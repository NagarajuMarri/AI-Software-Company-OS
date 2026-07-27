"""Agent identity and discovery primitives for the ASCOS runtime."""

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState

__all__ = [
    "AgentCapability",
    "AgentMetadata",
    "AgentRegistry",
    "AgentRole",
    "AgentState",
]
