from datetime import datetime, timezone

import pytest

from runtime.context.context_manager import ContextManager
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.exceptions import (
    ArtifactNotFoundError,
    DuplicateArtifactError,
    DuplicateWorkItemError,
    DuplicateWorkPackageError,
    InvalidLifecycleTransitionError,
    RuntimeDomainError,
    WorkItemNotFoundError,
    WorkPackageNotFoundError,
)
from runtime.models.artifact import Artifact
from runtime.models.lifecycle import LifecycleState
from runtime.models.work_item import WorkItem
from runtime.models.work_package import WorkPackage
from runtime.storage.artifact_store import ArtifactStore


def test_duplicate_work_package_is_rejected() -> None:
    engine = RuntimeEngine()
    engine.create_work_package("wp-1", "Title", "Description", "owner")

    with pytest.raises(DuplicateWorkPackageError):
        engine.create_work_package("wp-1", "Title 2", "Description 2", "owner")


def test_duplicate_work_item_is_rejected() -> None:
    engine = RuntimeEngine()
    engine.create_work_package("wp-2", "Title", "Description", "owner")

    engine.add_work_item("wp-2", "wi-1", "Item 1", "First item")

    with pytest.raises(DuplicateWorkItemError):
        engine.add_work_item("wp-2", "wi-1", "Item 2", "Dup item")


def test_missing_entities_raise_explicit_errors() -> None:
    engine = RuntimeEngine()

    with pytest.raises(WorkPackageNotFoundError):
        engine.get_work_package("missing")

    engine.create_work_package("wp-3", "Title", "Description", "owner")

    with pytest.raises(WorkItemNotFoundError):
        engine.change_work_item_state("wp-3", "missing", LifecycleState.READY)


def test_invalid_lifecycle_transition_is_rejected() -> None:
    item = WorkItem(id="wi-3", title="Test", description="Test")

    with pytest.raises(InvalidLifecycleTransitionError):
        item.change_state(LifecycleState.REVIEW)


def test_work_package_exposes_safe_collections() -> None:
    package = WorkPackage(id="wp-4", title="Title", description="Description", owner="owner")
    item = WorkItem(id="wi-4", title="Task", description="Task")
    package.add_work_item(item)

    work_items = package.get_work_items()
    work_items.append(WorkItem(id="wi-5", title="Extra", description="Extra"))

    assert len(package.get_work_items()) == 1

    package.add_artifact("artifact-1")
    artifact_ids = package.get_artifact_ids()
    artifact_ids.append("artifact-2")

    assert package.get_artifact_ids() == ["artifact-1"]


def test_context_manager_returns_copies() -> None:
    manager = ContextManager(
        enterprise_context={"tenant": "ascos"},
        project_context={"name": "platform"},
        work_item_context={"title": "work"},
    )

    context = manager.assemble_context()
    context["enterprise_context"]["tenant"] = "changed"

    assert manager.enterprise_context["tenant"] == "ascos"


def test_artifact_store_prevents_internal_mutation() -> None:
    store = ArtifactStore()
    artifact = Artifact(id="art-1", name="spec", type="document", version="1.0")
    store.add_artifact(artifact)

    listed = store.list_artifacts()
    listed.clear()

    assert len(store.list_artifacts()) == 1


def test_artifact_store_missing_artifact_raises_error() -> None:
    store = ArtifactStore()

    with pytest.raises(ArtifactNotFoundError):
        store.get_artifact("missing")


def test_duplicate_artifact_is_rejected() -> None:
    store = ArtifactStore()
    store.add_artifact(Artifact(id="art-2", name="spec", type="document", version="1.0"))

    with pytest.raises(DuplicateArtifactError):
        store.add_artifact(Artifact(id="art-2", name="spec", type="document", version="1.1"))


def test_work_package_updated_at_changes_on_modifications() -> None:
    package = WorkPackage(id="wp-5", title="Title", description="Description", owner="owner")
    initial_timestamp = package.updated_at

    package.add_work_item(WorkItem(id="wi-6", title="Task", description="Task"))

    assert package.updated_at >= initial_timestamp


def test_timestamps_are_timezone_aware() -> None:
    package = WorkPackage(id="wp-6", title="Title", description="Description", owner="owner")
    assert package.created_at.tzinfo is not None
    assert package.updated_at.tzinfo is not None
