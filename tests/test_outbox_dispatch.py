from runtime.integrations.github.exceptions import ExternalProviderUnavailableError
from runtime.outbox.dispatcher import DeterministicDispatchProvider
from runtime.outbox.models import OutboxStatus


def test_worker_dispatch_success(operation_factory, worker_factory):
    worker, repository, provider, application = worker_factory()
    repository.add_operation(operation_factory())
    result = worker.run_one()
    assert result.status == OutboxStatus.SUCCEEDED
    assert len(provider.calls) == 1
    assert application.snapshot()["applied"]


def test_provider_unavailable_schedules_retry(operation_factory, worker_factory):
    provider = DeterministicDispatchProvider(
        outcomes=(ExternalProviderUnavailableError("offline"),)
    )
    worker, repository, _, _ = worker_factory(provider=provider)
    repository.add_operation(operation_factory())
    assert worker.run_one().status == OutboxStatus.RETRY_WAIT


def test_provider_timeout_requires_reconciliation(operation_factory, worker_factory):
    provider = DeterministicDispatchProvider(outcomes=(TimeoutError(),))
    worker, repository, _, _ = worker_factory(provider=provider)
    repository.add_operation(operation_factory())
    assert worker.run_one().status == OutboxStatus.RECONCILIATION_REQUIRED
