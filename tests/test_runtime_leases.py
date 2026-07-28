from datetime import datetime, timedelta, timezone

import pytest

from runtime.persistence.database import (
    DatabasePersistenceProvider,
    LeaseConflictError,
    LeaseExpiredError,
    StaleFencingTokenError,
)
from runtime.persistence.models import RuntimeCheckpoint


class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def test_lease_exclusion_renewal_expiry_and_fencing(tmp_path):
    clock = Clock()
    provider = DatabasePersistenceProvider(
        tmp_path / "runtime.sqlite3", clock=clock
    )
    first = provider.leases.acquire_lease("runtime", "owner-a", ttl_seconds=10)
    assert "lease_token" not in provider.leases.inspect_lease("runtime")
    with pytest.raises(LeaseConflictError):
        provider.leases.acquire_lease("runtime", "owner-b")

    renewed = provider.leases.renew_lease(first, ttl_seconds=20)
    assert renewed.fencing_token == first.fencing_token
    clock.advance(21)
    with pytest.raises(LeaseExpiredError):
        provider.leases.renew_lease(renewed)
    assert provider.leases.break_expired_lease("runtime")

    second = provider.leases.acquire_lease("runtime", "owner-b")
    assert second.fencing_token > first.fencing_token
    checkpoint = RuntimeCheckpoint.create(
        "cp", "runtime", "lease", 0, {"events": []}
    )
    with pytest.raises(StaleFencingTokenError):
        provider.commit_checkpoint(
            checkpoint, expected_state_version=0, lease=first
        )
    result = provider.commit_checkpoint(
        checkpoint, expected_state_version=0, lease=second
    )
    assert result.state_version == 1
