"""Auditable deterministic recovery for failed executions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Mapping

from runtime.exceptions import (
    DuplicateExecutionError,
    DuplicateRecoveryError,
    ExecutionFailedError,
    ExecutionNotRecoverableError,
    InvalidRecoveryActionError,
    RecoveryNotFoundError,
    ValidationError,
)
from runtime.execution.result import ExecutionResult, ExecutionStatus
from runtime.execution.service import ExecutionService
from runtime.models.lifecycle import LifecycleState
from runtime.models.work_item import WorkItem
from runtime.models.work_package import WorkPackage
from runtime.orchestration.assignment import AssignmentStatus, WorkAssignment
from runtime.validation import validate_required_string
from runtime.transactions import atomic_domain_operation

if TYPE_CHECKING:
    from runtime.events.publisher import EventPublisher


class RecoveryAction(str, Enum):
    """Named recovery actions permitted for failed executions."""

    RETRY = "RETRY"
    RESET_TO_ASSIGNED = "RESET_TO_ASSIGNED"
    CANCEL_ASSIGNMENT = "CANCEL_ASSIGNMENT"


def validate_recovery_action(value: object) -> None:
    """Require a RecoveryAction enum member."""
    if not isinstance(value, RecoveryAction):
        raise InvalidRecoveryActionError(
            "recovery action must be a RecoveryAction enum value"
        )


@dataclass(frozen=True)
class ExecutionRecoveryRecord:
    """Immutable audit record for one recovery action."""

    id: str
    execution_id: str
    assignment_id: str
    action: RecoveryAction
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        validate_required_string(self.id, "ExecutionRecoveryRecord.id")
        validate_required_string(
            self.execution_id,
            "ExecutionRecoveryRecord.execution_id",
        )
        validate_required_string(
            self.assignment_id,
            "ExecutionRecoveryRecord.assignment_id",
        )
        validate_recovery_action(self.action)
        validate_required_string(self.reason, "ExecutionRecoveryRecord.reason")
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() != timedelta(0)
        ):
            raise ValidationError(
                "ExecutionRecoveryRecord.created_at must be timezone-aware UTC"
            )


class ExecutionRecoveryService:
    """Recover failed executions while preserving complete history."""

    def __init__(
        self,
        execution_service: ExecutionService,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        if not isinstance(execution_service, ExecutionService):
            raise ValidationError(
                "execution_service must be an ExecutionService value"
            )
        self.execution_service = execution_service
        self.event_publisher = event_publisher
        self._records: dict[str, ExecutionRecoveryRecord] = {}
        if event_publisher is not None:
            event_publisher.register_snapshot_provider(self._snapshot_targets)

    @atomic_domain_operation
    def retry_failed_execution(
        self,
        recovery_id: str,
        execution_id: str,
        new_execution_id: str,
        reason: str,
        context: Mapping[str, object] | None = None,
    ) -> ExecutionResult:
        """Reset failed work to ASSIGNED and execute under original requirements."""
        original, assignment = self._validate_recoverable(
            recovery_id,
            execution_id,
            reason,
        )
        validate_required_string(new_execution_id, "new_execution_id")
        if any(
            execution.id == new_execution_id
            for execution in self.execution_service.list_executions()
        ):
            raise DuplicateExecutionError(
                f"Execution {new_execution_id!r} already exists"
            )
        work_item, package = self._get_work_and_package(assignment)
        work_item_state = work_item.lifecycle_state
        package_updated_at = package.updated_at
        try:
            self.execution_service.orchestrator.runtime_engine.recover_work_item_state(
                assignment.package_id,
                assignment.work_item_id,
                LifecycleState.ASSIGNED,
                reason,
            )
            try:
                result = self.execution_service.execute_assignment(
                    new_execution_id,
                    assignment.id,
                    context,
                )
            except ExecutionFailedError:
                self._store_record(
                    recovery_id,
                    original,
                    RecoveryAction.RETRY,
                    reason,
                )
                raise
            self._store_record(
                recovery_id,
                original,
                RecoveryAction.RETRY,
                reason,
            )
            return result
        except Exception:
            if new_execution_id not in {
                execution.id
                for execution in self.execution_service.list_executions()
            }:
                # Compensating rollback after a later atomic step failed.
                # Normal and recovery transition APIs cannot express rollback.
                work_item.lifecycle_state = work_item_state
                package.updated_at = package_updated_at
            raise

    @atomic_domain_operation
    def reset_failed_execution(
        self,
        recovery_id: str,
        execution_id: str,
        reason: str,
    ) -> ExecutionRecoveryRecord:
        """Explicitly reset failed RUNNING work to ASSIGNED."""
        original, assignment = self._validate_recoverable(
            recovery_id,
            execution_id,
            reason,
        )
        work_item, package = self._get_work_and_package(assignment)
        work_item_state = work_item.lifecycle_state
        package_updated_at = package.updated_at
        try:
            self.execution_service.orchestrator.runtime_engine.recover_work_item_state(
                assignment.package_id,
                assignment.work_item_id,
                LifecycleState.ASSIGNED,
                reason,
            )
            return self._store_record(
                recovery_id,
                original,
                RecoveryAction.RESET_TO_ASSIGNED,
                reason,
            )
        except Exception:
            # Compensating rollback after recovery succeeded but audit storage failed.
            work_item.lifecycle_state = work_item_state
            package.updated_at = package_updated_at
            self._records.pop(recovery_id, None)
            raise

    @atomic_domain_operation
    def cancel_failed_assignment(
        self,
        recovery_id: str,
        execution_id: str,
        reason: str,
    ) -> ExecutionRecoveryRecord:
        """Reset failed work, then cancel through orchestrator policy."""
        original, assignment = self._validate_recoverable(
            recovery_id,
            execution_id,
            reason,
        )
        work_item, package = self._get_work_and_package(assignment)
        agent = self.execution_service.agent_registry.get_agent(
            assignment.agent_id
        )
        snapshot = (
            work_item.lifecycle_state,
            work_item.assigned_to,
            assignment.status,
            assignment.updated_at,
            agent.state,
            package.updated_at,
        )
        try:
            self.execution_service.orchestrator.runtime_engine.recover_work_item_state(
                assignment.package_id,
                assignment.work_item_id,
                LifecycleState.ASSIGNED,
                reason,
            )
            self.execution_service.orchestrator.cancel_assignment(
                assignment.id
            )
            return self._store_record(
                recovery_id,
                original,
                RecoveryAction.CANCEL_ASSIGNMENT,
                reason,
            )
        except Exception:
            # Compensating rollback of a multi-object recovery transaction.
            (
                work_item.lifecycle_state,
                work_item.assigned_to,
                assignment.status,
                assignment.updated_at,
                agent.state,
                package.updated_at,
            ) = snapshot
            self._records.pop(recovery_id, None)
            raise

    def get_recovery_record(
        self,
        recovery_id: str,
    ) -> ExecutionRecoveryRecord:
        """Retrieve a recovery record by identifier."""
        validate_required_string(recovery_id, "recovery_id")
        if recovery_id not in self._records:
            raise RecoveryNotFoundError(
                f"Recovery record {recovery_id!r} was not found"
            )
        return self._records[recovery_id]

    def list_recovery_records(self) -> list[ExecutionRecoveryRecord]:
        """Return recovery records in insertion order."""
        return list(self._records.values())

    def list_recovery_records_for_execution(
        self,
        execution_id: str,
    ) -> list[ExecutionRecoveryRecord]:
        """Return recovery records for an existing execution."""
        self.execution_service.get_execution(execution_id)
        return [
            record
            for record in self._records.values()
            if record.execution_id == execution_id
        ]

    def _validate_recoverable(
        self,
        recovery_id: str,
        execution_id: str,
        reason: str,
    ) -> tuple[ExecutionResult, WorkAssignment]:
        validate_required_string(recovery_id, "recovery_id")
        validate_required_string(reason, "reason")
        if recovery_id in self._records:
            raise DuplicateRecoveryError(
                f"Recovery record {recovery_id!r} already exists"
            )
        execution = self.execution_service.get_execution(execution_id)
        if execution.status != ExecutionStatus.FAILED:
            raise ExecutionNotRecoverableError(
                "Only FAILED executions can be recovered"
            )
        assignment = self.execution_service.orchestrator.get_assignment(
            execution.assignment_id
        )
        if assignment.status != AssignmentStatus.ACTIVE:
            raise ExecutionNotRecoverableError(
                "Recovery requires an ACTIVE assignment"
            )
        work_item = self.execution_service.orchestrator.runtime_engine.get_work_item(
            assignment.package_id,
            assignment.work_item_id,
        )
        if work_item.lifecycle_state != LifecycleState.RUNNING:
            raise ExecutionNotRecoverableError(
                "Recovery requires work item RUNNING"
            )
        return execution, assignment

    def _get_work_and_package(
        self,
        assignment: WorkAssignment,
    ) -> tuple[WorkItem, WorkPackage]:
        work_item = self.execution_service.orchestrator.runtime_engine.get_work_item(
            assignment.package_id,
            assignment.work_item_id,
        )
        package = self.execution_service.orchestrator.runtime_engine.get_work_package(
            assignment.package_id
        )
        return work_item, package

    def _store_record(
        self,
        recovery_id: str,
        execution: ExecutionResult,
        action: RecoveryAction,
        reason: str,
    ) -> ExecutionRecoveryRecord:
        record = ExecutionRecoveryRecord(
            id=recovery_id,
            execution_id=execution.id,
            assignment_id=execution.assignment_id,
            action=action,
            reason=reason,
        )
        self._records[record.id] = record
        try:
            self._publish(record)
        except Exception:
            self._records.pop(record.id, None)
            raise
        return record

    def _publish(self, record: ExecutionRecoveryRecord) -> None:
        if self.event_publisher is None:
            return
        from runtime.events.types import EventType

        event_by_action = {
            RecoveryAction.RETRY: EventType.EXECUTION_RECOVERY_RETRIED,
            RecoveryAction.RESET_TO_ASSIGNED: EventType.EXECUTION_RECOVERY_RESET,
            RecoveryAction.CANCEL_ASSIGNMENT: (
                EventType.EXECUTION_RECOVERY_CANCELLED
            ),
        }
        self.event_publisher.publish(
            event_by_action[record.action],
            "RECOVERY",
            record.id,
            {
                "execution_id": record.execution_id,
                "assignment_id": record.assignment_id,
                "reason": record.reason,
            },
        )

    def _snapshot_targets(self) -> list[object]:
        return [self._records, *self._records.values()]
