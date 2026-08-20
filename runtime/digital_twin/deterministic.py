"""Offline provider used to prove the real provider-neutral runtime boundary."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.agents.role import AgentRole, validate_agent_role
from runtime.digital_twin.contracts import DigitalTwinToolGateway
from runtime.digital_twin.models import (
    ContextValue,
    DigitalTwinExecutionStatus,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    validate_identifier,
    validate_public_field,
)


@dataclass(frozen=True)
class DeterministicToolInvocation:
    """One fixed, reviewable invocation performed by the offline provider."""

    tool_id: str
    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        validate_identifier(self.tool_id, "deterministic invocation tool ID")
        if (
            not isinstance(self.values, tuple)
            or not self.values
            or len(self.values) != len({key for key, _ in self.values})
        ):
            raise ValueError("Deterministic invocation values are invalid")
        for key, value in self.values:
            validate_public_field(key, value, label="deterministic invocation")


class DeterministicDigitalTwinProvider:
    """A real local provider with no network, filesystem, or subprocess access."""

    requires_live_authorization = False

    def __init__(
        self,
        provider_id: str,
        *,
        roles: tuple[AgentRole, ...],
        capabilities: tuple[str, ...],
        tool_invocations: tuple[DeterministicToolInvocation, ...],
    ) -> None:
        validate_identifier(provider_id, "deterministic provider ID")
        if not roles or len(roles) != len(set(roles)):
            raise ValueError("Deterministic provider roles are invalid")
        for role in roles:
            validate_agent_role(role)
        for value in capabilities:
            validate_identifier(value, "deterministic provider capability ID")
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("Deterministic provider capabilities are invalid")
        if not isinstance(tool_invocations, tuple):
            raise ValueError("Deterministic provider tool plan is invalid")
        self.provider_id = provider_id
        self._roles = roles
        self._capabilities = capabilities
        self._invocations = tool_invocations
        self._tool_ids = tuple(dict.fromkeys(item.tool_id for item in tool_invocations))
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return self._roles

    def supported_capabilities(self) -> tuple[str, ...]:
        return self._capabilities

    def supported_tool_ids(self) -> tuple[str, ...]:
        return self._tool_ids

    def execute(
        self,
        request: ProviderExecutionRequest,
        tools: DigitalTwinToolGateway,
    ) -> ProviderExecutionResult:
        self.execution_count += 1
        output: list[ContextValue] = []
        for sequence, invocation in enumerate(self._invocations, start=1):
            response = tools.invoke(invocation.tool_id, dict(invocation.values))
            for key, value in sorted(response.items()):
                output.append(ContextValue(f"tool_{sequence}.{key}", value))
        if not output:
            output.append(ContextValue("completion", "bounded execution verified"))
        return ProviderExecutionResult(
            execution_id=request.execution_id,
            provider_id=self.provider_id,
            request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary="Bounded Digital Twin execution completed",
            output=tuple(output),
        )
