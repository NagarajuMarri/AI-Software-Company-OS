import sqlite3

import pytest

from runtime.persistence.database import DatabasePersistenceProvider
from runtime.persistence.database.migrations import migrate
from runtime.persistence.database.schema import DATABASE_SCHEMA_VERSION
from runtime.persistence.models import RuntimeCheckpoint


def checkpoint(runtime_id="runtime", checkpoint_id="cp", events=()):
    payload = {"events": list(events), "state": {"value": checkpoint_id}}
    return RuntimeCheckpoint.create(
        checkpoint_id, runtime_id, "test", len(events), payload
    )


def test_schema_initialization_and_repeatable_migration(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    DatabasePersistenceProvider(path)
    with sqlite3.connect(path) as connection:
        migrate(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            DATABASE_SCHEMA_VERSION
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "runtime_instances",
        "runtime_checkpoints",
        "runtime_events",
        "runtime_state_versions",
        "runtime_leases",
        "persistence_transactions",
    } <= tables


def test_checkpoint_round_trip_and_state_version(tmp_path):
    provider = DatabasePersistenceProvider(tmp_path / "runtime.sqlite3")
    original = checkpoint()
    result = provider.commit_checkpoint(original, expected_state_version=0)

    assert result.committed and result.durable
    assert result.state_version == 1
    assert provider.get_state_version("runtime") == 1
    assert provider.load_checkpoint("cp") == original
    assert provider.load_latest_checkpoint("runtime") == original


def test_unknown_newer_schema_is_rejected(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=999")
    with pytest.raises(Exception, match="schema"):
        DatabasePersistenceProvider(path)
