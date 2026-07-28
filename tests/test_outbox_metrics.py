from runtime.outbox.metrics import collect_metrics
from runtime.outbox.repository import InMemoryOutboxRepository


def test_metrics_report_backlog_and_age(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    outbox_clock.advance(10)
    metrics = collect_metrics(repository, outbox_clock())
    assert metrics.depth == 1
    assert metrics.oldest_pending_age_seconds == 10


def test_metrics_report_success(operation_factory, worker_factory, outbox_clock):
    worker, repository, _, application = worker_factory()
    repository.add_operation(operation_factory())
    worker.run_one()
    assert collect_metrics(
        repository, outbox_clock(),
        application.duplicate_suppressions,
    ).succeeded == 1


def test_metrics_never_include_payload(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory(payload={"value": "private"}))
    assert "private" not in repr(collect_metrics(repository, outbox_clock()))
