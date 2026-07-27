"""Deterministic agent-selection models and validation."""

from dataclasses import dataclass

from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole, validate_agent_role
from runtime.exceptions import ValidationError
from runtime.validation import validate_required_string


def validate_required_capabilities(value: object) -> list[str]:
    """Validate and copy a capability-ID requirement list."""
    if not isinstance(value, list):
        raise ValidationError("required_capabilities must be a list of capability IDs")
    for capability_id in value:
        validate_required_string(capability_id, "required_capabilities")
    if len(value) != len(set(value)):
        raise ValidationError("required_capabilities must not contain duplicates")
    return list(value)


def validate_optional_role(value: object | None) -> None:
    """Validate an agent role only when supplied."""
    if value is not None:
        validate_agent_role(value)


@dataclass
class AgentSelectionResult:
    """Selected agent plus deterministic selection evidence."""

    agent: AgentMetadata
    score: int
    matched_capabilities: list[str]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.agent, AgentMetadata):
            raise ValidationError(
                "AgentSelectionResult.agent must be an AgentMetadata value"
            )
        if (
            not isinstance(self.score, int)
            or isinstance(self.score, bool)
            or self.score < 0
        ):
            raise ValidationError(
                "AgentSelectionResult.score must be a non-negative integer"
            )
        self.matched_capabilities = validate_required_capabilities(
            self.matched_capabilities
        )
        validate_required_string(self.reason, "AgentSelectionResult.reason")
