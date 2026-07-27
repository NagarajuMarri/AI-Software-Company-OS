"""Agent roles supported by the ASCOS runtime."""

from enum import Enum

from runtime.exceptions import ValidationError


class AgentRole(str, Enum):
    """Functional roles an ASCOS agent may perform."""

    CEO = "CEO"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    SOFTWARE_ARCHITECT = "SOFTWARE_ARCHITECT"
    BACKEND_ENGINEER = "BACKEND_ENGINEER"
    FRONTEND_ENGINEER = "FRONTEND_ENGINEER"
    QA_ENGINEER = "QA_ENGINEER"
    DEVOPS_ENGINEER = "DEVOPS_ENGINEER"
    SECURITY_ENGINEER = "SECURITY_ENGINEER"
    DATA_ENGINEER = "DATA_ENGINEER"
    AI_ENGINEER = "AI_ENGINEER"
    DOCUMENTATION_ENGINEER = "DOCUMENTATION_ENGINEER"


def validate_agent_role(value: object) -> None:
    """Require an AgentRole enum member."""
    if not isinstance(value, AgentRole):
        raise ValidationError(
            "agent role must be an AgentRole enum value; "
            f"received {type(value).__name__}"
        )
