"""Authenticated operator controls and immutable audit entries."""

from dataclasses import dataclass
from datetime import datetime, timezone

from runtime.outbox.exceptions import OutboxAuthorizationError
from runtime.outbox.models import OutboxOperation, OutboxStatus, plain


@dataclass(frozen=True)
class OperatorAudit:
    actor_id: str
    operation_id: str
    action: str
    reason: str
    timestamp: datetime


class OutboxOperatorService:
    def __init__(self, repository):
        self.repository = repository
        self._audit = []

    def list_dead_letters(self):
        return self.repository.list_operations(status=OutboxStatus.DEAD_LETTER)

    def retry_dead_letter(self, operation_id, *, actor_id, reason):
        self._authorize(actor_id, reason)
        result = self.repository.retry_dead_letter(operation_id)
        self._record(actor_id, operation_id, "RETRY", reason)
        return result

    def abandon(self, operation_id, *, actor_id, reason):
        self._authorize(actor_id, reason)
        operation = self.repository.abandon_operation(operation_id, reason)
        self._record(actor_id, operation_id, "ABANDON", reason)
        return operation

    def clone_corrected(
        self, operation_id, replacement_id, payload,
        *, actor_id, reason,
    ):
        self._authorize(actor_id, reason)
        source = self.repository.get_operation(operation_id)
        replacement = OutboxOperation(
            replacement_id, source.runtime_id, source.project_id,
            source.task_id, source.work_item_id, source.operation_type,
            source.provider_id, source.aggregate_id, source.aggregate_version,
            f"{source.idempotency_key}:replacement:{replacement_id}",
            source.correlation_id, source.causation_id, payload,
            source.payload_schema_version, OutboxStatus.PENDING,
            source.priority, self.repository.clock(), self.repository.clock(),
            maximum_attempts=source.maximum_attempts,
        )
        self.repository.add_operation(replacement)
        self._record(actor_id, operation_id, "CLONE", reason)
        return replacement

    def pause_provider(self, provider_id, *, actor_id, reason):
        self._authorize(actor_id, reason)
        self.repository.pause_provider(provider_id)
        self._record(actor_id, provider_id, "PAUSE_PROVIDER", reason)

    def resume_provider(self, provider_id, *, actor_id, reason):
        self._authorize(actor_id, reason)
        self.repository.resume_provider(provider_id)
        self._record(actor_id, provider_id, "RESUME_PROVIDER", reason)

    def audit(self): return tuple(self._audit)

    @staticmethod
    def _authorize(actor_id, reason):
        if not actor_id or not reason:
            raise OutboxAuthorizationError(
                "Operator identity and reason are required"
            )

    def _record(self, actor, operation, action, reason):
        self._audit.append(OperatorAudit(
            actor, operation, action, reason, datetime.now(timezone.utc)
        ))
