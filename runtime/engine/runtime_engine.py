from __future__ import annotations

from typing import Dict

from runtime.models.lifecycle import LifecycleState
from runtime.models.work_item import WorkItem
from runtime.models.work_package import WorkPackage


class RuntimeEngine:
    """In-memory runtime engine for creating and managing work packages."""

    def __init__(self) -> None:
        self._work_packages: Dict[str, WorkPackage] = {}

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
        package = WorkPackage(id=id, title=title, description=description, owner=owner)
        self._work_packages[id] = package
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
            KeyError: If the specified work package does not exist.
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
        return item

    def change_work_item_state(self, package_id: str, work_item_id: str, new_state: LifecycleState) -> None:
        """Change the lifecycle state of an existing work item.

        Args:
            package_id: The work package identifier.
            work_item_id: The work item identifier.
            new_state: The target lifecycle state.

        Raises:
            KeyError: If the work package or work item does not exist.
        """
        package = self.get_work_package(package_id)
        for item in package.work_items:
            if item.id == work_item_id:
                item.change_state(new_state)
                return
        raise KeyError(f"Work item {work_item_id} not found")

    def get_work_package(self, package_id: str) -> WorkPackage:
        """Retrieve a work package by identifier.

        Args:
            package_id: The work package identifier.

        Returns:
            The requested work package.

        Raises:
            KeyError: If the work package does not exist.
        """
        if package_id not in self._work_packages:
            raise KeyError(f"Work package {package_id} not found")
        return self._work_packages[package_id]
