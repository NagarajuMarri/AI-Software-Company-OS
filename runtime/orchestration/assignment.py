"""Assignment models and lifecycle policy."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from runtime.exceptions import (
    InvalidAssignmentStateTransitionError,
    ValidationError,
)
from runtime.validation import validate_required_string


class AssignmentStatus(str, Enum):
    """Lifecycle states for a work assignment."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


ASSIGNMENT_STATUS_TRANSITIONS: dict[
    AssignmentStatus, frozenset[AssignmentStatus]
] = {
    AssignmentStatus.CREATED: frozenset(
        {AssignmentStatus.ACTIVE, AssignmentStatus.CANCELLED}
    ),
    AssignmentStatus.ACTIVE: frozenset(
        {AssignmentStatus.COMPLETED, AssignmentStatus.CANCELLED}
    ),
    AssignmentStatus.COMPLETED: frozenset(),
    AssignmentStatus.CANCELLED: frozenset(),
}


def validate_assignment_status(value: object) -> None:
    """Require an AssignmentStatus enum member."""
    if not isinstance(value, AssignmentStatus):
        raise ValidationError(
            "assignment status must be an AssignmentStatus enum value; "
            f"received {type(value).__name__}"
        )


def validate_assignment_status_transition(
    current_status: AssignmentStatus,
    new_status: AssignmentStatus,
) -> None:
    """Require an assignment status change allowed by policy."""
    validate_assignment_status(current_status)
    validate_assignment_status(new_status)
    if new_status not in ASSIGNMENT_STATUS_TRANSITIONS[current_status]:
        raise InvalidAssignmentStateTransitionError(
            f"Cannot transition assignment from {current_status.value} "
            f"to {new_status.value}"
        )


def validate_utc_timestamp(value: object, field_name: str) -> None:
    """Require a timezone-aware UTC datetime."""
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValidationError(f"{field_name} must be a timezone-aware UTC datetime")


@dataclass
class WorkAssignment:
    """Relationship between a work item and its selected agent."""

    id: str
    package_id: str
    work_item_id: str
    agent_id: str
    status: AssignmentStatus = AssignmentStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        validate_required_string(self.id, "WorkAssignment.id")
        validate_required_string(self.package_id, "WorkAssignment.package_id")
        validate_required_string(self.work_item_id, "WorkAssignment.work_item_id")
        validate_required_string(self.agent_id, "WorkAssignment.agent_id")
        validate_assignment_status(self.status)
        validate_utc_timestamp(self.created_at, "WorkAssignment.created_at")
        validate_utc_timestamp(self.updated_at, "WorkAssignment.updated_at")
        if self.updated_at < self.created_at:
            raise ValidationError(
                "WorkAssignment.updated_at cannot precede created_at"
            )

    def change_status(self, new_status: AssignmentStatus) -> None:
        """Change assignment status according to policy."""
        validate_assignment_status_transition(self.status, new_status)
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
