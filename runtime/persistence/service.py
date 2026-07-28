"""Checkpoint capture, validation, and runtime restoration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.events.event import RuntimeEvent
from runtime.events.types import EventType
from runtime.execution.recovery import (
    ExecutionRecoveryRecord,
    RecoveryAction,
)
from runtime.execution.result import ExecutionResult, ExecutionStatus
from runtime.models.lifecycle import LifecycleState
from runtime.models.artifact import Artifact
from runtime.models.work_item import WorkItem
from runtime.models.work_package import WorkPackage
from runtime.orchestration.assignment import (
    AssignmentStatus,
    WorkAssignment,
)
from runtime.persistence.exceptions import (
    PersistenceCommitError,
    PersistenceConfigurationError,
    RuntimeRestoreError,
)
from runtime.persistence.interfaces import PersistenceProvider
from runtime.persistence.models import RuntimeCheckpoint
from runtime.persistence.models import (
    CheckpointSelection,
    DurabilityStatus,
    PersistenceCommitResult,
)
from runtime.persistence.serializer import CanonicalSerializer
from runtime.workflows.models import (
    SoftwareDeliveryRequest,
    SoftwareDeliveryWorkflow,
    WorkflowStage,
)

if TYPE_CHECKING:
    from runtime.composition.container import ASCOSRuntimeContainer


AUTOMATIC_OPERATIONS = frozenset(
    {
        "submit_request",
        "assign_work",
        "execute_work",
        "recover_failed_execution",
        "approve_work",
        "complete_work",
        "release_work",
        "cancel_workflow",
    }
)


class RuntimePersistenceService:
    """Persist complete runtime snapshots without coupling domain services."""

    def __init__(
        self,
        provider: PersistenceProvider,
        runtime_id: str,
        container: ASCOSRuntimeContainer,
        *,
        automatic_checkpoint_policy: bool = False,
    ) -> None:
        if not isinstance(provider, PersistenceProvider):
            raise PersistenceConfigurationError(
                "persistence_provider does not implement PersistenceProvider"
            )
        if not isinstance(runtime_id, str) or not runtime_id:
            raise PersistenceConfigurationError("runtime_id is required")
        if not isinstance(automatic_checkpoint_policy, bool):
            raise PersistenceConfigurationError(
                "automatic_checkpoint_policy must be boolean"
            )
        self.provider = provider
        self.runtime_id = runtime_id
        self.container = container
        self.automatic_checkpoint_policy = automatic_checkpoint_policy
        self._automatic_counter = len(
            provider.list_checkpoints(runtime_id)
        )
        self.last_commit_result = PersistenceCommitResult(
            runtime_id,
            "initial",
            self._automatic_counter,
            None,
            0,
            False,
            False,
            DurabilityStatus.NOT_ATTEMPTED,
            None,
        )
        self.last_checkpoint_selection: CheckpointSelection | None = None
        self.last_restore_missing_executors: tuple[str, ...] = ()

    def after_atomic_operation(self, operation: str, result: object) -> None:
        if (
            not self.automatic_checkpoint_policy
            or operation not in AUTOMATIC_OPERATIONS
        ):
            return
        self._automatic_counter += 1
        try:
            self.save_checkpoint(
                reason=f"automatic:{operation}",
                checkpoint_id=(
                    f"auto-{self._automatic_counter:06d}-{operation}"
                ),
            )
        except Exception as error:
            self.last_commit_result = PersistenceCommitResult(
                self.runtime_id,
                operation,
                self._automatic_counter,
                None,
                len(self.container.event_store.list_events()),
                True,
                False,
                DurabilityStatus.COMMITTED_NOT_CHECKPOINTED,
                datetime.now(timezone.utc),
            )
            raise PersistenceCommitError(
                "Domain committed but automatic checkpoint failed"
            ) from error

    def save_checkpoint(
        self,
        reason: str,
        *,
        checkpoint_id: str | None = None,
    ) -> RuntimeCheckpoint:
        payload = self._capture()
        position = len(self.container.event_store.list_events())
        resolved_id = checkpoint_id or (
            f"checkpoint-{position:08d}-{len(self.list_checkpoints()) + 1:06d}"
        )
        checkpoint = RuntimeCheckpoint.create(
            resolved_id,
            self.runtime_id,
            reason,
            position,
            payload,
        )
        try:
            self.provider.save_checkpoint(checkpoint)
        except Exception:
            self.last_commit_result = PersistenceCommitResult(
                self.runtime_id,
                resolved_id,
                len(self.list_checkpoints()),
                None,
                position,
                True,
                False,
                DurabilityStatus.COMMITTED_NOT_CHECKPOINTED,
                datetime.now(timezone.utc),
            )
            raise
        self.last_commit_result = PersistenceCommitResult(
            self.runtime_id,
            resolved_id,
            len(self.list_checkpoints()),
            resolved_id,
            position,
            True,
            True,
            DurabilityStatus.COMMITTED_DURABLE,
            datetime.now(timezone.utc),
        )
        return checkpoint

    def load_checkpoint(self, checkpoint_id: str) -> RuntimeCheckpoint:
        checkpoint = self.provider.load_checkpoint(checkpoint_id)
        self.validate_checkpoint(checkpoint)
        return checkpoint

    def load_latest_checkpoint(
        self,
        *,
        recovery_mode: bool = False,
    ) -> RuntimeCheckpoint:
        if hasattr(self.provider, "select_latest_checkpoint"):
            selection = self.provider.select_latest_checkpoint(
                self.runtime_id,
                recovery_mode=recovery_mode,
            )
            self.last_checkpoint_selection = selection
            checkpoint = selection.checkpoint
        else:
            checkpoint = self.provider.load_latest_checkpoint(self.runtime_id)
            self.last_checkpoint_selection = CheckpointSelection(
                checkpoint,
                recovery_mode,
            )
        self.validate_checkpoint(checkpoint)
        return checkpoint

    def list_checkpoints(self) -> list[RuntimeCheckpoint]:
        return self.provider.list_checkpoints(self.runtime_id)

    def validate_checkpoint(self, checkpoint: RuntimeCheckpoint) -> None:
        if checkpoint.runtime_id != self.runtime_id:
            raise RuntimeRestoreError("Checkpoint runtime_id does not match")
        if checkpoint.last_event_position != len(checkpoint.payload["events"]):
            raise RuntimeRestoreError(
                "Checkpoint event position does not match event stream"
            )
        self._build_state(dict(checkpoint.payload))

    def restore_runtime(
        self,
        checkpoint: RuntimeCheckpoint,
    ) -> ASCOSRuntimeContainer:
        self.validate_checkpoint(checkpoint)
        built = self._build_state(dict(checkpoint.payload))
        container = self.container
        try:
            container.runtime_engine._work_packages = built["packages"]
            container.agent_registry._agents = built["agents"]
            container.orchestrator._assignments = built["assignments"]
            container.execution_service._executions = built["executions"]
            container.execution_recovery_service._records = built["recoveries"]
            container.artifact_store._artifacts = built["artifacts"]
            workflow_service = container.software_delivery_workflow_service
            workflow_service._requests = built["requests"]
            workflow_service._workflows = built["workflows"]
            container.event_store._events = built["events"]
        except Exception as error:
            raise RuntimeRestoreError("Runtime restoration failed") from error
        self.last_restore_missing_executors = (
            self.validate_executor_readiness()
        )
        return container

    def validate_executor_readiness(self) -> tuple[str, ...]:
        missing = []
        for assignment in self.container.orchestrator.list_assignments():
            if assignment.status != AssignmentStatus.ACTIVE:
                continue
            agent = self.container.agent_registry.get_agent(
                assignment.agent_id
            )
            try:
                self.container.executor_registry.select_executor(
                    agent,
                    assignment,
                )
            except Exception:
                missing.append(assignment.id)
        return tuple(missing)

    def _capture(self) -> dict:
        container = self.container
        workflows = container.software_delivery_workflow_service
        return {
            "type": "ascos.runtime-state",
            "version": 1,
            "packages": [
                {
                    "id": package.id,
                    "title": package.title,
                    "description": package.description,
                    "owner": package.owner,
                    "lifecycle_state": package.lifecycle_state.value,
                    "work_items": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "description": item.description,
                            "priority": item.priority,
                            "dependencies": list(item.dependencies),
                            "assigned_to": item.assigned_to,
                            "lifecycle_state": item.lifecycle_state.value,
                        }
                        for item in package.work_items
                    ],
                    "artifacts": list(package.artifacts),
                    "created_at": package.created_at.isoformat(),
                    "updated_at": package.updated_at.isoformat(),
                }
                for package in container.runtime_engine.list_work_packages()
            ],
            "agents": [
                {
                    "id": agent.id,
                    "display_name": agent.display_name,
                    "role": agent.role.value,
                    "description": agent.description,
                    "state": agent.state.value,
                    "capabilities": [
                        {
                            "id": capability.id,
                            "name": capability.name,
                            "description": capability.description,
                            "version": capability.version,
                            "tags": list(capability.tags),
                        }
                        for capability in agent.supported_capabilities
                    ],
                    "max_parallel_tasks": agent.max_parallel_tasks,
                    "priority": agent.priority,
                }
                for agent in container.agent_registry.list_agents()
            ],
            "artifacts": [
                {
                    "id": artifact.id,
                    "name": artifact.name,
                    "type": artifact.type,
                    "version": artifact.version,
                    "work_item_id": artifact.work_item_id,
                    "lifecycle_state": artifact.lifecycle_state.value,
                }
                for artifact in container.artifact_store.list_artifacts()
            ],
            "assignments": [
                {
                    "id": item.id,
                    "package_id": item.package_id,
                    "work_item_id": item.work_item_id,
                    "agent_id": item.agent_id,
                    "status": item.status.value,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                    "required_role": (
                        item.required_role.value
                        if item.required_role is not None
                        else None
                    ),
                    "required_capabilities": list(
                        item.required_capabilities
                    ),
                    "selection_reason": item.selection_reason,
                    "selected_agent_priority": item.selected_agent_priority,
                    "selected_agent_active_assignment_count": (
                        item.selected_agent_active_assignment_count
                    ),
                }
                for item in container.orchestrator.list_assignments()
            ],
            "executions": [
                {
                    "id": item.id,
                    "assignment_id": item.assignment_id,
                    "work_item_id": item.work_item_id,
                    "agent_id": item.agent_id,
                    "status": item.status.value,
                    "output": item.output,
                    "error": item.error,
                    "started_at": (
                        item.started_at.isoformat()
                        if item.started_at is not None
                        else None
                    ),
                    "completed_at": (
                        item.completed_at.isoformat()
                        if item.completed_at is not None
                        else None
                    ),
                }
                for item in container.execution_service.list_executions()
            ],
            "recoveries": [
                {
                    "id": item.id,
                    "execution_id": item.execution_id,
                    "assignment_id": item.assignment_id,
                    "action": item.action.value,
                    "reason": item.reason,
                    "created_at": item.created_at.isoformat(),
                }
                for item in (
                    container.execution_recovery_service.list_recovery_records()
                )
            ],
            "requests": [
                {
                    "id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "requested_by": item.requested_by,
                    "required_role": item.required_role.value,
                    "required_capabilities": list(
                        item.required_capabilities
                    ),
                    "acceptance_criteria": list(item.acceptance_criteria),
                    "priority": item.priority,
                    "correlation_id": item.correlation_id,
                    "created_at": item.created_at.isoformat(),
                }
                for item in workflows._requests.values()
            ],
            "workflows": [
                {
                    "id": item.id,
                    "request_id": item.request_id,
                    "work_package_id": item.work_package_id,
                    "work_item_id": item.work_item_id,
                    "assignment_id": item.assignment_id,
                    "execution_ids": list(item.execution_ids),
                    "current_stage": item.current_stage.value,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                    "failure_reason": item.failure_reason,
                    "rejection_reason": item.rejection_reason,
                    "approved_at": (
                        item.approved_at.isoformat()
                        if item.approved_at is not None
                        else None
                    ),
                }
                for item in workflows.list_workflows()
            ],
            "events": [
                {
                    "id": event.id,
                    "event_type": event.event_type.value,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": event.aggregate_id,
                    "sequence_number": event.sequence_number,
                    "payload": CanonicalSerializer.encode_value(event.payload),
                    "occurred_at": event.occurred_at.isoformat(),
                    "correlation_id": event.correlation_id,
                    "causation_id": event.causation_id,
                }
                for event in container.event_store.list_events()
            ],
        }

    def _build_state(self, payload: dict) -> dict:
        try:
            if (
                payload.get("type") != "ascos.runtime-state"
                or payload.get("version") != 1
            ):
                raise RuntimeRestoreError("Unsupported runtime state payload")
            packages = {}
            for value in payload["packages"]:
                items = [
                    WorkItem(
                        id=item["id"],
                        title=item["title"],
                        description=item["description"],
                        priority=item["priority"],
                        dependencies=list(item["dependencies"]),
                        assigned_to=item["assigned_to"],
                        lifecycle_state=LifecycleState(
                            item["lifecycle_state"]
                        ),
                    )
                    for item in value["work_items"]
                ]
                package = WorkPackage(
                    id=value["id"],
                    title=value["title"],
                    description=value["description"],
                    owner=value["owner"],
                    lifecycle_state=LifecycleState(
                        value["lifecycle_state"]
                    ),
                    work_items=items,
                    artifacts=list(value["artifacts"]),
                    created_at=datetime.fromisoformat(value["created_at"]),
                    updated_at=datetime.fromisoformat(value["updated_at"]),
                )
                packages[package.id] = package
            agents = {}
            for value in payload["agents"]:
                capabilities = [
                    AgentCapability(
                        item["id"],
                        item["name"],
                        item["description"],
                        item["version"],
                        list(item["tags"]),
                    )
                    for item in value["capabilities"]
                ]
                agent = AgentMetadata(
                    value["id"],
                    value["display_name"],
                    AgentRole(value["role"]),
                    value["description"],
                    AgentState(value["state"]),
                    capabilities,
                    value["max_parallel_tasks"],
                    value["priority"],
                )
                agents[agent.id] = agent
            artifacts = {
                value["id"]: Artifact(
                    id=value["id"],
                    name=value["name"],
                    type=value["type"],
                    version=value["version"],
                    work_item_id=value["work_item_id"],
                    lifecycle_state=LifecycleState(
                        value["lifecycle_state"]
                    ),
                )
                for value in payload["artifacts"]
            }
            assignments = {}
            for value in payload["assignments"]:
                assignment = WorkAssignment(
                    id=value["id"],
                    package_id=value["package_id"],
                    work_item_id=value["work_item_id"],
                    agent_id=value["agent_id"],
                    status=AssignmentStatus(value["status"]),
                    created_at=datetime.fromisoformat(value["created_at"]),
                    updated_at=datetime.fromisoformat(value["updated_at"]),
                    required_role=(
                        AgentRole(value["required_role"])
                        if value["required_role"] is not None
                        else None
                    ),
                    required_capabilities=list(
                        value["required_capabilities"]
                    ),
                    selection_reason=value["selection_reason"],
                    selected_agent_priority=value[
                        "selected_agent_priority"
                    ],
                    selected_agent_active_assignment_count=value[
                        "selected_agent_active_assignment_count"
                    ],
                )
                assignments[assignment.id] = assignment
            executions = {}
            for value in payload["executions"]:
                execution = ExecutionResult(
                    id=value["id"],
                    assignment_id=value["assignment_id"],
                    work_item_id=value["work_item_id"],
                    agent_id=value["agent_id"],
                    status=ExecutionStatus(value["status"]),
                    output=value["output"],
                    error=value["error"],
                    started_at=(
                        datetime.fromisoformat(value["started_at"])
                        if value["started_at"] is not None
                        else None
                    ),
                    completed_at=(
                        datetime.fromisoformat(value["completed_at"])
                        if value["completed_at"] is not None
                        else None
                    ),
                )
                executions[execution.id] = execution
            recoveries = {
                value["id"]: ExecutionRecoveryRecord(
                    id=value["id"],
                    execution_id=value["execution_id"],
                    assignment_id=value["assignment_id"],
                    action=RecoveryAction(value["action"]),
                    reason=value["reason"],
                    created_at=datetime.fromisoformat(value["created_at"]),
                )
                for value in payload["recoveries"]
            }
            requests = {
                value["id"]: SoftwareDeliveryRequest(
                    id=value["id"],
                    title=value["title"],
                    description=value["description"],
                    requested_by=value["requested_by"],
                    required_role=AgentRole(value["required_role"]),
                    required_capabilities=list(
                        value["required_capabilities"]
                    ),
                    acceptance_criteria=list(value["acceptance_criteria"]),
                    priority=value["priority"],
                    correlation_id=value["correlation_id"],
                    created_at=datetime.fromisoformat(value["created_at"]),
                )
                for value in payload["requests"]
            }
            workflows = {
                value["id"]: SoftwareDeliveryWorkflow(
                    id=value["id"],
                    request_id=value["request_id"],
                    work_package_id=value["work_package_id"],
                    work_item_id=value["work_item_id"],
                    assignment_id=value["assignment_id"],
                    execution_ids=list(value["execution_ids"]),
                    current_stage=WorkflowStage(value["current_stage"]),
                    created_at=datetime.fromisoformat(value["created_at"]),
                    updated_at=datetime.fromisoformat(value["updated_at"]),
                    failure_reason=value["failure_reason"],
                    rejection_reason=value["rejection_reason"],
                    approved_at=(
                        datetime.fromisoformat(value["approved_at"])
                        if value["approved_at"] is not None
                        else None
                    ),
                )
                for value in payload["workflows"]
            }
            events = {}
            sequences: dict[tuple[str, str], int] = {}
            for value in payload["events"]:
                event_payload = CanonicalSerializer.decode_value(
                    value["payload"]
                )
                if not isinstance(event_payload, dict):
                    raise RuntimeRestoreError("Event payload is invalid")
                event = RuntimeEvent(
                    id=value["id"],
                    event_type=EventType(value["event_type"]),
                    aggregate_type=value["aggregate_type"],
                    aggregate_id=value["aggregate_id"],
                    sequence_number=value["sequence_number"],
                    payload=event_payload,
                    occurred_at=datetime.fromisoformat(value["occurred_at"]),
                    correlation_id=value["correlation_id"],
                    causation_id=value["causation_id"],
                )
                key = (event.aggregate_type, event.aggregate_id)
                expected = sequences.get(key, 0) + 1
                if event.sequence_number != expected or event.id in events:
                    raise RuntimeRestoreError(
                        "Event sequence continuity is invalid"
                    )
                sequences[key] = expected
                events[event.id] = event
            self._validate_references(
                packages,
                agents,
                assignments,
                executions,
                recoveries,
                artifacts,
                requests,
                workflows,
            )
            return {
                "packages": packages,
                "agents": agents,
                "assignments": assignments,
                "executions": executions,
                "recoveries": recoveries,
                "artifacts": artifacts,
                "requests": requests,
                "workflows": workflows,
                "events": events,
            }
        except RuntimeRestoreError:
            raise
        except Exception as error:
            raise RuntimeRestoreError(
                "Checkpoint contains malformed runtime state"
            ) from error

    @staticmethod
    def _validate_references(
        packages,
        agents,
        assignments,
        executions,
        recoveries,
        artifacts,
        requests,
        workflows,
    ) -> None:
        for assignment in assignments.values():
            if (
                assignment.package_id not in packages
                or assignment.agent_id not in agents
            ):
                raise RuntimeRestoreError("Invalid assignment reference")
            try:
                packages[assignment.package_id].get_work_item(
                    assignment.work_item_id
                )
            except Exception as error:
                raise RuntimeRestoreError(
                    "Invalid assignment work-item reference"
                ) from error
        for execution in executions.values():
            if execution.assignment_id not in assignments:
                raise RuntimeRestoreError("Invalid execution reference")
        for recovery in recoveries.values():
            if (
                recovery.execution_id not in executions
                or recovery.assignment_id not in assignments
            ):
                raise RuntimeRestoreError("Invalid recovery reference")
        work_item_ids = {
            item.id
            for package in packages.values()
            for item in package.work_items
        }
        for artifact in artifacts.values():
            if (
                artifact.work_item_id is not None
                and artifact.work_item_id not in work_item_ids
            ):
                raise RuntimeRestoreError("Invalid artifact reference")
        for workflow in workflows.values():
            if (
                workflow.request_id not in requests
                or workflow.work_package_id not in packages
            ):
                raise RuntimeRestoreError("Invalid workflow reference")
            try:
                packages[workflow.work_package_id].get_work_item(
                    workflow.work_item_id
                )
            except Exception as error:
                raise RuntimeRestoreError(
                    "Invalid workflow work-item reference"
                ) from error
            if (
                workflow.assignment_id is not None
                and workflow.assignment_id not in assignments
            ):
                raise RuntimeRestoreError(
                    "Invalid workflow assignment reference"
                )
            if any(
                execution_id not in executions
                for execution_id in workflow.execution_ids
            ):
                raise RuntimeRestoreError(
                    "Invalid workflow execution reference"
                )
