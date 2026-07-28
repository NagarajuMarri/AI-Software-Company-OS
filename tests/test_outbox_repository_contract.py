import pytest

from runtime.outbox.exceptions import (
    DuplicateOutboxOperationError, IdempotencyConflictError,
)
from runtime.outbox.repository import InMemoryOutboxRepository


def test_add_get_and_queries(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    operation = repository.add_operation(operation_factory())
    assert repository.get_operation(operation.operation_id) is operation
    assert repository.list_by_task("task") == (operation,)
    assert repository.list_by_aggregate("task") == (operation,)


def test_duplicate_operation_is_rejected(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    with pytest.raises(DuplicateOutboxOperationError):
        repository.add_operation(operation_factory())


def test_changed_payload_with_same_idempotency_key_is_rejected(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory("one", idempotency_key="same"))
    with pytest.raises(IdempotencyConflictError):
        repository.add_operation(operation_factory(
            "two", idempotency_key="same", payload={"branch": "different"}
        ))
