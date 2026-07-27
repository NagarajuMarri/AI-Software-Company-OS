"""Assignment models and lifecycle policy."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from runtime.agents.role import AgentRole, validate_agent_role
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
    required_role: AgentRole | None = None
    required_capabilities: tuple[str, ...] | list[str] = ()
    selection_reason: str = "No selection metadata supplied"
    selected_agent_priority: int = 0
    selected_agent_active_assignment_count: int = 0

    _IMMUTABLE_REQUIREMENT_FIELDS = frozenset(
        {
            "required_role",
            "required_capabilities",
            "selection_reason",
            "selected_agent_priority",
            "selected_agent_active_assignment_count",
        }
    )

    def __setattr__(self, name: str, value: object) -> None:
        if (
            name in self._IMMUTABLE_REQUIREMENT_FIELDS
            and name in self.__dict__
        ):
            raise AttributeError(f"{name} is an immutable assignment requirement")
        super().__setattr__(name, value)

    def __post_init__(self) -> None:
        validate_required_string(self.id, "WorkAssignment.id")
        validate_required_string(self.package_id, "WorkAssignment.package_id")
        validate_required_string(self.work_item_id, "WorkAssignment.work_item_id")
        validate_required_string(self.agent_id, "WorkAssignment.agent_id")
        if self.required_role is not None:
            validate_agent_role(self.required_role)
        if not isinstance(self.required_capabilities, (list, tuple)):
            raise ValidationError(
                "WorkAssignment.required_capabilities must be a list or tuple"
            )
        for capability_id in self.required_capabilities:
            validate_required_string(
                capability_id,
                "WorkAssignment.required_capabilities",
            )
        if len(self.required_capabilities) != len(
            set(self.required_capabilities)
        ):
            raise ValidationError(
                "WorkAssignment.required_capabilities must not contain duplicates"
            )
        object.__setattr__(
            self,
            "required_capabilities",
            tuple(self.required_capabilities),
        )
        validate_required_string(
            self.selection_reason,
            "WorkAssignment.selection_reason",
        )
        if not isinstance(self.selected_agent_priority, int) or isinstance(
            self.selected_agent_priority,
            bool,
        ):
            raise ValidationError(
                "WorkAssignment.selected_agent_priority must be an integer"
            )
        if (
            not isinstance(self.selected_agent_active_assignment_count, int)
            or isinstance(self.selected_agent_active_assignment_count, bool)
            or self.selected_agent_active_assignment_count < 0
        ):
            raise ValidationError(
                "WorkAssignment.selected_agent_active_assignment_count "
                "must be a non-negative integer"
            )
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
