from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from runtime.exceptions import (
    DuplicateArtifactError,
    DuplicateWorkItemError,
    WorkItemNotFoundError,
)
from runtime.models.lifecycle import LifecycleState
from runtime.models.work_item import WorkItem
from runtime.validation import validate_required_string


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

    def __post_init__(self) -> None:
        validate_required_string(self.id, "WorkPackage.id")
        validate_required_string(self.title, "WorkPackage.title")
        validate_required_string(self.description, "WorkPackage.description")
        validate_required_string(self.owner, "WorkPackage.owner")

        work_item_ids = [item.id for item in self.work_items]
        if len(work_item_ids) != len(set(work_item_ids)):
            raise DuplicateWorkItemError("WorkPackage contains duplicate work item IDs")

        for artifact_id in self.artifacts:
            validate_required_string(artifact_id, "WorkPackage.artifact_id")
        if len(self.artifacts) != len(set(self.artifacts)):
            raise DuplicateArtifactError("WorkPackage contains duplicate artifact IDs")

    def mark_updated(self) -> None:
        """Refresh the package modification timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    def add_work_item(self, work_item: WorkItem) -> None:
        """Add a work item to the package.

        Args:
            work_item: The work item to attach to the package.
        """
        if any(existing.id == work_item.id for existing in self.work_items):
            raise DuplicateWorkItemError(
                f"Work item {work_item.id!r} already exists in package {self.id!r}"
            )
        self.work_items.append(work_item)
        self.mark_updated()

    def get_work_item(self, work_item_id: str) -> WorkItem:
        """Return a work item by identifier."""
        for work_item in self.work_items:
            if work_item.id == work_item_id:
                return work_item
        raise WorkItemNotFoundError(
            f"Work item {work_item_id!r} not found in package {self.id!r}"
        )

    def get_work_items(self) -> List[WorkItem]:
        """Return a shallow copy of the package's work items."""
        return list(self.work_items)

    def add_artifact(self, artifact_id: str) -> None:
        """Attach an artifact identifier to the work package.

        Args:
            artifact_id: The identifier of the artifact to track.
        """
        validate_required_string(artifact_id, "WorkPackage.artifact_id")
        if artifact_id in self.artifacts:
            raise DuplicateArtifactError(
                f"Artifact {artifact_id!r} is already attached to package {self.id!r}"
            )
        self.artifacts.append(artifact_id)
        self.mark_updated()

    def get_artifact_ids(self) -> List[str]:
        """Return a copy of the attached artifact identifiers."""
        return list(self.artifacts)
