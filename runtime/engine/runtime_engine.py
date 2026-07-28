from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from runtime.exceptions import DuplicateWorkPackageError, WorkPackageNotFoundError
from runtime.models.lifecycle import LifecycleState
from runtime.models.work_item import WorkItem
from runtime.models.work_package import WorkPackage

if TYPE_CHECKING:
    from runtime.events.publisher import EventPublisher


class RuntimeEngine:
    """In-memory runtime engine for creating and managing work packages."""

    def __init__(self, event_publisher: EventPublisher | None = None) -> None:
        self._work_packages: Dict[str, WorkPackage] = {}
        self.event_publisher = event_publisher

    def create_work_package(
        self,
        id: str,
        title: str,
        description: str,
        owner: str,
    ) -> WorkPackage:
        """Create and register a new work package.

        Args:
            id: The unique identifier for the work package.
            title: The title of the work package.
            description: The description of the work package.
            owner: The accountable owner of the work package.

        Returns:
            The created work package.
        """
        if id in self._work_packages:
            raise DuplicateWorkPackageError(f"Work package {id!r} already exists")
        package = WorkPackage(id=id, title=title, description=description, owner=owner)
        self._work_packages[id] = package
        self._publish(
            "WORK_PACKAGE_CREATED",
            "WORK_PACKAGE",
            package.id,
            {"title": package.title, "owner": package.owner},
        )
        return package

    def add_work_item(
        self,
        package_id: str,
        id: str,
        title: str,
        description: str,
        priority: str = "normal",
        assigned_to: str | None = None,
    ) -> WorkItem:
        """Add a work item to an existing work package.

        Args:
            package_id: The work package identifier.
            id: The unique identifier for the work item.
            title: The title of the work item.
            description: The description of the work item.
            priority: The priority label for the work item.
            assigned_to: The optional assignee for the work item.

        Returns:
            The created work item.

        Raises:
            WorkPackageNotFoundError: If the specified work package does not exist.
        """
        package = self.get_work_package(package_id)
        item = WorkItem(
            id=id,
            title=title,
            description=description,
            priority=priority,
            assigned_to=assigned_to,
        )
        package.add_work_item(item)
        self._publish(
            "WORK_ITEM_CREATED",
            "WORK_ITEM",
            f"{package_id}:{item.id}",
            {"package_id": package_id, "work_item_id": item.id},
        )
        return item

    def change_work_item_state(self, package_id: str, work_item_id: str, new_state: LifecycleState) -> None:
        """Change the lifecycle state of an existing work item.

        Args:
            package_id: The work package identifier.
            work_item_id: The work item identifier.
            new_state: The target lifecycle state.

        Raises:
            WorkPackageNotFoundError: If the work package does not exist.
            WorkItemNotFoundError: If the work item does not exist.
        """
        package = self.get_work_package(package_id)
        item = package.get_work_item(work_item_id)
        previous_state = item.lifecycle_state
        item.change_state(new_state)
        package.mark_updated()
        self._publish(
            "WORK_ITEM_STATE_CHANGED",
            "WORK_ITEM",
            f"{package_id}:{work_item_id}",
            {
                "package_id": package_id,
                "work_item_id": work_item_id,
                "previous_state": previous_state.value,
                "new_state": new_state.value,
            },
        )

    def get_work_item(self, package_id: str, work_item_id: str) -> WorkItem:
        """Retrieve a work item from a package by identifier."""
        return self.get_work_package(package_id).get_work_item(work_item_id)

    def recover_work_item_state(
        self,
        package_id: str,
        work_item_id: str,
        target_state: LifecycleState,
        reason: str,
    ) -> None:
        """Apply the recovery-only RUNNING to ASSIGNED work-item transition."""
        package = self.get_work_package(package_id)
        item = package.get_work_item(work_item_id)
        previous_state = item.lifecycle_state
        item.recover_state(target_state, reason)
        package.mark_updated()
        self._publish(
            "WORK_ITEM_STATE_CHANGED",
            "WORK_ITEM",
            f"{package_id}:{work_item_id}",
            {
                "package_id": package_id,
                "work_item_id": work_item_id,
                "previous_state": previous_state.value,
                "new_state": target_state.value,
                "recovery": True,
                "reason": reason,
            },
        )

    def list_work_packages(self) -> list[WorkPackage]:
        """Return all work packages in insertion order."""
        return list(self._work_packages.values())

    def get_work_package(self, package_id: str) -> WorkPackage:
        """Retrieve a work package by identifier.

        Args:
            package_id: The work package identifier.

        Returns:
            The requested work package.

        Raises:
            WorkPackageNotFoundError: If the work package does not exist.
        """
        if package_id not in self._work_packages:
            raise WorkPackageNotFoundError(f"Work package {package_id!r} not found")
        return self._work_packages[package_id]

    def _publish(
        self,
        event_name: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
    ) -> None:
        if self.event_publisher is None:
            return
        from runtime.events.types import EventType

        self.event_publisher.publish(
            EventType(event_name),
            aggregate_type,
            aggregate_id,
            payload,
        )
