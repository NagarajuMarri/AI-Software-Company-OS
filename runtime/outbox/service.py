"""Atomically add outbox intent and its runtime event."""

from datetime import datetime, timezone

from runtime.events.types import EventType
from runtime.outbox.models import OutboxOperation, OutboxStatus
from runtime.transactions.transaction import atomic_domain_operation


class OutboxService:
    def __init__(self, repository, event_publisher=None):
        self.repository = repository
        self.event_publisher = event_publisher
        if event_publisher is not None:
            event_publisher.register_snapshot_provider(
                repository.snapshot_targets
            )

    @atomic_domain_operation
    def create_operation(self, **values):
        now = values.pop("created_at", datetime.now(timezone.utc))
        operation = OutboxOperation(
            status=OutboxStatus.PENDING,
            available_at=values.pop("available_at", now),
            created_at=now,
            **values,
        )
        self.repository.add_operation(operation)
        if self.event_publisher:
            self.event_publisher.publish(
                EventType.OUTBOX_OPERATION_CREATED,
                "outbox-operation",
                operation.operation_id,
                {
                    "operation_type": operation.operation_type,
                    "provider_id": operation.provider_id,
                    "task_id": operation.task_id,
                },
                correlation_id=operation.correlation_id,
                causation_id=operation.causation_id,
            )
        return operation
