"""Explicit database persistence transaction."""

from runtime.persistence.database.models import RuntimeLease
from runtime.persistence.database.provider import DatabasePersistenceProvider
from runtime.persistence.models import RuntimeCheckpoint


class DatabasePersistenceTransaction:
    def __init__(
        self,
        provider: DatabasePersistenceProvider,
        runtime_id: str,
        expected_state_version: int,
        *,
        lease: RuntimeLease | None = None,
    ) -> None:
        self.provider = provider
        self.runtime_id = runtime_id
        self.expected_state_version = expected_state_version
        self.lease = lease
        self._checkpoint = None
        self._completed = False

    def stage_checkpoint(self, checkpoint: RuntimeCheckpoint) -> None:
        if self._completed:
            raise RuntimeError("Persistence transaction is completed")
        if checkpoint.runtime_id != self.runtime_id:
            raise ValueError("Checkpoint runtime does not match transaction")
        self._checkpoint = checkpoint

    def commit(self):
        if self._completed or self._checkpoint is None:
            raise RuntimeError("Persistence transaction cannot commit")
        try:
            return self.provider.commit_checkpoint(
                self._checkpoint,
                expected_state_version=self.expected_state_version,
                lease=self.lease,
            )
        finally:
            self._completed = True

    def rollback(self) -> None:
        if self._completed:
            raise RuntimeError("Persistence transaction is completed")
        self._checkpoint = None
        self._completed = True
