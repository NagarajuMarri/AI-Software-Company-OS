from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from runtime.models.lifecycle import LifecycleState
from runtime.models.work_item import WorkItem


@dataclass
class WorkPackage:
    """Represents the top-level container for related work items and artifacts."""

    id: str
    title: str
    description: str
    owner: str
    lifecycle_state: LifecycleState = LifecycleState.CREATED
    work_items: List[WorkItem] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_work_item(self, work_item: WorkItem) -> None:
        """Add a work item to the package.

        Args:
            work_item: The work item to attach to the package.
        """
        self.work_items.append(work_item)
        self.updated_at = datetime.now(timezone.utc)

    def add_artifact(self, artifact_id: str) -> None:
        """Attach an artifact identifier to the work package.

        Args:
            artifact_id: The identifier of the artifact to track.
        """
        self.artifacts.append(artifact_id)
        self.updated_at = datetime.now(timezone.utc)
