"""In-memory registry of ASCOS agents."""

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole, validate_agent_role
from runtime.agents.state import AgentState
from runtime.exceptions import AgentNotFoundError, DuplicateAgentError, ValidationError
from runtime.validation import validate_required_string


class AgentRegistry:
    """Register, discover, and update agent metadata."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentMetadata] = {}

    def register_agent(self, agent: AgentMetadata) -> AgentMetadata:
        """Register a new agent without overwriting an existing identifier."""
        if not isinstance(agent, AgentMetadata):
            raise ValidationError("agent must be an AgentMetadata value")
        if agent.id in self._agents:
            raise DuplicateAgentError(f"Agent {agent.id!r} is already registered")
        self._agents[agent.id] = agent
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

    def update_agent_state(
        self,
        agent_id: str,
        new_state: AgentState,
    ) -> AgentMetadata:
        """Update and return a registered agent's operational state."""
        agent = self.get_agent(agent_id)
        agent.change_state(new_state)
        return agent
