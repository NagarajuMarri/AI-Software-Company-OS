import pytest

from runtime.operations import IdempotencyStore, ResultApplicationService
from runtime.operations.handlers import ProviderDispatchResult
from runtime.outbox.exceptions import IdempotencyConflictError


def test_duplicate_result_application_is_suppressed(operation_factory):
    operation = operation_factory()
    result = ProviderDispatchResult(
        operation.operation_id, operation.provider_id, "reference", {"ok": True}
    )
    service = ResultApplicationService(IdempotencyStore())
    assert service.apply(operation, result)[1]
    assert not service.apply(operation, result)[1]
    assert service.duplicate_suppressions == 1


def test_changed_result_for_same_key_is_rejected(operation_factory):
    operation = operation_factory()
    service = ResultApplicationService(IdempotencyStore())
    service.apply(operation, ProviderDispatchResult(
        "op", "deterministic", "one", {"ok": True}
    ))
    with pytest.raises(IdempotencyConflictError):
        service.apply(operation, ProviderDispatchResult(
            "op", "deterministic", "two", {"ok": False}
        ))


def test_provider_remote_idempotency_returns_same_result(operation_factory, worker_factory):
    worker, repository, provider, _ = worker_factory()
    operation = operation_factory()
    first = provider.dispatch(
        operation.operation_type, {"operation_id": operation.operation_id},
        idempotency_key=operation.idempotency_key,
    )
    second = provider.dispatch(
        operation.operation_type, {"operation_id": operation.operation_id},
        idempotency_key=operation.idempotency_key,
    )
    assert first == second and len(provider.calls) == 1
