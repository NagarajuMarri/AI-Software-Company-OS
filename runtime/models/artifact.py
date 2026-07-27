from __future__ import annotations

from dataclasses import dataclass

from runtime.models.lifecycle import (
    LifecycleState,
    validate_lifecycle_state,
    validate_lifecycle_transition,
)
from runtime.validation import validate_optional_string, validate_required_string


@dataclass
class Artifact:
    """Represents a generated artifact associated with a work item."""

    id: str
    name: str
    type: str
    version: str
    work_item_id: str | None = None
    lifecycle_state: LifecycleState = LifecycleState.CREATED

    def __post_init__(self) -> None:
        validate_required_string(self.id, "Artifact.id")
        validate_required_string(self.name, "Artifact.name")
        validate_required_string(self.type, "Artifact.type")
        validate_required_string(self.version, "Artifact.version")
        validate_optional_string(self.work_item_id, "Artifact.work_item_id")
        validate_lifecycle_state(self.lifecycle_state)

    def change_state(self, new_state: LifecycleState) -> None:
        """Update the lifecycle state for the artifact.

        Args:
            new_state: The target lifecycle state.
        """
        validate_lifecycle_transition(self.lifecycle_state, new_state)
        self.lifecycle_state = new_state
