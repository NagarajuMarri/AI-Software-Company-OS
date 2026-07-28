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
        self.add_events([event])
        return event

    def add_events(self, events: list[RuntimeEvent]) -> list[RuntimeEvent]:
        if type(self).add_event is not EventStore.add_event:
            for event in events:
                self.add_event(event)
            return list(events)
        pending_ids = set(self._events)
        next_sequences: dict[tuple[str, str], int] = {}
        for event in events:
            self._validate_pending_event(event, pending_ids, next_sequences)
            pending_ids.add(event.id)
            key = (event.aggregate_type, event.aggregate_id)
            next_sequences[key] = event.sequence_number + 1
        for event in events:
            self._events[event.id] = event
        return list(events)

    def _validate_pending_event(
        self,
        event: RuntimeEvent,
        pending_ids: set[str],
        next_sequences: dict[tuple[str, str], int],
    ) -> None:
        if not isinstance(event, RuntimeEvent):
            raise ValidationError("event must be a RuntimeEvent value")
        if event.id in pending_ids:
            raise DuplicateEventError(f"Event {event.id!r} already exists")
        key = (event.aggregate_type, event.aggregate_id)
        expected = next_sequences.get(
            key,
            self.next_sequence_number(event.aggregate_type, event.aggregate_id),
        )
        if event.sequence_number != expected:
            raise ValidationError(
                f"Event sequence must be {expected} for aggregate "
                f"{event.aggregate_type}:{event.aggregate_id}"
            )

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
