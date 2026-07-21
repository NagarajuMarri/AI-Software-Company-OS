from __future__ import annotations

from dataclasses import dataclass

from runtime.models.lifecycle import LifecycleState


@dataclass
class Artifact:
    """Represents a generated artifact associated with a work item."""

    id: str
    name: str
    type: str
    version: str
    work_item_id: str | None = None
    lifecycle_state: LifecycleState = LifecycleState.CREATED

    def change_state(self, new_state: LifecycleState) -> None:
        """Update the lifecycle state for the artifact.

        Args:
            new_state: The target lifecycle state.
        """
        self.lifecycle_state = new_state
