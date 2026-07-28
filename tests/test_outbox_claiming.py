from runtime.outbox.repository import InMemoryOutboxRepository


def test_deterministic_priority_available_creation_order(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory("later", priority=20))
    repository.add_operation(operation_factory("first", priority=1))
    assert repository.claim_next("worker").operation_id == "first"


def test_only_one_worker_claims_operation(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    assert repository.claim_next("one") is not None
    assert repository.claim_next("two") is None


def test_claim_tokens_are_hashed_at_rest(operation_factory, outbox_clock):
    repository = InMemoryOutboxRepository(clock=outbox_clock)
    repository.add_operation(operation_factory())
    claim = repository.claim_next("worker")
    operation = repository.get_operation("op")
    assert claim.token not in operation.claim_token_hash
    assert len(operation.claim_token_hash) == 64
