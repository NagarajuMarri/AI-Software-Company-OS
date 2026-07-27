"""Execution result model and lifecycle policy."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from runtime.exceptions import InvalidExecutionStateTransitionError, ValidationError
from runtime.validation import validate_optional_string, validate_required_string


class ExecutionStatus(str, Enum):
    """Lifecycle states for deterministic executions."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


EXECUTION_STATUS_TRANSITIONS: dict[
    ExecutionStatus, frozenset[ExecutionStatus]
] = {
    ExecutionStatus.CREATED: frozenset(
        {ExecutionStatus.RUNNING, ExecutionStatus.CANCELLED}
    ),
    ExecutionStatus.RUNNING: frozenset(
        {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        }
    ),
    ExecutionStatus.SUCCEEDED: frozenset(),
    ExecutionStatus.FAILED: frozenset(),
    ExecutionStatus.CANCELLED: frozenset(),
}


def validate_execution_status(value: object) -> None:
    """Require an ExecutionStatus enum member."""
    if not isinstance(value, ExecutionStatus):
        raise ValidationError(
            "execution status must be an ExecutionStatus enum value; "
            f"received {type(value).__name__}"
        )


def validate_execution_status_transition(
    current_status: ExecutionStatus,
    new_status: ExecutionStatus,
) -> None:
    """Require a transition allowed by the execution policy."""
    validate_execution_status(current_status)
    validate_execution_status(new_status)
    if new_status not in EXECUTION_STATUS_TRANSITIONS[current_status]:
        raise InvalidExecutionStateTransitionError(
            f"Cannot transition execution from {current_status.value} "
            f"to {new_status.value}"
        )


def validate_optional_utc_timestamp(
    value: object | None,
    field_name: str,
) -> None:
    """Validate a supplied timezone-aware UTC datetime."""
    if value is not None and (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValidationError(f"{field_name} must be a timezone-aware UTC datetime")


@dataclass
class ExecutionResult:
    """Outcome and timing details for one assignment execution."""

    id: str
    assignment_id: str
    work_item_id: str
    agent_id: str
    status: ExecutionStatus = ExecutionStatus.CREATED
    output: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_required_string(self.id, "ExecutionResult.id")
        validate_required_string(
            self.assignment_id,
            "ExecutionResult.assignment_id",
        )
        validate_required_string(
            self.work_item_id,
            "ExecutionResult.work_item_id",
        )
        validate_required_string(self.agent_id, "ExecutionResult.agent_id")
        validate_execution_status(self.status)
        validate_optional_string(self.output, "ExecutionResult.output")
        validate_optional_string(self.error, "ExecutionResult.error")
        validate_optional_utc_timestamp(
            self.started_at,
            "ExecutionResult.started_at",
        )
        validate_optional_utc_timestamp(
            self.completed_at,
            "ExecutionResult.completed_at",
        )
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValidationError(
                "ExecutionResult.completed_at cannot precede started_at"
            )
        self._validate_status_contract()

    def _validate_status_contract(self) -> None:
        if self.status == ExecutionStatus.CREATED:
            if self.started_at is not None or self.completed_at is not None:
                raise ValidationError("CREATED execution cannot have timestamps")
        elif self.status == ExecutionStatus.RUNNING:
            if self.started_at is None or self.completed_at is not None:
                raise ValidationError(
                    "RUNNING execution requires started_at only"
                )
        elif self.status == ExecutionStatus.SUCCEEDED:
            if (
                self.started_at is None
                or self.completed_at is None
                or self.output is None
                or self.error is not None
            ):
                raise ValidationError(
                    "SUCCEEDED execution requires timestamps and output only"
                )
        elif self.status == ExecutionStatus.FAILED:
            if (
                self.started_at is None
                or self.completed_at is None
                or self.error is None
            ):
                raise ValidationError(
                    "FAILED execution requires timestamps and error"
                )
        elif self.completed_at is None:
            raise ValidationError("CANCELLED execution requires completed_at")

    def mark_running(self) -> None:
        """Start a created execution."""
        validate_execution_status_transition(self.status, ExecutionStatus.RUNNING)
        self.status = ExecutionStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_succeeded(self, output: str) -> None:
        """Finish a running execution successfully."""
        validate_required_string(output, "ExecutionResult.output")
        validate_execution_status_transition(
            self.status,
            ExecutionStatus.SUCCEEDED,
        )
        self.status = ExecutionStatus.SUCCEEDED
        self.output = output
        self.error = None
        self.completed_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str) -> None:
        """Finish a running execution with a recorded error."""
        validate_required_string(error, "ExecutionResult.error")
        validate_execution_status_transition(self.status, ExecutionStatus.FAILED)
        self.status = ExecutionStatus.FAILED
        self.error = error
        self.completed_at = datetime.now(timezone.utc)

    def cancel(self) -> None:
        """Cancel a created or running execution."""
        validate_execution_status_transition(
            self.status,
            ExecutionStatus.CANCELLED,
        )
        self.status = ExecutionStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)
