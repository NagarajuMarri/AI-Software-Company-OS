from __future__ import annotations

from enum import Enum

from runtime.exceptions import InvalidLifecycleTransitionError, ValidationError


class LifecycleState(str, Enum):
    """Enumeration of supported lifecycle states for runtime work items and artifacts."""

    CREATED = "CREATED"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    RELEASED = "RELEASED"


LIFECYCLE_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.CREATED: frozenset({LifecycleState.READY}),
    LifecycleState.READY: frozenset({LifecycleState.ASSIGNED}),
    LifecycleState.ASSIGNED: frozenset(
        {LifecycleState.READY, LifecycleState.RUNNING}
    ),
    LifecycleState.RUNNING: frozenset(
        {LifecycleState.ASSIGNED, LifecycleState.REVIEW}
    ),
    LifecycleState.REVIEW: frozenset(
        {LifecycleState.APPROVED, LifecycleState.REJECTED}
    ),
    LifecycleState.REJECTED: frozenset({LifecycleState.RUNNING}),
    LifecycleState.APPROVED: frozenset({LifecycleState.COMPLETED}),
    LifecycleState.COMPLETED: frozenset({LifecycleState.RELEASED}),
    LifecycleState.RELEASED: frozenset(),
}


def validate_lifecycle_state(value: object) -> None:
    """Require a lifecycle value to be a LifecycleState enum member."""
    if not isinstance(value, LifecycleState):
        raise ValidationError(
            "lifecycle state must be a LifecycleState enum value; "
            f"received {type(value).__name__}"
        )


def validate_lifecycle_transition(
    current_state: LifecycleState,
    new_state: LifecycleState,
) -> None:
    """Raise when a lifecycle transition is outside the shared policy."""
    validate_lifecycle_state(current_state)
    validate_lifecycle_state(new_state)
    if new_state not in LIFECYCLE_TRANSITIONS[current_state]:
        raise InvalidLifecycleTransitionError(
            f"Cannot transition from {current_state.value} to {new_state.value}"
        )
