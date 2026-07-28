"""In-memory registry of ASCOS agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole, validate_agent_role
from runtime.agents.state import AgentState
from runtime.exceptions import AgentNotFoundError, DuplicateAgentError, ValidationError
from runtime.validation import validate_required_string
from runtime.transactions import atomic_domain_operation

if TYPE_CHECKING:
    from runtime.events.publisher import EventPublisher


class AgentRegistry:
    """Register, discover, and update agent metadata."""

    def __init__(self, event_publisher: EventPublisher | None = None) -> None:
        self._agents: dict[str, AgentMetadata] = {}
        self.event_publisher = event_publisher
        if event_publisher is not None:
            event_publisher.register_snapshot_provider(self._snapshot_targets)

    @atomic_domain_operation
    def register_agent(self, agent: AgentMetadata) -> AgentMetadata:
        """Register a new agent without overwriting an existing identifier."""
        if not isinstance(agent, AgentMetadata):
            raise ValidationError("agent must be an AgentMetadata value")
        if agent.id in self._agents:
            raise DuplicateAgentError(f"Agent {agent.id!r} is already registered")
        self._agents[agent.id] = agent
        self._publish(
            "AGENT_REGISTERED",
            agent.id,
            {"role": agent.role.value, "state": agent.state.value},
        )
        return agent

    def remove_agent(self, agent_id: str) -> AgentMetadata:
        """Remove and return a registered agent."""
        agent = self.get_agent(agent_id)
        del self._agents[agent_id]
        return agent

    def get_agent(self, agent_id: str) -> AgentMetadata:
        """Retrieve an agent by identifier."""
        validate_required_string(agent_id, "agent_id")
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent {agent_id!r} is not registered")
        return self._agents[agent_id]

    def list_agents(self) -> list[AgentMetadata]:
        """Return all agents in registration order."""
        return list(self._agents.values())

    def find_agents_by_role(self, role: AgentRole) -> list[AgentMetadata]:
        """Return registered agents with the requested role."""
        validate_agent_role(role)
        return [agent for agent in self._agents.values() if agent.role == role]

    def find_agents_by_capability(
        self,
        capability: str | AgentCapability,
    ) -> list[AgentMetadata]:
        """Return agents advertising the requested capability identifier."""
        capability_id = (
            capability.id
            if isinstance(capability, AgentCapability)
            else capability
        )
        validate_required_string(capability_id, "capability_id")
        return [
            agent
            for agent in self._agents.values()
            if agent.supports_capability(capability_id)
        ]

    @atomic_domain_operation
    def update_agent_state(
        self,
        agent_id: str,
        new_state: AgentState,
    ) -> AgentMetadata:
        """Update and return a registered agent's operational state."""
        agent = self.get_agent(agent_id)
        previous_state = agent.state
        agent.change_state(new_state)
        self._publish(
            "AGENT_STATE_CHANGED",
            agent.id,
            {
                "previous_state": previous_state.value,
                "new_state": new_state.value,
            },
        )
        return agent

    def _publish(
        self,
        event_name: str,
        aggregate_id: str,
        payload: dict[str, object],
    ) -> None:
        if self.event_publisher is None:
            return
        from runtime.events.types import EventType

        self.event_publisher.publish(
            EventType(event_name),
            "AGENT",
            aggregate_id,
            payload,
        )

    def _snapshot_targets(self) -> list[object]:
        return [self._agents, *self._agents.values()]
