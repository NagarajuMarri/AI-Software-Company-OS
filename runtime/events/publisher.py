"""Synchronous runtime event publisher."""

from typing import Mapping

from runtime.events.event import RuntimeEvent
from runtime.events.store import EventStore
from runtime.events.types import EventType, validate_event_type
from runtime.exceptions import (
    DuplicateEventError,
    EventPublicationError,
    ValidationError,
)
from runtime.validation import validate_optional_string, validate_required_string


class EventPublisher:
    def __init__(self, event_store: EventStore) -> None:
        if not isinstance(event_store, EventStore):
            raise ValidationError("event_store must be an EventStore value")
        self.event_store = event_store

    def publish(
        self,
        event_type: EventType,
        aggregate_type: str,
        aggregate_id: str,
        payload: Mapping[str, object],
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        event_id: str | None = None,
    ) -> RuntimeEvent:
        validate_event_type(event_type)
        validate_required_string(aggregate_type, "aggregate_type")
        validate_required_string(aggregate_id, "aggregate_id")
        validate_optional_string(correlation_id, "correlation_id")
        validate_optional_string(causation_id, "causation_id")
        sequence = self.event_store.next_sequence_number(
            aggregate_type,
            aggregate_id,
        )
        resolved_event_id = event_id or (
            f"{aggregate_type}:{aggregate_id}:{sequence}:{event_type.value}"
        )
        event = RuntimeEvent(
            id=resolved_event_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            sequence_number=sequence,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        try:
            return self.event_store.add_event(event)
        except DuplicateEventError:
            raise
        except Exception as error:
            raise EventPublicationError(
                f"Failed to publish event {resolved_event_id!r}"
            ) from error
