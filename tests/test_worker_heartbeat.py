from datetime import datetime, timedelta, timezone

from runtime.workers.heartbeat import HeartbeatService
from runtime.workers.models import WorkerStatus
from runtime.workers.registry import InMemoryWorkerRegistry
from tests.test_worker_registration import registration


def test_heartbeat_advances_expiry():
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo = InMemoryWorkerRegistry(clock=lambda: now[0])
    repo.register(registration())
    now[0] += timedelta(seconds=2)
    HeartbeatService(repo, timeout_seconds=10).record("worker-1")
    assert repo.get("worker-1").heartbeat_expires_at == now[0] + timedelta(seconds=10)


def test_stale_boundary_is_inclusive():
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo = InMemoryWorkerRegistry(clock=lambda: now[0])
    repo.register(registration())
    now[0] += timedelta(seconds=10)
    assert HeartbeatService(repo, timeout_seconds=10).scan_stale()[0].status == WorkerStatus.STALE


def test_active_worker_not_stale():
    repo = InMemoryWorkerRegistry(clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    repo.register(registration())
    assert repo.scan_stale() == ()


def test_stopped_worker_not_marked_stale():
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo = InMemoryWorkerRegistry(clock=lambda: now[0])
    repo.register(registration())
    repo.mark_stopped("worker-1")
    now[0] += timedelta(seconds=20)
    assert repo.scan_stale() == ()


def test_shutdown_request_is_persisted():
    repo = InMemoryWorkerRegistry(clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    repo.register(registration())
    repo.request_shutdown("worker-1")
    assert repo.get("worker-1").shutdown_requested
    assert repo.get("worker-1").status == WorkerStatus.STOPPING
