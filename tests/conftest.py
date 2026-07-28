from datetime import datetime, timedelta, timezone

import pytest

from runtime.operations import (
    DeterministicOperationHandler, IdempotencyStore,
    OperationHandlerRegistry, ResultApplicationService,
)
from runtime.outbox import (
    DeterministicDispatchProvider, InMemoryOutboxRepository,
    ProviderRegistry, RetryPolicy,
)
from runtime.outbox.models import OutboxOperation, OutboxStatus
from runtime.outbox.worker import OutboxWorker


class TestClock:
    def __init__(self):
        self.value = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def __call__(self): return self.value
    def advance(self, seconds): self.value += timedelta(seconds=seconds)


@pytest.fixture
def outbox_clock():
    return TestClock()


@pytest.fixture
def operation_factory(outbox_clock):
    def create(identifier="op", **overrides):
        values = dict(
            operation_id=identifier, runtime_id="runtime",
            project_id="project", task_id="task", work_item_id="work",
            operation_type="CREATE_GIT_BRANCH", provider_id="deterministic",
            aggregate_id="task", aggregate_version=0,
            idempotency_key=f"key-{identifier}", correlation_id="corr",
            causation_id=None, payload={"branch": "agent/task"},
            payload_schema_version=1, status=OutboxStatus.PENDING,
            priority=10, available_at=outbox_clock(),
            created_at=outbox_clock(), maximum_attempts=3,
        )
        values.update(overrides)
        return OutboxOperation(**values)
    return create


@pytest.fixture
def worker_factory(outbox_clock):
    def create(repository=None, provider=None, handler=None):
        repository = repository or InMemoryOutboxRepository(clock=outbox_clock)
        handlers = OperationHandlerRegistry()
        handlers.register(handler or DeterministicOperationHandler(
            "CREATE_GIT_BRANCH"
        ))
        providers = ProviderRegistry()
        provider = providers.register(
            provider or DeterministicDispatchProvider()
        )
        application = ResultApplicationService(IdempotencyStore())
        worker = OutboxWorker(
            "worker", repository, handlers, providers, application,
            RetryPolicy(), clock=outbox_clock,
        )
        return worker, repository, provider, application
    return create
