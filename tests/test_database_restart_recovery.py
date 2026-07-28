from runtime.persistence.database import DatabasePersistenceProvider
from runtime.persistence.models import RuntimeCheckpoint


def test_checkpoint_and_event_stream_recover_after_restart(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    first = DatabasePersistenceProvider(path)
    event = {
        "id": "event-1",
        "aggregate_type": "request",
        "aggregate_id": "request-1",
        "sequence_number": 1,
        "event_type": "SOFTWARE_REQUEST_SUBMITTED",
        "occurred_at": "2026-01-01T00:00:00+00:00",
        "correlation_id": "request-1",
        "causation_id": None,
        "payload": {"request": "build"},
    }
    checkpoint = RuntimeCheckpoint.create(
        "cp-1", "runtime", "restart", 1, {"events": [event]}
    )
    first.commit_checkpoint(checkpoint, expected_state_version=0)

    restarted = DatabasePersistenceProvider(path)
    assert restarted.load_latest_checkpoint("runtime") == checkpoint
    assert [item.id for item in restarted.list_events("runtime")] == [
        "event-1"
    ]
    assert restarted.get_state_version("runtime") == 1


def test_missing_durable_event_prevents_restore(tmp_path):
    import sqlite3
    import pytest

    from runtime.persistence.exceptions import PersistenceIntegrityError

    path = tmp_path / "runtime.sqlite3"
    provider = DatabasePersistenceProvider(path)
    event = {
        "id": "event-1",
        "aggregate_type": "request",
        "aggregate_id": "request-1",
        "sequence_number": 1,
        "event_type": "SOFTWARE_REQUEST_SUBMITTED",
        "occurred_at": "2026-01-01T00:00:00+00:00",
        "correlation_id": None,
        "causation_id": None,
        "payload": {},
    }
    provider.commit_checkpoint(
        RuntimeCheckpoint.create(
            "cp", "runtime", "test", 1, {"events": [event]}
        ),
        expected_state_version=0,
    )
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DELETE FROM runtime_events")
    with pytest.raises(PersistenceIntegrityError, match="event position"):
        provider.load_latest_checkpoint("runtime")
