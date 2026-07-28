"""SQLite-backed outbox with serialized atomic repository mutations."""

import json
import sqlite3
from pathlib import Path

from runtime.outbox.providers.serde import decode_state, encode_state
from runtime.outbox.repository import InMemoryOutboxRepository

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox_schema (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox_state (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1), canonical_state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox_operations (
  operation_id TEXT PRIMARY KEY, status TEXT NOT NULL, available_at TEXT NOT NULL,
  priority INTEGER NOT NULL, task_id TEXT NOT NULL, aggregate_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE, claim_owner TEXT,
  claim_token_hash TEXT, claim_expires_at TEXT, fencing_token INTEGER NOT NULL,
  reconciliation_state TEXT NOT NULL, dead_letter_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_eligible
ON outbox_operations(status, priority, available_at, operation_id);
CREATE INDEX IF NOT EXISTS idx_outbox_task ON outbox_operations(task_id);
CREATE INDEX IF NOT EXISTS idx_outbox_aggregate ON outbox_operations(aggregate_id);
CREATE TABLE IF NOT EXISTS outbox_attempt_history (
  operation_id TEXT NOT NULL, attempt_number INTEGER NOT NULL,
  started_at TEXT NOT NULL, completed_at TEXT, outcome TEXT NOT NULL,
  failure_code TEXT, failure_category TEXT, safe_summary TEXT NOT NULL,
  PRIMARY KEY(operation_id, attempt_number)
);
CREATE TABLE IF NOT EXISTS outbox_idempotency (
  idempotency_key TEXT PRIMARY KEY, request_fingerprint TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox_provider_pauses (
  provider_id TEXT PRIMARY KEY, paused INTEGER NOT NULL
);
"""


class DatabaseOutboxRepository(InMemoryOutboxRepository):
    def __init__(self, database_path, *, clock=None):
        self.database_path = str(Path(database_path).resolve())
        self._in_mutation = False
        super().__init__(clock=clock)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.executescript(SCHEMA)
            row = connection.execute(
                "SELECT version FROM outbox_schema WHERE singleton=1"
            ).fetchone()
            if row and row[0] > SCHEMA_VERSION:
                raise ValueError("Outbox database schema is newer than supported")
            connection.execute(
                "INSERT OR IGNORE INTO outbox_schema VALUES(1,?)",
                (SCHEMA_VERSION,),
            )
            state = connection.execute(
                "SELECT canonical_state FROM outbox_state WHERE singleton=1"
            ).fetchone()
        finally:
            connection.close()
        if state:
            self.import_state(decode_state(json.loads(state[0])))

    def _connect(self):
        connection = sqlite3.connect(
            self.database_path, timeout=5, isolation_level=None
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _reload(self, connection):
        row = connection.execute(
            "SELECT canonical_state FROM outbox_state WHERE singleton=1"
        ).fetchone()
        if row:
            self.import_state(decode_state(json.loads(row[0])), recover=False)

    def _save(self, connection):
        encoded = json.dumps(encode_state(self.export_state()), sort_keys=True)
        connection.execute(
            "INSERT OR REPLACE INTO outbox_state VALUES(1,?)", (encoded,)
        )
        connection.execute("DELETE FROM outbox_operations")
        connection.executemany(
            "INSERT INTO outbox_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    item.operation_id, item.status.value,
                    item.available_at.isoformat(), item.priority, item.task_id,
                    item.aggregate_id, item.idempotency_key, item.claim_owner,
                    item.claim_token_hash,
                    item.claim_expires_at.isoformat()
                    if item.claim_expires_at else None,
                    item.fencing_token, item.reconciliation_state.value,
                    item.dead_letter_reason,
                )
                for item in self._operations.values()
            ],
        )
        connection.execute("DELETE FROM outbox_attempt_history")
        connection.executemany(
            "INSERT INTO outbox_attempt_history VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    item.operation_id, item.attempt_number,
                    item.started_at.isoformat(),
                    item.completed_at.isoformat() if item.completed_at else None,
                    item.outcome, item.failure_code,
                    item.failure_category.value if item.failure_category else None,
                    item.safe_summary,
                )
                for values in self._attempts.values() for item in values
            ],
        )
        connection.execute("DELETE FROM outbox_idempotency")
        connection.executemany(
            "INSERT INTO outbox_idempotency VALUES(?,?)",
            list(self._idempotency.items()),
        )
        connection.execute("DELETE FROM outbox_provider_pauses")
        connection.executemany(
            "INSERT INTO outbox_provider_pauses VALUES(?,?)",
            [
                (key, int(value))
                for key, value in self._provider_pauses.items()
            ],
        )

    def _mutate(self, method_name, *args, **kwargs):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._reload(connection)
            self._in_mutation = True
            result = getattr(super(), method_name)(*args, **kwargs)
            self._save(connection)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            self._in_mutation = False
            connection.close()

    def _refresh(self):
        connection = self._connect()
        try:
            self._reload(connection)
        finally:
            connection.close()

    def get_operation(self, operation_id):
        if not self._in_mutation:
            self._refresh()
        return super().get_operation(operation_id)

    def list_operations(self, *, status=None):
        if not self._in_mutation:
            self._refresh()
        return super().list_operations(status=status)

    def list_pending_operations(self):
        if not self._in_mutation:
            self._refresh()
        return super().list_pending_operations()

    def list_attempts(self, operation_id):
        if not self._in_mutation:
            self._refresh()
        return super().list_attempts(operation_id)

    def list_by_task(self, task_id):
        self._refresh()
        return super().list_by_task(task_id)

    def list_by_aggregate(self, aggregate_id):
        self._refresh()
        return super().list_by_aggregate(aggregate_id)

    def get_by_idempotency_key(self, key):
        self._refresh()
        return super().get_by_idempotency_key(key)

    def add_operation(self, value): return self._mutate("add_operation", value)
    def claim_next(self, *a, **k): return self._mutate("claim_next", *a, **k)
    def claim_reconciliation(self, *a, **k): return self._mutate("claim_reconciliation", *a, **k)
    def renew_claim(self, *a, **k): return self._mutate("renew_claim", *a, **k)
    def release_claim(self, *a, **k): return self._mutate("release_claim", *a, **k)
    def mark_dispatching(self, *a, **k): return self._mutate("mark_dispatching", *a, **k)
    def mark_succeeded(self, *a, **k): return self._mutate("mark_succeeded", *a, **k)
    def mark_retry_wait(self, *a, **k): return self._mutate("mark_retry_wait", *a, **k)
    def mark_reconciliation_required(self, *a, **k): return self._mutate("mark_reconciliation_required", *a, **k)
    def mark_dead_letter(self, *a, **k): return self._mutate("mark_dead_letter", *a, **k)
    def cancel_operation(self, *a, **k): return self._mutate("cancel_operation", *a, **k)
    def abandon_operation(self, *a, **k): return self._mutate("abandon_operation", *a, **k)
    def retry_dead_letter(self, *a, **k): return self._mutate("retry_dead_letter", *a, **k)
    def pause_provider(self, *a, **k): return self._mutate("pause_provider", *a, **k)
    def resume_provider(self, *a, **k): return self._mutate("resume_provider", *a, **k)
    def recover_expired(self, *a, **k): return self._mutate("recover_expired", *a, **k)
