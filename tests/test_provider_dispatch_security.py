import pytest

from runtime.operations import DeterministicOperationHandler
from runtime.operations.exceptions import ForgedProviderResultError
from runtime.operations.handlers import ProviderDispatchResult
from runtime.outbox.exceptions import OutboxValidationError


def test_forged_provider_result_is_rejected(operation_factory):
    operation = operation_factory()
    class Forged:
        def dispatch(self, *args, **kwargs):
            return ProviderDispatchResult("other", "deterministic", "ref", {})
    with pytest.raises(ForgedProviderResultError):
        DeterministicOperationHandler(
            "CREATE_GIT_BRANCH"
        ).dispatch(Forged(), operation)


def test_claim_token_never_appears_in_attempt_history(operation_factory, worker_factory):
    worker, repository, _, _ = worker_factory()
    repository.add_operation(operation_factory())
    worker.run_one()
    text = repr(repository.list_attempts("op"))
    assert "token" not in text.lower()


def test_provider_identifier_allowlist_rejects_injection(operation_factory):
    with pytest.raises(OutboxValidationError):
        operation_factory(provider_id="provider;rm")


def test_oversized_provider_result_is_rejected(operation_factory):
    operation = operation_factory()
    class Oversized:
        def dispatch(self, *args, **kwargs):
            return ProviderDispatchResult(
                "op", "deterministic", "reference",
                {"value": "x" * 40_000},
            )
    with pytest.raises(Exception, match="size"):
        DeterministicOperationHandler(
            "CREATE_GIT_BRANCH"
        ).dispatch(Oversized(), operation)
