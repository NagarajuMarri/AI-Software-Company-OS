"""Dispatch one durable operation and prove restart does not duplicate it."""

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.composition import create_runtime_container
from runtime.operations import DeterministicOperationHandler
from runtime.outbox import (
    DeterministicDispatchProvider, OutboxWorker, RetryPolicy,
)
from runtime.persistence import FilePersistenceProvider


def operation(service):
    return service.create_operation(
        operation_id="branch-op", runtime_id="runtime", project_id="project",
        task_id="task", work_item_id="work",
        operation_type="CREATE_GIT_BRANCH", provider_id="deterministic",
        aggregate_id="task", aggregate_version=0,
        idempotency_key="branch-key", correlation_id="corr",
        causation_id=None, payload={"branch": "agent/outbox"},
        payload_schema_version=1, priority=1, maximum_attempts=3,
    )


def main():
    with tempfile.TemporaryDirectory() as directory:
        persistence = FilePersistenceProvider(directory)
        runtime = create_runtime_container(
            persistence_enabled=True, persistence_provider=persistence,
            runtime_id="outbox-example",
        )
        provider = runtime.dispatch_provider_registry.register(
            DeterministicDispatchProvider()
        )
        created = operation(runtime.outbox_service)
        worker = OutboxWorker(
            "worker", runtime.outbox_repository,
            runtime.operation_handler_registry,
            runtime.dispatch_provider_registry,
            runtime.result_application_service, RetryPolicy(),
            clock=lambda: datetime.now(timezone.utc),
        )
        worker.run_one()
        checkpoint = runtime.persistence_service.save_checkpoint("outbox")
        restarted = create_runtime_container(
            persistence_enabled=True, persistence_provider=persistence,
            runtime_id="outbox-example",
        )
        restarted.persistence_service.restore_runtime(checkpoint)
        print(
            f"operation={restarted.outbox_repository.get_operation(created.operation_id).status.value} "
            f"dispatches={len(provider.calls)} "
            f"events={len(restarted.event_store.list_events())}"
        )


if __name__ == "__main__":
    main()
