"""Provider and tool protocols for bounded Digital Twin execution."""

from __future__ import annotations

from typing import Mapping, Protocol

from runtime.agents.role import AgentRole
from runtime.digital_twin.models import ProviderExecutionRequest, ProviderExecutionResult


class DigitalTwinToolGateway(Protocol):
    """The only tool-use capability exposed to a provider."""

    def invoke(self, tool_id: str, values: Mapping[str, str]) -> Mapping[str, str]: ...


class DigitalTwinTool(Protocol):
    """One explicitly read-only tool implementation."""

    tool_id: str
    read_only: bool

    def invoke(self, values: Mapping[str, str]) -> Mapping[str, str]: ...


class DigitalTwinProvider(Protocol):
    """Replaceable execution provider with no implicit host authority."""

    provider_id: str
    requires_live_authorization: bool

    def supported_roles(self) -> tuple[AgentRole, ...]: ...

    def supported_capabilities(self) -> tuple[str, ...]: ...

    def supported_tool_ids(self) -> tuple[str, ...]: ...

    def execute(
        self,
        request: ProviderExecutionRequest,
        tools: DigitalTwinToolGateway,
    ) -> ProviderExecutionResult: ...
