import pytest

from runtime.events.event import RuntimeEvent
from runtime.events.types import EventType
from runtime.persistence.database import (
    ConcurrentPersistenceError,
    DatabasePersistenceProvider,
)


def event(identifier, sequence, correlation="corr"):
    return RuntimeEvent(
        identifier,
        EventType.WORK_ITEM_CREATED,
        "work-item",
        "item",
        sequence,
        {"sequence": sequence},
        correlation_id=correlation,
    )


def test_event_queries_and_positions_survive_new_provider(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    provider = DatabasePersistenceProvider(path)
    assert provider.append_event_batch(
        "runtime", [event("one", 1), event("two", 2)]
    ) == [1, 2]

    restarted = DatabasePersistenceProvider(path)
    assert restarted.latest_global_position("runtime") == 2
    assert restarted.latest_aggregate_sequence(
        "runtime", "work-item", "item"
    ) == 2
    assert [e.id for e in restarted.list_events("runtime")] == ["one", "two"]
    assert [e.id for e in restarted.list_events_for_correlation(
        "runtime", "corr"
    )] == ["one", "two"]
    assert restarted.get_event("two").payload["sequence"] == 2


def test_event_batch_constraint_failure_is_all_or_nothing(tmp_path):
    provider = DatabasePersistenceProvider(tmp_path / "runtime.sqlite3")
    with pytest.raises(ConcurrentPersistenceError):
        provider.append_event_batch(
            "runtime", [event("same", 1), event("same", 2)]
        )
    assert provider.list_events("runtime") == []
    assert provider.latest_global_position("runtime") == 0
