from datetime import datetime, timedelta, timezone
import pytest

from runtime.providers.health.circuit_breaker import CircuitBreaker
from runtime.providers.health.exceptions import (
    OperatorAuthorizationError, ProviderHealthVersionConflictError,
    ProviderUnavailableError,
)
from runtime.providers.health.models import ProviderHealthState, ProviderHealthStatus
from runtime.providers.health.repository import (
    FileProviderHealthRepository, InMemoryProviderHealthRepository,
    SQLiteProviderHealthRepository,
)
from runtime.providers.health.routing import ProviderRoute, ProviderRouter
from runtime.providers.health.service import ProviderHealthService

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def state(provider="a", status=ProviderHealthStatus.UNKNOWN, maximum=2):
    return ProviderHealthState(
        provider, "coding", status, 0, 0, None, None, None, None,
        None, 0, 0, maximum, NOW,
    )


def breaker(repo, clock=lambda: NOW, failures=2):
    return CircuitBreaker(repo, clock=clock, failure_threshold=failures, open_seconds=10)


@pytest.mark.parametrize("status", list(ProviderHealthStatus))
def test_health_status_round_trip(status):
    repo = InMemoryProviderHealthRepository()
    repo.add(state(status=status))
    assert repo.get("a", "coding").status == status


def test_invalid_negative_inflight():
    item = state()
    item.current_in_flight = -1
    with pytest.raises(ValueError): item.__post_init__()


def test_failure_degrades_then_opens():
    repo = InMemoryProviderHealthRepository(); repo.add(state())
    cb = breaker(repo)
    cb.failure("a", "coding", category="UNAVAILABLE", code="E1")
    assert repo.get("a", "coding").status == ProviderHealthStatus.DEGRADED
    cb.failure("a", "coding", category="UNAVAILABLE", code="E2")
    assert repo.get("a", "coding").status == ProviderHealthStatus.OPEN


def test_open_rejects_dispatch():
    repo = InMemoryProviderHealthRepository(); repo.add(state(status=ProviderHealthStatus.OPEN))
    repo.get("a", "coding").open_until = NOW + timedelta(seconds=1)
    with pytest.raises(ProviderUnavailableError): breaker(repo).allow("a", "coding")


def test_expired_open_enters_half_open():
    now = [NOW]
    item = state(status=ProviderHealthStatus.OPEN)
    item.open_until = NOW
    repo = InMemoryProviderHealthRepository(); repo.add(item)
    breaker(repo, clock=lambda: now[0]).allow("a", "coding")
    assert repo.get("a", "coding").status == ProviderHealthStatus.HALF_OPEN


def test_half_open_success_closes():
    item = state(status=ProviderHealthStatus.HALF_OPEN)
    item.current_in_flight = 1
    repo = InMemoryProviderHealthRepository(); repo.add(item)
    breaker(repo).success("a", "coding")
    assert repo.get("a", "coding").status == ProviderHealthStatus.HEALTHY


def test_saturated_provider_rejected():
    item = state(maximum=1); item.current_in_flight = 1
    repo = InMemoryProviderHealthRepository(); repo.add(item)
    with pytest.raises(ProviderUnavailableError): breaker(repo).allow("a", "coding")


def test_inflight_never_negative():
    repo = InMemoryProviderHealthRepository(); repo.add(state())
    breaker(repo).success("a", "coding")
    assert repo.get("a", "coding").current_in_flight == 0


def test_repository_version_conflict():
    repo = InMemoryProviderHealthRepository(); item = repo.add(state())
    repo.save(item, expected_version=0)
    with pytest.raises(ProviderHealthVersionConflictError):
        repo.save(item, expected_version=0)


@pytest.mark.parametrize("kind", ["file", "sqlite"])
def test_health_persistence(tmp_path, kind):
    cls = FileProviderHealthRepository if kind == "file" else SQLiteProviderHealthRepository
    path = tmp_path / ("health.json" if kind == "file" else "health.db")
    repo = cls(path); repo.add(state(status=ProviderHealthStatus.OPEN))
    assert cls(path).get("a", "coding").status == ProviderHealthStatus.OPEN


def test_router_uses_priority_then_id():
    repo = InMemoryProviderHealthRepository()
    repo.add(state("a")); repo.add(state("b"))
    router = ProviderRouter(repo, [ProviderRoute("b", "coding", 1), ProviderRoute("a", "coding", 1)])
    assert router.select("coding").provider_id == "a"


def test_router_honours_affinity():
    repo = InMemoryProviderHealthRepository()
    repo.add(state("a")); repo.add(state("b"))
    router = ProviderRouter(repo, [ProviderRoute("a", "coding"), ProviderRoute("b", "coding")])
    assert router.select("coding", affinity_provider_id="b").provider_id == "b"


def test_router_rejects_open_and_disabled():
    repo = InMemoryProviderHealthRepository()
    repo.add(state("a", ProviderHealthStatus.OPEN))
    repo.add(state("b", ProviderHealthStatus.DISABLED))
    router = ProviderRouter(repo, [ProviderRoute("a", "coding"), ProviderRoute("b", "coding")])
    with pytest.raises(ProviderUnavailableError): router.select("coding")


def test_operator_disable_is_audited():
    repo = InMemoryProviderHealthRepository(); repo.add(state())
    audit = []
    ProviderHealthService(repo, clock=lambda: NOW, audit=audit).disable(
        "a", "coding", actor="operator", reason="maintenance"
    )
    assert audit[0]["action"] == "DISABLE"


@pytest.mark.parametrize("actor,reason", [("", "why"), ("operator", "")])
def test_operator_identity_and_reason_required(actor, reason):
    repo = InMemoryProviderHealthRepository(); repo.add(state())
    with pytest.raises(OperatorAuthorizationError):
        ProviderHealthService(repo, clock=lambda: NOW).disable(
            "a", "coding", actor=actor, reason=reason
        )
