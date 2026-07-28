"""Atomic single-process file-backed checkpoint provider."""

import json
import os
import re
import tempfile
from pathlib import Path

from runtime.persistence.exceptions import (
    CheckpointCorruptedError,
    CheckpointNotFoundError,
    DuplicateCheckpointError,
    PersistenceCommitError,
    PersistenceConfigurationError,
    PersistenceIntegrityError,
)
from runtime.persistence.models import RuntimeCheckpoint
from runtime.persistence.serializer import CanonicalSerializer

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class FilePersistenceProvider:
    """Local atomic checkpoint storage; callers must serialize writers."""

    def __init__(self, storage_directory: str | Path) -> None:
        self.storage_directory = Path(storage_directory).resolve()
        try:
            self.storage_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PersistenceConfigurationError(
                "Cannot create persistence directory"
            ) from error
        if not self.storage_directory.is_dir():
            raise PersistenceConfigurationError(
                "Persistence path must be a directory"
            )

    def _validate_id(self, value: str, name: str) -> None:
        if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
            raise PersistenceConfigurationError(f"Unsafe {name}")
        if ".." in value:
            raise PersistenceConfigurationError(f"Unsafe {name}")

    def _path(self, runtime_id: str, checkpoint_id: str) -> Path:
        self._validate_id(runtime_id, "runtime_id")
        self._validate_id(checkpoint_id, "checkpoint_id")
        path = self.storage_directory / (
            f"{runtime_id}--{checkpoint_id}.checkpoint.json"
        )
        if path.parent.resolve() != self.storage_directory:
            raise PersistenceConfigurationError("Checkpoint path escapes storage")
        return path

    def save_checkpoint(self, checkpoint: RuntimeCheckpoint) -> None:
        path = self._path(checkpoint.runtime_id, checkpoint.id)
        if path.exists():
            raise DuplicateCheckpointError(
                f"Checkpoint {checkpoint.id!r} already exists"
            )
        document = self._to_document(checkpoint)
        data = CanonicalSerializer.dumps(document).encode("utf-8")
        temp_path = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=".checkpoint-",
                suffix=".tmp",
                dir=self.storage_directory,
            )
            temp_path = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
            try:
                directory_fd = os.open(self.storage_directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        except OSError as error:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise PersistenceCommitError("Atomic checkpoint write failed") from error

    def load_checkpoint(self, checkpoint_id: str) -> RuntimeCheckpoint:
        self._validate_id(checkpoint_id, "checkpoint_id")
        matches = sorted(
            self.storage_directory.glob(
                f"*--{checkpoint_id}.checkpoint.json"
            )
        )
        if len(matches) != 1:
            raise CheckpointNotFoundError(
                f"Checkpoint {checkpoint_id!r} was not found"
            )
        return self._read(matches[0])

    def list_checkpoints(self, runtime_id: str) -> list[RuntimeCheckpoint]:
        self._validate_id(runtime_id, "runtime_id")
        checkpoints = [
            self._read(path)
            for path in sorted(
                self.storage_directory.glob(
                    f"{runtime_id}--*.checkpoint.json"
                )
            )
        ]
        return sorted(
            checkpoints,
            key=lambda item: (item.created_at, item.id),
        )

    def load_latest_checkpoint(self, runtime_id: str) -> RuntimeCheckpoint:
        self._validate_id(runtime_id, "runtime_id")
        found = False
        valid = []
        for path in self.storage_directory.glob(
            f"{runtime_id}--*.checkpoint.json"
        ):
            found = True
            try:
                valid.append(self._read(path))
            except (CheckpointCorruptedError, PersistenceIntegrityError):
                continue
        if valid:
            return max(valid, key=lambda item: (item.created_at, item.id))
        if found:
            raise CheckpointCorruptedError("No valid checkpoint is available")
        raise CheckpointNotFoundError(
            f"No checkpoints exist for runtime {runtime_id!r}"
        )

    def _read(self, path: Path) -> RuntimeCheckpoint:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            return self._from_document(document)
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise CheckpointCorruptedError(
                f"Checkpoint {path.name!r} is corrupted"
            ) from error

    @staticmethod
    def _to_document(checkpoint: RuntimeCheckpoint) -> dict:
        return {
            "type": "ascos.runtime-checkpoint",
            "id": checkpoint.id,
            "schema_version": checkpoint.schema_version,
            "runtime_id": checkpoint.runtime_id,
            "created_at": checkpoint.created_at.isoformat(),
            "reason": checkpoint.reason,
            "last_event_position": checkpoint.last_event_position,
            "state_digest": checkpoint.state_digest,
            "payload": CanonicalSerializer.encode_value(checkpoint.payload),
        }

    @staticmethod
    def _from_document(document: dict) -> RuntimeCheckpoint:
        if document.get("type") != "ascos.runtime-checkpoint":
            raise CheckpointCorruptedError("Invalid checkpoint discriminator")
        payload = CanonicalSerializer.decode_value(document["payload"])
        if not isinstance(payload, dict):
            raise CheckpointCorruptedError("Checkpoint payload must be a mapping")
        return RuntimeCheckpoint(
            id=document["id"],
            schema_version=document["schema_version"],
            runtime_id=document["runtime_id"],
            created_at=__import__("datetime").datetime.fromisoformat(
                document["created_at"]
            ),
            reason=document["reason"],
            last_event_position=document["last_event_position"],
            state_digest=document["state_digest"],
            payload=payload,
        )
