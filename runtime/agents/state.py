"""Agent availability states and transition policy."""

from enum import Enum

from runtime.exceptions import InvalidAgentStateTransitionError, ValidationError


class AgentState(str, Enum):
    """Operational state of a registered agent."""

    REGISTERED = "REGISTERED"
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"
    DISABLED = "DISABLED"


AGENT_STATE_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.REGISTERED: frozenset(
        {AgentState.AVAILABLE, AgentState.OFFLINE, AgentState.DISABLED}
    ),
    AgentState.AVAILABLE: frozenset(
        {AgentState.BUSY, AgentState.OFFLINE, AgentState.DISABLED}
    ),
    AgentState.BUSY: frozenset(
        {AgentState.AVAILABLE, AgentState.OFFLINE, AgentState.DISABLED}
    ),
    AgentState.OFFLINE: frozenset({AgentState.AVAILABLE, AgentState.DISABLED}),
    AgentState.DISABLED: frozenset(),
}


def validate_agent_state(value: object) -> None:
    """Require an AgentState enum member."""
    if not isinstance(value, AgentState):
        raise ValidationError(
            "agent state must be an AgentState enum value; "
            f"received {type(value).__name__}"
        )


def validate_agent_state_transition(
    current_state: AgentState,
    new_state: AgentState,
) -> None:
    """Require a state change allowed by the agent transition policy."""
    validate_agent_state(current_state)
    validate_agent_state(new_state)
    if new_state not in AGENT_STATE_TRANSITIONS[current_state]:
        raise InvalidAgentStateTransitionError(
            f"Cannot transition agent from {current_state.value} to {new_state.value}"
        )
