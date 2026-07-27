"""Deterministic in-memory runtime event store."""

from runtime.events.event import RuntimeEvent
from runtime.exceptions import (
    DuplicateEventError,
    EventNotFoundError,
    ValidationError,
)
from runtime.validation import validate_required_string


class EventStore:
    def __init__(self) -> None:
        self._events: dict[str, RuntimeEvent] = {}

    def add_event(self, event: RuntimeEvent) -> RuntimeEvent:
        if not isinstance(event, RuntimeEvent):
            raise ValidationError("event must be a RuntimeEvent value")
        if event.id in self._events:
            raise DuplicateEventError(f"Event {event.id!r} already exists")
        expected = self.next_sequence_number(
            event.aggregate_type,
            event.aggregate_id,
        )
        if event.sequence_number != expected:
            raise ValidationError(
                f"Event sequence must be {expected} for aggregate "
                f"{event.aggregate_type}:{event.aggregate_id}"
            )
        self._events[event.id] = event
        return event

    def get_event(self, event_id: str) -> RuntimeEvent:
        validate_required_string(event_id, "event_id")
        if event_id not in self._events:
            raise EventNotFoundError(f"Event {event_id!r} was not found")
        return self._events[event_id]

    def list_events(self) -> list[RuntimeEvent]:
        return list(self._events.values())

    def list_events_for_aggregate(
        self,
        aggregate_type: str,
        aggregate_id: str,
    ) -> list[RuntimeEvent]:
        validate_required_string(aggregate_type, "aggregate_type")
        validate_required_string(aggregate_id, "aggregate_id")
        return [
            event
            for event in self._events.values()
            if event.aggregate_type == aggregate_type
            and event.aggregate_id == aggregate_id
        ]

    def list_events_for_correlation(
        self,
        correlation_id: str,
    ) -> list[RuntimeEvent]:
        validate_required_string(correlation_id, "correlation_id")
        return [
            event
            for event in self._events.values()
            if event.correlation_id == correlation_id
        ]

    def next_sequence_number(
        self,
        aggregate_type: str,
        aggregate_id: str,
    ) -> int:
        validate_required_string(aggregate_type, "aggregate_type")
        validate_required_string(aggregate_id, "aggregate_id")
        return (
            len(
                self.list_events_for_aggregate(
                    aggregate_type,
                    aggregate_id,
                )
            )
            + 1
        )
