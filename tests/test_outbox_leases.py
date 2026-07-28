import pytest

from runtime.outbox.exceptions import (
    OutboxClaimExpiredError, OutboxClaimError,
)
from runtime.outbox.models import OutboxClaim
from runtime.outbox.repository import InMemoryOutboxRepository


def test_claim_renewal_and_release(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    claim = repository.claim_next("worker", ttl_seconds=10)
    renewed = repository.renew_claim(claim, ttl_seconds=20)
    repository.release_claim(renewed)
    assert repository.claim_next("other").fencing_token == 2


def test_expired_claim_cannot_dispatch(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    claim = repository.claim_next("worker", ttl_seconds=1)
    outbox_clock.advance(2)
    with pytest.raises(OutboxClaimExpiredError):
        repository.mark_dispatching(claim)


def test_forged_claim_identity_is_rejected(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    claim = repository.claim_next("worker")
    forged = OutboxClaim(
        claim.operation_id, claim.owner_id, "wrong", claim.claimed_at,
        claim.expires_at, claim.fencing_token,
    )
    with pytest.raises(OutboxClaimError):
        repository.mark_dispatching(forged)
