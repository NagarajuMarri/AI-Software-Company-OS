"""Dispatch one idempotency key twice and apply its result once."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.operations import IdempotencyStore, ResultApplicationService
from runtime.outbox import DeterministicDispatchProvider
from runtime.outbox.models import OutboxOperation, OutboxStatus


def main():
    now = datetime.now(timezone.utc)
    operation = OutboxOperation(
        "idempotent-op", "runtime", "project", "task", "work",
        "CREATE_DRAFT_PULL_REQUEST", "deterministic", "task", 0,
        "stable-key", None, None, {}, 1, OutboxStatus.PENDING, 1, now, now,
    )
    provider = DeterministicDispatchProvider()
    first = provider.dispatch(
        operation.operation_type, {"operation_id": operation.operation_id},
        idempotency_key=operation.idempotency_key,
    )
    second = provider.dispatch(
        operation.operation_type, {"operation_id": operation.operation_id},
        idempotency_key=operation.idempotency_key,
    )
    application = ResultApplicationService(IdempotencyStore())
    application.apply(operation, first)
    application.apply(operation, second)
    print(
        f"provider_dispatches={len(provider.calls)} "
        f"local_applications={len(application.snapshot()['applied'])} "
        f"duplicates_suppressed={application.duplicate_suppressions}"
    )


if __name__ == "__main__":
    main()
