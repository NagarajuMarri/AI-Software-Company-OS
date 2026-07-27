from datetime import timezone

import pytest

from runtime.engine.runtime_engine import RuntimeEngine
from runtime.exceptions import (
    ArtifactNotFoundError,
    DuplicateArtifactError,
    InvalidLifecycleTransitionError,
    RuntimeDomainError,
    ValidationError,
    WorkItemNotFoundError,
)
from runtime.models.artifact import Artifact
from runtime.models.lifecycle import (
    LifecycleState,
    validate_lifecycle_transition,
)
from runtime.models.work_item import WorkItem
from runtime.models.work_package import WorkPackage
from runtime.storage.artifact_store import ArtifactStore


def test_valid_work_package_creation() -> None:
    package = WorkPackage("wp-1", "Runtime", "Runtime refinement", "platform")

    assert package.id == "wp-1"
    assert package.created_at.tzinfo == timezone.utc
    assert package.updated_at.tzinfo == timezone.utc


@pytest.mark.parametrize(
    ("model", "field_name"),
    [
        (lambda: WorkPackage("", "Title", "Description", "owner"), "WorkPackage.id"),
        (lambda: WorkPackage("wp", " ", "Description", "owner"), "WorkPackage.title"),
        (lambda: WorkPackage("wp", "Title", "\t", "owner"), "WorkPackage.description"),
        (lambda: WorkPackage("wp", "Title", "Description", ""), "WorkPackage.owner"),
        (lambda: WorkItem("", "Title", "Description"), "WorkItem.id"),
        (lambda: WorkItem("wi", " ", "Description"), "WorkItem.title"),
        (lambda: WorkItem("wi", "Title", ""), "WorkItem.description"),
        (lambda: WorkItem("wi", "Title", "Description", priority=" "), "WorkItem.priority"),
        (lambda: Artifact("", "Name", "document", "1"), "Artifact.id"),
        (lambda: Artifact("art", " ", "document", "1"), "Artifact.name"),
        (lambda: Artifact("art", "Name", "", "1"), "Artifact.type"),
        (lambda: Artifact("art", "Name", "document", "\t"), "Artifact.version"),
    ],
)
def test_invalid_mandatory_fields(model: object, field_name: str) -> None:
    with pytest.raises(ValidationError, match=field_name):
        model()


@pytest.mark.parametrize(
    "model",
    [
        lambda: WorkItem("wi", "Title", "Description", assigned_to=" "),
        lambda: Artifact("art", "Name", "document", "1", work_item_id=" "),
    ],
)
def test_optional_strings_are_validated_when_supplied(model: object) -> None:
    with pytest.raises(ValidationError):
        model()


def test_duplicate_attached_artifact_is_rejected() -> None:
    package = WorkPackage("wp", "Title", "Description", "owner")
    package.add_artifact("art")

    with pytest.raises(DuplicateArtifactError):
        package.add_artifact("art")


@pytest.mark.parametrize(
    "states",
    [
        [
            LifecycleState.CREATED,
            LifecycleState.READY,
            LifecycleState.ASSIGNED,
            LifecycleState.RUNNING,
            LifecycleState.REVIEW,
            LifecycleState.APPROVED,
            LifecycleState.COMPLETED,
            LifecycleState.RELEASED,
        ],
        [
            LifecycleState.CREATED,
            LifecycleState.READY,
            LifecycleState.ASSIGNED,
            LifecycleState.RUNNING,
            LifecycleState.REVIEW,
            LifecycleState.REJECTED,
            LifecycleState.RUNNING,
        ],
    ],
)
def test_valid_lifecycle_transitions(states: list[LifecycleState]) -> None:
    item = WorkItem("wi", "Title", "Description")

    for state in states[1:]:
        item.change_state(state)

    assert item.lifecycle_state == states[-1]


def test_artifact_uses_shared_lifecycle_policy() -> None:
    artifact = Artifact("art", "Name", "document", "1")
    artifact.change_state(LifecycleState.READY)

    with pytest.raises(InvalidLifecycleTransitionError):
        artifact.change_state(LifecycleState.COMPLETED)


@pytest.mark.parametrize(
    "target",
    [LifecycleState.CREATED, LifecycleState.RUNNING, LifecycleState.RELEASED],
)
def test_invalid_lifecycle_transitions(target: LifecycleState) -> None:
    item = WorkItem("wi", "Title", "Description")

    with pytest.raises(InvalidLifecycleTransitionError):
        item.change_state(target)


def test_runtime_retrieval_and_list_operations() -> None:
    engine = RuntimeEngine()
    package = engine.create_work_package("wp", "Title", "Description", "owner")
    item = engine.add_work_item("wp", "wi", "Item", "Description")

    assert engine.list_work_packages() == [package]
    assert engine.get_work_item("wp", "wi") is item
    assert package.get_work_item("wi") is item

    with pytest.raises(WorkItemNotFoundError):
        engine.get_work_item("wp", "missing")


def test_artifact_store_list_and_missing_operations() -> None:
    store = ArtifactStore()
    artifact = store.add_artifact(Artifact("art", "Name", "document", "1"))

    assert store.list_artifacts() == [artifact]
    with pytest.raises(ArtifactNotFoundError):
        store.get_artifact("missing")


def test_package_timestamp_changes_for_each_supported_mutation() -> None:
    engine = RuntimeEngine()
    package = engine.create_work_package("wp", "Title", "Description", "owner")
    created = package.updated_at

    engine.add_work_item("wp", "wi", "Item", "Description")
    item_added = package.updated_at
    package.add_artifact("art")
    artifact_added = package.updated_at
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    state_changed = package.updated_at

    assert created < item_added < artifact_added < state_changed


def test_all_specific_exceptions_share_domain_base() -> None:
    assert issubclass(ValidationError, RuntimeDomainError)
    assert issubclass(DuplicateArtifactError, RuntimeDomainError)
    assert issubclass(ArtifactNotFoundError, RuntimeDomainError)
    assert issubclass(InvalidLifecycleTransitionError, RuntimeDomainError)


@pytest.mark.parametrize("invalid_state", ["CREATED", 1, None, object()])
def test_invalid_lifecycle_during_work_item_creation(invalid_state: object) -> None:
    with pytest.raises(ValidationError, match="LifecycleState enum value"):
        WorkItem(
            "wi",
            "Title",
            "Description",
            lifecycle_state=invalid_state,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("invalid_state", ["CREATED", 1, None, object()])
def test_invalid_lifecycle_during_artifact_creation(invalid_state: object) -> None:
    with pytest.raises(ValidationError, match="LifecycleState enum value"):
        Artifact(
            "art",
            "Name",
            "document",
            "1",
            lifecycle_state=invalid_state,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("invalid_state", ["READY", 1, None, object()])
def test_invalid_target_state_passed_to_change_state(invalid_state: object) -> None:
    item = WorkItem("wi", "Title", "Description")

    with pytest.raises(ValidationError, match="LifecycleState enum value"):
        item.change_state(invalid_state)  # type: ignore[arg-type]

    assert item.lifecycle_state == LifecycleState.CREATED


@pytest.mark.parametrize("invalid_state", ["CREATED", 1, None, object()])
def test_invalid_current_state_supplied_to_transition_validator(
    invalid_state: object,
) -> None:
    with pytest.raises(ValidationError, match="LifecycleState enum value"):
        validate_lifecycle_transition(
            invalid_state,  # type: ignore[arg-type]
            LifecycleState.READY,
        )
