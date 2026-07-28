import pytest

from runtime.outbox.dead_letter import OutboxOperatorService
from runtime.outbox.exceptions import OutboxAuthorizationError
from runtime.outbox.models import OutboxStatus
from runtime.outbox.repository import InMemoryOutboxRepository


def dead(repository, operation_factory):
    operation = repository.add_operation(operation_factory())
    claim = repository.claim_next("worker")
    repository.mark_dispatching(claim)
    repository.mark_dead_letter(claim, "permanent")
    return operation


def test_explicit_dead_letter_retry_is_audited(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    operation = dead(repository, operation_factory)
    operators = OutboxOperatorService(repository)
    operators.retry_dead_letter(operation.operation_id, actor_id="ops", reason="fixed")
    assert operation.status == OutboxStatus.PENDING
    assert operators.audit()[0].action == "RETRY"


def test_operator_identity_and_reason_are_required(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    operation = dead(repository, operation_factory)
    with pytest.raises(OutboxAuthorizationError):
        OutboxOperatorService(repository).retry_dead_letter(
            operation.operation_id, actor_id="", reason=""
        )


def test_corrected_clone_preserves_dead_letter_history(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    operation = dead(repository, operation_factory)
    operators = OutboxOperatorService(repository)
    replacement = operators.clone_corrected(
        operation.operation_id, "replacement", {"branch": "agent/fixed"},
        actor_id="ops", reason="correct payload",
    )
    assert operation.status == OutboxStatus.DEAD_LETTER
    assert replacement.status == OutboxStatus.PENDING
