import sqlite3

import pytest

from runtime.persistence.database import (
    DatabasePersistenceProvider,
    DatabasePersistenceTransaction,
    RuntimeVersionConflictError,
)
from runtime.persistence.models import RuntimeCheckpoint


def cp(identifier):
    return RuntimeCheckpoint.create(
        identifier, "runtime", "transaction", 0, {"events": []}
    )


def test_staged_checkpoint_is_invisible_and_rollback_is_terminal(tmp_path):
    provider = DatabasePersistenceProvider(tmp_path / "runtime.sqlite3")
    transaction = DatabasePersistenceTransaction(provider, "runtime", 0)
    transaction.stage_checkpoint(cp("staged"))
    assert provider.list_checkpoints("runtime") == []

    transaction.rollback()
    assert provider.list_checkpoints("runtime") == []
    with pytest.raises(RuntimeError):
        transaction.commit()


def test_commit_is_terminal_and_version_conflict_is_atomic(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    provider = DatabasePersistenceProvider(path)
    transaction = DatabasePersistenceTransaction(provider, "runtime", 0)
    transaction.stage_checkpoint(cp("winner"))
    transaction.commit()
    with pytest.raises(RuntimeError):
        transaction.rollback()

    stale = DatabasePersistenceTransaction(provider, "runtime", 0)
    stale.stage_checkpoint(cp("loser"))
    with pytest.raises(RuntimeVersionConflictError):
        stale.commit()
    assert [item.id for item in provider.list_checkpoints("runtime")] == [
        "winner"
    ]
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM persistence_transactions"
        ).fetchone()[0] == 1
