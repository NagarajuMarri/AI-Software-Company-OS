"""Metadata model for agents registered with ASCOS."""

from dataclasses import dataclass, field

from runtime.agents.capability import AgentCapability
from runtime.agents.role import AgentRole, validate_agent_role
from runtime.agents.state import (
    AgentState,
    validate_agent_state,
    validate_agent_state_transition,
)
from runtime.exceptions import ValidationError
from runtime.validation import validate_required_string


@dataclass
class AgentMetadata:
    """Identity, capacity, and capability metadata for one agent."""

    id: str
    display_name: str
    role: AgentRole
    description: str
    state: AgentState = AgentState.REGISTERED
    supported_capabilities: list[AgentCapability] = field(default_factory=list)
    max_parallel_tasks: int = 1
    priority: int = 0

    def __post_init__(self) -> None:
        validate_required_string(self.id, "AgentMetadata.id")
        validate_required_string(self.display_name, "AgentMetadata.display_name")
        validate_agent_role(self.role)
        validate_agent_state(self.state)
        if (
            not isinstance(self.max_parallel_tasks, int)
            or isinstance(self.max_parallel_tasks, bool)
            or self.max_parallel_tasks < 1
        ):
            raise ValidationError(
                "AgentMetadata.max_parallel_tasks must be a positive integer"
            )
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ValidationError("AgentMetadata.priority must be an integer")
        validate_required_string(self.description, "AgentMetadata.description")

        capability_ids: list[str] = []
        for capability in self.supported_capabilities:
            if not isinstance(capability, AgentCapability):
                raise ValidationError(
                    "AgentMetadata.supported_capabilities must contain "
                    "AgentCapability values"
                )
            capability_ids.append(capability.id)
        if len(capability_ids) != len(set(capability_ids)):
            raise ValidationError(
                "AgentMetadata.supported_capabilities must not contain duplicate IDs"
            )

    def change_state(self, new_state: AgentState) -> None:
        """Change the agent state according to the shared policy."""
        validate_agent_state_transition(self.state, new_state)
        self.state = new_state

    def supports_capability(self, capability_id: str) -> bool:
        """Return whether the agent advertises a capability identifier."""
        validate_required_string(capability_id, "capability_id")
        return any(
            capability.id == capability_id
            for capability in self.supported_capabilities
        )
