"""Idempotent local result application."""


class ResultApplicationService:
    def __init__(self, idempotency_store, *, event_publisher=None):
        self.idempotency_store = idempotency_store
        self.event_publisher = event_publisher
        self._applied = {}
        self._aggregate_versions = {}
        self.duplicate_suppressions = 0

    def snapshot_targets(self):
        return [
            self,
            self._applied,
            self._aggregate_versions,
            self.idempotency_store._records,
        ]

    def apply(self, operation, result):
        existing = self.idempotency_store.get(operation.idempotency_key)
        if existing is not None and existing.status == "SUCCEEDED":
            record, first = self.idempotency_store.complete(operation, result)
            self.duplicate_suppressions += 1
            return self._applied.get(operation.idempotency_key), False
        aggregate_key = (
            f"{len(operation.runtime_id)}:{operation.runtime_id}:"
            f"{operation.aggregate_id}"
        )
        current_version = self._aggregate_versions.get(aggregate_key, 0)
        if current_version != operation.aggregate_version:
            raise ValueError("Aggregate version is stale")
        record, first = self.idempotency_store.complete(operation, result)
        if not first:
            self.duplicate_suppressions += 1
            return self._applied.get(operation.idempotency_key), False
        value = {
            "operation_id": operation.operation_id,
            "aggregate_id": operation.aggregate_id,
            "aggregate_version": operation.aggregate_version,
            "result_reference": result.result_reference,
            "result": dict(result.result_payload),
        }
        self._applied[operation.idempotency_key] = value
        self._aggregate_versions[aggregate_key] = (
            operation.aggregate_version + 1
        )
        return value, True

    def snapshot(self):
        return {
            "applied": dict(self._applied),
            "idempotency": self.idempotency_store.snapshot(),
            "duplicate_suppressions": self.duplicate_suppressions,
            "aggregate_versions": dict(self._aggregate_versions),
        }

    def restore(self, value):
        self._applied = dict(value.get("applied", {}))
        self.idempotency_store.restore(value.get("idempotency", {}))
        self.duplicate_suppressions = value.get("duplicate_suppressions", 0)
        self._aggregate_versions = dict(value.get("aggregate_versions", {}))
