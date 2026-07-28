from runtime.integrations.github.exceptions import (
    GitHubAuthenticationError, GitHubRateLimitError,
)
from runtime.outbox.dispatcher import DeterministicDispatchProvider
from runtime.outbox.models import OutboxStatus
from runtime.outbox.retry import RetryPolicy


def test_authentication_failure_is_dead_lettered(operation_factory, worker_factory):
    worker, repository, _, _ = worker_factory(
        provider=DeterministicDispatchProvider(
            outcomes=(GitHubAuthenticationError("bad token"),)
        )
    )
    repository.add_operation(operation_factory())
    assert worker.run_one().status == OutboxStatus.DEAD_LETTER


def test_rate_limit_uses_retry_schedule(operation_factory, worker_factory):
    worker, repository, _, _ = worker_factory(
        provider=DeterministicDispatchProvider(
            outcomes=(GitHubRateLimitError("limited"),)
        )
    )
    repository.add_operation(operation_factory())
    result = worker.run_one()
    assert result.status == OutboxStatus.RETRY_WAIT
    assert result.available_at > result.created_at


def test_maximum_attempts_dead_letters(operation_factory, worker_factory, outbox_clock):
    provider = DeterministicDispatchProvider(
        outcomes=(
            __import__("runtime.integrations.github.exceptions", fromlist=["ExternalProviderUnavailableError"]).ExternalProviderUnavailableError("x"),
        )
    )
    worker, repository, _, _ = worker_factory(provider=provider)
    repository.add_operation(operation_factory(maximum_attempts=1))
    assert worker.run_one().status == OutboxStatus.DEAD_LETTER
