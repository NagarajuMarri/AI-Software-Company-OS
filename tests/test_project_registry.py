import json

import pytest

from runtime.composition.factory import create_runtime_container
from runtime.events import EventType
from runtime.exceptions import DuplicateProjectError, ProjectNotFoundError, ValidationError
from runtime.projects import (
    FileProjectRegistry,
    InMemoryProjectRegistry,
    ManagedProject,
    ProjectLifecycle,
    ProjectRegistryCorruptError,
    register_spoken_english_ai,
)


def project(project_id="product", repository_url="https://example.com/product"):
    return ManagedProject(
        project_id, "Product", "A managed product", repository_url, "main",
        tags=("example",),
    )


def test_registry_registers_and_discovers_deterministically():
    registry = InMemoryProjectRegistry()
    later = registry.register(project("z-product", "https://example.com/z"))
    earlier = registry.register(project("a-product", "https://example.com/a.git"))
    assert registry.list_projects() == (earlier, later)
    assert registry.get(later.project_id) is later
    assert registry.find_by_repository("HTTPS://EXAMPLE.COM/A/") is earlier


def test_registry_rejects_duplicate_identity_and_repository():
    registry = InMemoryProjectRegistry((project(),))
    with pytest.raises(DuplicateProjectError):
        registry.register(project())
    with pytest.raises(DuplicateProjectError):
        registry.register(project("other", "https://example.com/product.git"))


def test_registry_reports_missing_and_invalid_lookups():
    registry = InMemoryProjectRegistry()
    with pytest.raises(ProjectNotFoundError):
        registry.get("missing")
    with pytest.raises(ProjectNotFoundError):
        registry.find_by_repository("https://example.com/missing")
    with pytest.raises(ValidationError):
        registry.get("")


def test_project_validation_and_lifecycle_filtering():
    paused = ManagedProject(
        "paused", "Paused", "Paused product", "https://example.com/paused", "main",
        lifecycle=ProjectLifecycle.PAUSED,
    )
    registry = InMemoryProjectRegistry((project(), paused))
    assert registry.list_projects(ProjectLifecycle.PAUSED) == (paused,)
    with pytest.raises(ValidationError):
        project(repository_url="file:///unsafe")
    with pytest.raises(ValidationError):
        ManagedProject(
            "bad", "Bad", "Bad tags", "https://example.com/bad", "main",
            tags=("duplicate", "duplicate"),
        )


def test_file_registry_is_versioned_and_restart_safe(tmp_path):
    path = tmp_path / "registry" / "projects.json"
    registered = FileProjectRegistry(path).register(project())
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert not list(path.parent.glob("*.tmp"))
    assert FileProjectRegistry(path).get("product") == registered


def test_file_registry_rejects_corrupt_or_unknown_schema(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text('{"schema_version": 999, "projects": []}', encoding="utf-8")
    with pytest.raises(ProjectRegistryCorruptError):
        FileProjectRegistry(path)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ProjectRegistryCorruptError):
        FileProjectRegistry(path)


def test_registration_publishes_event_and_container_isolation():
    first = create_runtime_container()
    second = create_runtime_container()
    managed = first.project_registry.register(project())
    assert second.project_registry.list_projects() == ()
    event = first.event_store.list_events()[0]
    assert event.event_type == EventType.PROJECT_REGISTERED
    assert event.aggregate_id == managed.project_id


def test_first_managed_product_registration_is_portable():
    managed = register_spoken_english_ai(InMemoryProjectRegistry())
    assert managed.project_id == "spoken-english-ai"
    assert managed.local_path is None
