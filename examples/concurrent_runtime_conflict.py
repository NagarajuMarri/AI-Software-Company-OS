"""Show deterministic optimistic concurrency with two SQLite writers."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.persistence.database import (
    DatabasePersistenceProvider,
    RuntimeVersionConflictError,
)
from runtime.persistence.models import RuntimeCheckpoint


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "runtime.sqlite3"
        first = DatabasePersistenceProvider(path)
        second = DatabasePersistenceProvider(path)
        first_version = first.get_state_version("shared-runtime")
        second_version = second.get_state_version("shared-runtime")
        winner = RuntimeCheckpoint.create(
            "winner", "shared-runtime", "first writer", 0, {"events": []}
        )
        loser = RuntimeCheckpoint.create(
            "loser", "shared-runtime", "second writer", 0, {"events": []}
        )
        first.commit_checkpoint(winner, expected_state_version=first_version)
        try:
            second.commit_checkpoint(loser, expected_state_version=second_version)
        except RuntimeVersionConflictError as error:
            print(f"conflict={type(error).__name__}")
        print(
            f"checkpoints={len(second.list_checkpoints('shared-runtime'))} "
            f"events={len(second.list_events('shared-runtime'))} "
            f"winner={second.load_latest_checkpoint('shared-runtime').id}"
        )


if __name__ == "__main__":
    main()
