from datetime import datetime, timedelta, timezone
import pytest

from runtime.workers.models import WorkerConfiguration, WorkerRegistration, WorkerStatus
from runtime.workers.registry import (
    DuplicateWorkerInstanceError, FileWorkerRegistry,
    InMemoryWorkerRegistry, SQLiteWorkerRegistry, WorkerVersionConflictError,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def registration(instance="worker-1"):
    return WorkerRegistration(
        "worker", instance, 42, "node", "runtime", "OUTBOX",
        ("DISPATCH",), ("coding",), WorkerStatus.STARTING,
        NOW, NOW, NOW, NOW + timedelta(seconds=10),
    )


def test_registration_round_trip():
    repo = InMemoryWorkerRegistry(clock=lambda: NOW)
    assert repo.register(registration()).worker_instance_id == "worker-1"


def test_duplicate_instance_rejected():
    repo = InMemoryWorkerRegistry(clock=lambda: NOW)
    repo.register(registration())
    with pytest.raises(DuplicateWorkerInstanceError): repo.register(registration())


def test_restart_uses_distinct_instance():
    repo = InMemoryWorkerRegistry(clock=lambda: NOW)
    repo.register(registration("worker-1"))
    repo.register(registration("worker-2"))
    assert len(repo.list()) == 2


@pytest.mark.parametrize("value", ["bad space", "x@y", ""])
def test_unsafe_worker_identity_rejected(value):
    with pytest.raises(ValueError): registration(value)


def test_naive_timestamp_rejected():
    item = registration()
    item.started_at = datetime(2026, 1, 1)
    with pytest.raises(ValueError): item.__post_init__()


def test_configuration_rejects_secret_reference():
    with pytest.raises(ValueError):
        WorkerConfiguration("runtime", "worker", "postgres://u:p@host/db", ("X",), ("p",))


@pytest.mark.parametrize("heartbeat,timeout", [(0, 5), (5, 5), (6, 5)])
def test_configuration_heartbeat_relationship(heartbeat, timeout):
    with pytest.raises(ValueError):
        WorkerConfiguration(
            "runtime", "worker", "database-ref", ("X",), ("p",),
            heartbeat_interval_seconds=heartbeat, heartbeat_timeout_seconds=timeout,
        )


def test_optimistic_status_update():
    repo = InMemoryWorkerRegistry(clock=lambda: NOW)
    repo.register(registration())
    repo.update_status("worker-1", WorkerStatus.IDLE, expected_version=0)
    with pytest.raises(WorkerVersionConflictError):
        repo.update_status("worker-1", WorkerStatus.IDLE, expected_version=0)


@pytest.mark.parametrize("kind", ["file", "sqlite"])
def test_durable_worker_registry_round_trip(tmp_path, kind):
    cls = FileWorkerRegistry if kind == "file" else SQLiteWorkerRegistry
    path = tmp_path / ("workers.json" if kind == "file" else "workers.db")
    repo = cls(path, clock=lambda: NOW)
    repo.register(registration())
    assert cls(path, clock=lambda: NOW).get("worker-1").status == WorkerStatus.STARTING
