from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from runtime.models.lifecycle import (
    LifecycleState,
    validate_lifecycle_state,
    validate_lifecycle_transition,
)
from runtime.validation import validate_optional_string, validate_required_string


@dataclass
class WorkItem:
    """Represents a single executable unit of work within a work package."""

    id: str
    title: str
    description: str
    priority: str = "normal"
    dependencies: List[str] = field(default_factory=list)
    assigned_to: Optional[str] = None
    lifecycle_state: LifecycleState = LifecycleState.CREATED

    def __post_init__(self) -> None:
        validate_required_string(self.id, "WorkItem.id")
        validate_required_string(self.title, "WorkItem.title")
        validate_required_string(self.description, "WorkItem.description")
        validate_required_string(self.priority, "WorkItem.priority")
        validate_optional_string(self.assigned_to, "WorkItem.assigned_to")
        validate_lifecycle_state(self.lifecycle_state)

    def change_state(self, new_state: LifecycleState) -> None:
        """Update the lifecycle state for the work item.

        Args:
            new_state: The target lifecycle state.
        """
        validate_lifecycle_transition(self.lifecycle_state, new_state)
        self.lifecycle_state = new_state
