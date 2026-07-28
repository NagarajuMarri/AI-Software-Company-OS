from dataclasses import dataclass
from datetime import datetime

from runtime.outbox.models import OutboxStatus


@dataclass(frozen=True)
class OutboxMetrics:
    depth: int
    claimed: int
    succeeded: int
    retry: int
    reconciliation_required: int
    dead_letter: int
    oldest_pending_age_seconds: float
    duplicate_result_suppressions: int


def collect_metrics(repository, now, duplicate_suppressions=0):
    values = repository.list_operations()
    pending = [item for item in values if item.status in {OutboxStatus.PENDING, OutboxStatus.RETRY_WAIT}]
    age = max(((now - item.created_at).total_seconds() for item in pending), default=0)
    return OutboxMetrics(
        len(pending), sum(item.status == OutboxStatus.CLAIMED for item in values),
        sum(item.status == OutboxStatus.SUCCEEDED for item in values),
        sum(item.status == OutboxStatus.RETRY_WAIT for item in values),
        sum(item.status == OutboxStatus.RECONCILIATION_REQUIRED for item in values),
        sum(item.status == OutboxStatus.DEAD_LETTER for item in values),
        age, duplicate_suppressions,
    )
