from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from runtime.models.lifecycle import LifecycleState


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

    def change_state(self, new_state: LifecycleState) -> None:
        """Update the lifecycle state for the work item.

        Args:
            new_state: The target lifecycle state.
        """
        self.lifecycle_state = new_state
