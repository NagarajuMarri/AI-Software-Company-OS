"""Immutable runtime event model."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Mapping

from runtime.events.types import EventType, validate_event_type
from runtime.exceptions import ValidationError
from runtime.validation import validate_optional_string, validate_required_string


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class RuntimeEvent:
    """One immutable, ordered domain event."""

    id: str
    event_type: EventType
    aggregate_type: str
    aggregate_id: str
    sequence_number: int
    payload: Mapping[str, object]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None
    causation_id: str | None = None

    def __post_init__(self) -> None:
        validate_required_string(self.id, "RuntimeEvent.id")
        validate_event_type(self.event_type)
        validate_required_string(
            self.aggregate_type,
            "RuntimeEvent.aggregate_type",
        )
        validate_required_string(
            self.aggregate_id,
            "RuntimeEvent.aggregate_id",
        )
        if (
            not isinstance(self.sequence_number, int)
            or isinstance(self.sequence_number, bool)
            or self.sequence_number < 1
        ):
            raise ValidationError(
                "RuntimeEvent.sequence_number must be a positive integer"
            )
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() != timedelta(0)
        ):
            raise ValidationError(
                "RuntimeEvent.occurred_at must be timezone-aware UTC"
            )
        validate_optional_string(
            self.correlation_id,
            "RuntimeEvent.correlation_id",
        )
        validate_optional_string(
            self.causation_id,
            "RuntimeEvent.causation_id",
        )
        if not isinstance(self.payload, Mapping):
            raise ValidationError("RuntimeEvent.payload must be a mapping")
        object.__setattr__(
            self,
            "payload",
            _freeze(deepcopy(dict(self.payload))),
        )
