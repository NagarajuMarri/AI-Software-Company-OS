"""Recover an uncertain dispatch through provider reconciliation."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.operations import (
    IdempotencyStore, ResultApplicationService,
)
from runtime.outbox import (
    DeterministicDispatchProvider, InMemoryOutboxRepository,
    ProviderRegistry,
)
from runtime.outbox.models import OutboxOperation, OutboxStatus
from runtime.outbox.reconciliation import ReconciliationWorker


def main():
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    clock = lambda: now[0]
    repository = InMemoryOutboxRepository(clock=clock)
    operation = OutboxOperation(
        "crash-op", "runtime", "project", "task", "work",
        "CREATE_DRAFT_PULL_REQUEST", "deterministic", "task", 0,
        "crash-key", "corr", None, {}, 1, OutboxStatus.PENDING, 1,
        clock(), clock(),
    )
    repository.add_operation(operation)
    claim = repository.claim_next("crashed-worker", ttl_seconds=1)
    repository.mark_dispatching(claim)
    provider = DeterministicDispatchProvider()
    provider.dispatch(
        operation.operation_type, {"operation_id": operation.operation_id},
        idempotency_key=operation.idempotency_key,
    )
    now[0] += timedelta(seconds=2)
    repository.recover_expired()
    providers = ProviderRegistry()
    providers.register(provider)
    application = ResultApplicationService(IdempotencyStore())
    ReconciliationWorker(
        "reconciler", repository, providers, application, clock=clock
    ).run_one()
    print(
        f"status={operation.status.value} "
        f"applications={len(application.snapshot()['applied'])}"
    )


if __name__ == "__main__":
    main()
