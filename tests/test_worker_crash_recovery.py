from runtime.outbox.models import OutboxStatus
from runtime.outbox.repository import InMemoryOutboxRepository


def test_crash_before_claim_keeps_pending(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    assert repository.get_operation("op").status == OutboxStatus.PENDING


def test_crash_after_claim_recovers_after_expiry(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    repository.claim_next("dead-worker", ttl_seconds=1)
    outbox_clock.advance(2)
    repository.recover_expired()
    assert repository.get_operation("op").status == OutboxStatus.PENDING


def test_crash_after_dispatch_requires_reconciliation(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    claim = repository.claim_next("dead-worker", ttl_seconds=1)
    repository.mark_dispatching(claim)
    outbox_clock.advance(2)
    repository.recover_expired()
    assert repository.get_operation("op").status == OutboxStatus.RECONCILIATION_REQUIRED
