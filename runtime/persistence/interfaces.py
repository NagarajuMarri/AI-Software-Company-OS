"""Provider-neutral persistence contracts."""

from typing import Protocol, runtime_checkable

if False:  # pragma: no cover
    from runtime.persistence.models import RuntimeCheckpoint


@runtime_checkable
class RuntimeStateRepository(Protocol):
    def save_state(self, runtime_id: str, payload: dict) -> None: ...
    def load_state(self, runtime_id: str) -> dict: ...


@runtime_checkable
class EventRepository(Protocol):
    def save_events(self, runtime_id: str, events: list[dict]) -> None: ...
    def load_events(self, runtime_id: str) -> list[dict]: ...


@runtime_checkable
class CheckpointRepository(Protocol):
    def save_checkpoint(self, checkpoint: "RuntimeCheckpoint") -> None: ...
    def load_checkpoint(self, checkpoint_id: str) -> "RuntimeCheckpoint": ...
    def load_latest_checkpoint(self, runtime_id: str) -> "RuntimeCheckpoint": ...
    def list_checkpoints(self, runtime_id: str) -> list["RuntimeCheckpoint"]: ...


class PersistenceTransaction(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


@runtime_checkable
class PersistenceProvider(CheckpointRepository, Protocol):
    """Checkpoint provider boundary used by runtime composition."""
