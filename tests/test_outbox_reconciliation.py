from runtime.outbox.models import OutboxStatus
from runtime.outbox.reconciliation import ReconciliationWorker


def uncertain(repository, operation_factory):
    operation = repository.add_operation(operation_factory())
    claim = repository.claim_next("worker")
    repository.mark_dispatching(claim)
    repository.mark_reconciliation_required(claim, "uncertain")
    return operation


def test_reconciliation_applies_known_provider_result(operation_factory, worker_factory, outbox_clock):
    worker, repository, provider, application = worker_factory()
    operation = uncertain(repository, operation_factory)
    provider.dispatch(
        operation.operation_type, {"operation_id": operation.operation_id},
        idempotency_key=operation.idempotency_key,
    )
    reconciler = ReconciliationWorker(
        "reconciler", repository, worker.providers, application,
        clock=outbox_clock,
    )
    assert reconciler.run_one().status == OutboxStatus.SUCCEEDED


def test_unverifiable_reconciliation_dead_letters(operation_factory, worker_factory, outbox_clock):
    worker, repository, provider, application = worker_factory()
    operation = uncertain(repository, operation_factory)
    from runtime.operations import (
        ProviderReconciliationResult, ProviderReconciliationStatus,
    )
    provider.set_reconciliation_result(
        operation.idempotency_key,
        ProviderReconciliationResult(
            ProviderReconciliationStatus.UNVERIFIABLE
        ),
    )
    reconciler = ReconciliationWorker(
        "reconciler", repository, worker.providers, application,
        clock=outbox_clock,
    )
    assert reconciler.run_one().status == OutboxStatus.DEAD_LETTER


def test_duplicate_reconciliation_has_no_second_operation(operation_factory, worker_factory, outbox_clock):
    worker, repository, provider, application = worker_factory()
    operation = uncertain(repository, operation_factory)
    provider.dispatch(
        operation.operation_type, {"operation_id": operation.operation_id},
        idempotency_key=operation.idempotency_key,
    )
    reconciler = ReconciliationWorker(
        "reconciler", repository, worker.providers, application,
        clock=outbox_clock,
    )
    reconciler.run_one()
    assert reconciler.run_one() is None


def test_provider_not_executed_returns_operation_to_pending(operation_factory, worker_factory, outbox_clock):
    worker, repository, provider, application = worker_factory()
    uncertain(repository, operation_factory)
    reconciler = ReconciliationWorker(
        "reconciler", repository, worker.providers, application,
        clock=outbox_clock,
    )
    assert reconciler.run_one().status == OutboxStatus.PENDING


def test_provider_in_progress_remains_reconciliation_required(operation_factory, worker_factory, outbox_clock):
    from runtime.operations import (
        ProviderReconciliationResult, ProviderReconciliationStatus,
    )
    worker, repository, provider, application = worker_factory()
    operation = uncertain(repository, operation_factory)
    provider.set_reconciliation_result(
        operation.idempotency_key,
        ProviderReconciliationResult(
            ProviderReconciliationStatus.IN_PROGRESS
        ),
    )
    reconciler = ReconciliationWorker(
        "reconciler", repository, worker.providers, application,
        clock=outbox_clock,
    )
    assert reconciler.run_one().status == OutboxStatus.RECONCILIATION_REQUIRED


def test_provider_confirmed_failure_dead_letters(operation_factory, worker_factory, outbox_clock):
    from runtime.operations import (
        ProviderReconciliationResult, ProviderReconciliationStatus,
    )
    worker, repository, provider, application = worker_factory()
    operation = uncertain(repository, operation_factory)
    provider.set_reconciliation_result(
        operation.idempotency_key,
        ProviderReconciliationResult(
            ProviderReconciliationStatus.FAILED,
            failure_code="REMOTE_FAILED",
        ),
    )
    reconciler = ReconciliationWorker(
        "reconciler", repository, worker.providers, application,
        clock=outbox_clock,
    )
    assert reconciler.run_one().status == OutboxStatus.DEAD_LETTER
