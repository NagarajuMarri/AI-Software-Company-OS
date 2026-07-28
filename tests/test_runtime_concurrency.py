import pytest

from runtime.persistence.database import (
    DatabasePersistenceProvider,
    RuntimeVersionConflictError,
)
from runtime.persistence.models import RuntimeCheckpoint


def test_two_connections_cannot_commit_the_same_runtime_version(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    first = DatabasePersistenceProvider(path)
    second = DatabasePersistenceProvider(path)
    expected_by_first = first.get_state_version("shared")
    expected_by_second = second.get_state_version("shared")
    one = RuntimeCheckpoint.create("one", "shared", "writer one", 0, {"events": []})
    two = RuntimeCheckpoint.create("two", "shared", "writer two", 0, {"events": []})

    first.commit_checkpoint(one, expected_state_version=expected_by_first)
    with pytest.raises(RuntimeVersionConflictError):
        second.commit_checkpoint(two, expected_state_version=expected_by_second)

    assert second.get_state_version("shared") == 1
    assert second.load_latest_checkpoint("shared").id == "one"
