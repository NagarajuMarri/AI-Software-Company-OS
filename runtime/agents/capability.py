"""Capability model for registered agents."""

from dataclasses import dataclass, field

from runtime.exceptions import ValidationError
from runtime.validation import validate_required_string


@dataclass
class AgentCapability:
    """A versioned capability supported by an agent."""

    id: str
    name: str
    description: str
    version: str
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_required_string(self.id, "AgentCapability.id")
        validate_required_string(self.name, "AgentCapability.name")
        validate_required_string(self.description, "AgentCapability.description")
        validate_required_string(self.version, "AgentCapability.version")
        for tag in self.tags:
            validate_required_string(tag, "AgentCapability.tags")
        if len(self.tags) != len(set(self.tags)):
            raise ValidationError("AgentCapability.tags must not contain duplicates")
