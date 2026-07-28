import sqlite3

import pytest

from runtime.outbox.models import OutboxStatus
from runtime.outbox.providers.database import DatabaseOutboxRepository


def test_database_creation_restart_and_indexes(operation_factory, outbox_clock, tmp_path):
    path = tmp_path / "outbox.sqlite3"
    first = DatabaseOutboxRepository(path, clock=outbox_clock)
    first.add_operation(operation_factory())
    second = DatabaseOutboxRepository(path, clock=outbox_clock)
    assert second.get_operation("op").status == OutboxStatus.PENDING
    with sqlite3.connect(path) as connection:
        indexes = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
    assert {"idx_outbox_eligible", "idx_outbox_task"} <= indexes


def test_database_claim_is_atomic_across_connections(operation_factory, outbox_clock, tmp_path):
    path = tmp_path / "outbox.sqlite3"
    first = DatabaseOutboxRepository(path, clock=outbox_clock)
    second = DatabaseOutboxRepository(path, clock=outbox_clock)
    first.add_operation(operation_factory())
    assert first.claim_next("one") is not None
    assert second.claim_next("two") is None


def test_database_completion_persists_attempt_history(operation_factory, outbox_clock, tmp_path):
    path = tmp_path / "outbox.sqlite3"
    repository = DatabaseOutboxRepository(path, clock=outbox_clock)
    repository.add_operation(operation_factory())
    claim = repository.claim_next("worker")
    repository.mark_dispatching(claim)
    repository.mark_succeeded(claim, "reference")
    restarted = DatabaseOutboxRepository(path, clock=outbox_clock)
    assert restarted.get_operation("op").status == OutboxStatus.SUCCEEDED
    assert restarted.list_attempts("op")[0].outcome == "SUCCEEDED"


def test_database_unknown_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE outbox_schema(singleton INTEGER PRIMARY KEY, version INTEGER)"
        )
        connection.execute("INSERT INTO outbox_schema VALUES(1,999)")
    with pytest.raises(ValueError, match="newer"):
        DatabaseOutboxRepository(path)
