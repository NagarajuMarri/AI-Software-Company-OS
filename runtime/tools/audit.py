"""Bounded side-effect audit records."""

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType


@dataclass(frozen=True)
class AuditRecord:
    action: str
    target: str
    outcome: str
    timestamp: datetime
    details: object


class AuditLog:
    def __init__(self) -> None:
        self._records = []

    def record(self, action, target, outcome, details=None):
        record = AuditRecord(
            action, target, outcome, datetime.now(timezone.utc),
            MappingProxyType(dict(details or {})),
        )
        self._records.append(record)
        return record

    def list_records(self):
        return tuple(self._records)
