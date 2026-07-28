import pytest

from runtime.composition import create_runtime_container
from runtime.exceptions import TransactionCommitError


def values():
    return dict(
        operation_id="op", runtime_id="runtime", project_id="project",
        task_id="task", work_item_id="work",
        operation_type="CREATE_GIT_BRANCH", provider_id="deterministic",
        aggregate_id="task", aggregate_version=0, idempotency_key="key",
        correlation_id="corr", causation_id=None, payload={},
        payload_schema_version=1, priority=1, maximum_attempts=3,
    )


def test_outbox_and_event_commit_atomically():
    container = create_runtime_container()
    container.outbox_service.create_operation(**values())
    assert len(container.outbox_repository.list_operations()) == 1
    assert len(container.event_store.list_events()) == 1


def test_event_failure_rolls_back_outbox():
    container = create_runtime_container()
    def fail(events): raise RuntimeError("storage")
    container.event_store.add_events = fail
    with pytest.raises(TransactionCommitError):
        container.outbox_service.create_operation(**values())
    assert container.outbox_repository.list_operations() == ()
    assert container.event_store.list_events() == []


def test_validation_failure_stores_neither_intent_nor_event():
    container = create_runtime_container()
    invalid = values()
    invalid["payload"] = {"api_token": "secret"}
    with pytest.raises(Exception):
        container.outbox_service.create_operation(**invalid)
    assert not container.outbox_repository.list_operations()
    assert not container.event_store.list_events()
