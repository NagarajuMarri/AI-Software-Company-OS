import hashlib
import json
from datetime import datetime, timezone

from runtime.outbox.exceptions import IdempotencyConflictError
from runtime.outbox.models import IdempotencyRecord


class IdempotencyStore:
    def __init__(self):
        self._records = {}

    def get(self, key): return self._records.get(key)

    def begin(self, operation):
        fingerprint = operation.request_fingerprint()
        existing = self._records.get(operation.idempotency_key)
        if existing and existing.request_fingerprint != fingerprint:
            raise IdempotencyConflictError("Idempotency fingerprint changed")
        if existing: return existing
        record = IdempotencyRecord(
            operation.idempotency_key, operation.operation_id,
            operation.provider_id, fingerprint, datetime.now(timezone.utc),
            None, None, None, "DISPATCHING",
        )
        self._records[operation.idempotency_key] = record
        return record

    def complete(self, operation, result):
        existing = self.begin(operation)
        fingerprint = hashlib.sha256(json.dumps(
            result.result_payload, sort_keys=True, default=str
        ).encode()).hexdigest()
        if existing.status == "SUCCEEDED":
            if existing.result_fingerprint != fingerprint:
                raise IdempotencyConflictError("Provider result changed")
            return existing, False
        record = IdempotencyRecord(
            existing.idempotency_key, existing.operation_id,
            existing.provider_id, existing.request_fingerprint,
            existing.first_dispatch_at, result.result_reference, fingerprint,
            datetime.now(timezone.utc), "SUCCEEDED",
        )
        self._records[operation.idempotency_key] = record
        return record, True

    def snapshot(self):
        return {
            key: {
                **dict(vars(item)),
                "first_dispatch_at": item.first_dispatch_at.isoformat(),
                "completion_time": (
                    item.completion_time.isoformat()
                    if item.completion_time else None
                ),
            }
            for key, item in self._records.items()
        }

    def restore(self, value):
        self._records = {
            key: IdempotencyRecord(
                **{
                    **item,
                    "first_dispatch_at": datetime.fromisoformat(
                        item["first_dispatch_at"]
                    ),
                    "completion_time": (
                        datetime.fromisoformat(item["completion_time"])
                        if item["completion_time"] else None
                    ),
                }
            )
            for key, item in value.items()
        }
