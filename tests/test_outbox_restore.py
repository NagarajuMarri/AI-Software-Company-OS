from runtime.outbox.models import OutboxStatus
from runtime.outbox.providers.file import FileOutboxRepository


def test_file_repository_restart_preserves_pending(operation_factory, outbox_clock, tmp_path):
    path = tmp_path / "outbox.json"
    first = FileOutboxRepository(path, clock=outbox_clock)
    first.add_operation(operation_factory())
    second = FileOutboxRepository(path, clock=outbox_clock)
    assert second.get_operation("op").status == OutboxStatus.PENDING


def test_file_restart_recovers_expired_claim(operation_factory, outbox_clock, tmp_path):
    path = tmp_path / "outbox.json"
    first = FileOutboxRepository(path, clock=outbox_clock)
    first.add_operation(operation_factory())
    first.claim_next("worker", ttl_seconds=1)
    outbox_clock.advance(2)
    second = FileOutboxRepository(path, clock=outbox_clock)
    assert second.get_operation("op").status == OutboxStatus.PENDING


def test_file_restart_marks_expired_dispatch_uncertain(operation_factory, outbox_clock, tmp_path):
    path = tmp_path / "outbox.json"
    first = FileOutboxRepository(path, clock=outbox_clock)
    first.add_operation(operation_factory())
    claim = first.claim_next("worker", ttl_seconds=1)
    first.mark_dispatching(claim)
    outbox_clock.advance(2)
    second = FileOutboxRepository(path, clock=outbox_clock)
    assert second.get_operation("op").status == OutboxStatus.RECONCILIATION_REQUIRED
