"""Dead-letter exhausted work, then explicitly clone corrected work."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.integrations.github.exceptions import ExternalProviderUnavailableError
from runtime.operations import (
    DeterministicOperationHandler, IdempotencyStore,
    OperationHandlerRegistry, ResultApplicationService,
)
from runtime.outbox import (
    DeterministicDispatchProvider, InMemoryOutboxRepository,
    OutboxOperatorService, OutboxWorker, ProviderRegistry, RetryPolicy,
)
from runtime.outbox.models import OutboxOperation, OutboxStatus


def main():
    clock = lambda: datetime.now(timezone.utc)
    repository = InMemoryOutboxRepository(clock=clock)
    operation = OutboxOperation(
        "failing", "runtime", "project", "task", "work",
        "PUSH_GIT_BRANCH", "deterministic", "task", 0, "failing-key",
        None, None, {}, 1, OutboxStatus.PENDING, 1, clock(), clock(),
        maximum_attempts=1,
    )
    repository.add_operation(operation)
    handlers = OperationHandlerRegistry()
    handlers.register(DeterministicOperationHandler("PUSH_GIT_BRANCH"))
    providers = ProviderRegistry()
    providers.register(DeterministicDispatchProvider(
        outcomes=(ExternalProviderUnavailableError("offline"),)
    ))
    worker = OutboxWorker(
        "worker", repository, handlers, providers,
        ResultApplicationService(IdempotencyStore()), RetryPolicy(),
        clock=clock,
    )
    worker.run_one()
    operators = OutboxOperatorService(repository)
    replacement = operators.clone_corrected(
        operation.operation_id, "corrected", {},
        actor_id="operator", reason="provider restored",
    )
    providers = ProviderRegistry()
    providers.register(DeterministicDispatchProvider())
    worker.providers = providers
    worker.run_one()
    print(
        f"original={operation.status.value} "
        f"replacement={replacement.status.value} "
        f"attempts={len(repository.list_attempts(operation.operation_id))}"
    )


if __name__ == "__main__":
    main()
