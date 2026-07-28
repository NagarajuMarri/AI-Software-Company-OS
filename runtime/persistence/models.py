"""Immutable checkpoint model with integrity metadata."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise PersistenceIntegrityError("Checkpoint payload is not JSON-compatible")


def payload_digest(payload: Mapping[str, object]) -> str:
    encoded = CanonicalSerializer.encode_value(dict(payload))
    return sha256(CanonicalSerializer.dumps(encoded).encode("utf-8")).hexdigest()


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
        if payload_digest(self.payload) != self.state_digest:
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
        return cls(
            checkpoint_id,
            CHECKPOINT_SCHEMA_VERSION,
            runtime_id,
            datetime.now(timezone.utc),
            reason,
            last_event_position,
            payload_digest(payload),
            payload,
        )
