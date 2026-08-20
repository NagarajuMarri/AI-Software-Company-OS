"""Closed provider and read-only tool registries for Digital Twins."""

from __future__ import annotations

from runtime.agents.role import AgentRole, validate_agent_role
from runtime.digital_twin.contracts import DigitalTwinProvider, DigitalTwinTool
from runtime.digital_twin.errors import DigitalTwinRegistryError
from runtime.digital_twin.models import validate_identifier


class DigitalTwinProviderRegistry:
    """Register replaceable providers without selecting one implicitly."""

    def __init__(self, providers: tuple[DigitalTwinProvider, ...] = ()) -> None:
        self._providers: dict[str, DigitalTwinProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: DigitalTwinProvider) -> DigitalTwinProvider:
        try:
            validate_identifier(provider.provider_id, "Digital Twin provider ID")
            if not isinstance(provider.requires_live_authorization, bool):
                raise ValueError("provider live-authorization policy is invalid")
            roles = provider.supported_roles()
            capabilities = provider.supported_capabilities()
            tools = provider.supported_tool_ids()
            if (
                not isinstance(roles, tuple)
                or not isinstance(capabilities, tuple)
                or not isinstance(tools, tuple)
                or len(roles) != len(set(roles))
                or len(capabilities) != len(set(capabilities))
                or len(tools) != len(set(tools))
            ):
                raise ValueError("provider support declarations are invalid")
            for role in roles:
                validate_agent_role(role)
            for value in (*capabilities, *tools):
                validate_identifier(value, "Digital Twin provider support ID")
            if not callable(provider.execute):
                raise ValueError("provider execute boundary is missing")
        except (AttributeError, TypeError, ValueError) as error:
            raise DigitalTwinRegistryError("Digital Twin provider is invalid") from error
        if provider.provider_id in self._providers:
            raise DigitalTwinRegistryError("Digital Twin provider ID is already registered")
        self._providers[provider.provider_id] = provider
        return provider

    def get(self, provider_id: str) -> DigitalTwinProvider:
        try:
            validate_identifier(provider_id, "Digital Twin provider ID")
            return self._providers[provider_id]
        except (KeyError, ValueError) as error:
            raise DigitalTwinRegistryError("Digital Twin provider is not registered") from error


class DigitalTwinToolRegistry:
    """Register only read-only tools for the Day 22 authority boundary."""

    def __init__(self, tools: tuple[DigitalTwinTool, ...] = ()) -> None:
        self._tools: dict[str, DigitalTwinTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: DigitalTwinTool) -> DigitalTwinTool:
        try:
            validate_identifier(tool.tool_id, "Digital Twin tool ID")
            if tool.read_only is not True or not callable(tool.invoke):
                raise ValueError("Day 22 tools must be explicitly read-only")
        except (AttributeError, TypeError, ValueError) as error:
            raise DigitalTwinRegistryError("Digital Twin tool is invalid") from error
        if tool.tool_id in self._tools:
            raise DigitalTwinRegistryError("Digital Twin tool ID is already registered")
        self._tools[tool.tool_id] = tool
        return tool

    def get(self, tool_id: str) -> DigitalTwinTool:
        try:
            validate_identifier(tool_id, "Digital Twin tool ID")
            return self._tools[tool_id]
        except (KeyError, ValueError) as error:
            raise DigitalTwinRegistryError("Digital Twin tool is not registered") from error
