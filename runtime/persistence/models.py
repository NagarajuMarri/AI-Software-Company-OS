"""Immutable checkpoint model with integrity metadata."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping

from runtime.persistence.exceptions import (
    PersistenceIntegrityError,
    UnsupportedCheckpointVersionError,
)
from runtime.persistence.serializer import CanonicalSerializer
from runtime.validation import validate_required_string

CHECKPOINT_SCHEMA_VERSION = 1


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(v) for v in value)
    if isinstance(value, bytearray):
        return bytes(value)
    if value is None or isinstance(
        value,
        (str, int, float, bool, bytes, Enum),
    ):
        return value
    raise PersistenceIntegrityError("Checkpoint payload is not JSON-compatible")


def checkpoint_digest(
    checkpoint_id: str,
    schema_version: int,
    runtime_id: str,
    created_at: datetime,
    reason: str,
    last_event_position: int,
    payload: Mapping[str, object],
) -> str:
    encoded = CanonicalSerializer.encode_value(
        {
            "id": checkpoint_id,
            "schema_version": schema_version,
            "runtime_id": runtime_id,
            "created_at": created_at,
            "reason": reason,
            "last_event_position": last_event_position,
            "payload": dict(payload),
        }
    )
    return sha256(CanonicalSerializer.dumps(encoded).encode("utf-8")).hexdigest()


class DurabilityStatus(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    COMMITTED_DURABLE = "COMMITTED_DURABLE"
    COMMITTED_NOT_CHECKPOINTED = "COMMITTED_NOT_CHECKPOINTED"
    ROLLED_BACK = "ROLLED_BACK"
    CONFLICTED = "CONFLICTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PersistenceCommitResult:
    runtime_id: str
    operation_id: str
    state_version: int
    checkpoint_id: str | None
    last_event_position: int
    committed: bool
    durable: bool
    durability_status: DurabilityStatus
    committed_at: datetime | None


@dataclass(frozen=True)
class CheckpointSelection:
    checkpoint: "RuntimeCheckpoint"
    recovery_mode: bool
    skipped_corruptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeCheckpoint:
    id: str
    schema_version: int
    runtime_id: str
    created_at: datetime
    reason: str
    last_event_position: int
    state_digest: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        validate_required_string(self.id, "RuntimeCheckpoint.id")
        validate_required_string(self.runtime_id, "RuntimeCheckpoint.runtime_id")
        validate_required_string(self.reason, "RuntimeCheckpoint.reason")
        if self.schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise UnsupportedCheckpointVersionError(
                f"Unsupported checkpoint schema {self.schema_version}"
            )
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() != timedelta(0)
        ):
            raise PersistenceIntegrityError(
                "RuntimeCheckpoint.created_at must be UTC"
            )
        if (
            not isinstance(self.last_event_position, int)
            or isinstance(self.last_event_position, bool)
            or self.last_event_position < 0
        ):
            raise PersistenceIntegrityError(
                "last_event_position must be non-negative"
            )
        frozen = _freeze(dict(self.payload))
        object.__setattr__(self, "payload", frozen)
        if checkpoint_digest(
            self.id,
            self.schema_version,
            self.runtime_id,
            self.created_at,
            self.reason,
            self.last_event_position,
            self.payload,
        ) != self.state_digest:
            raise PersistenceIntegrityError("Checkpoint digest mismatch")

    @classmethod
    def create(
        cls,
        checkpoint_id: str,
        runtime_id: str,
        reason: str,
        last_event_position: int,
        payload: Mapping[str, object],
    ) -> "RuntimeCheckpoint":
        created_at = datetime.now(timezone.utc)
        return cls(
            checkpoint_id,
            CHECKPOINT_SCHEMA_VERSION,
            runtime_id,
            created_at,
            reason,
            last_event_position,
            checkpoint_digest(
                checkpoint_id,
                CHECKPOINT_SCHEMA_VERSION,
                runtime_id,
                created_at,
                reason,
                last_event_position,
                payload,
            ),
            payload,
        )
