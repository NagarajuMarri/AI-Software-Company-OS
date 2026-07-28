import pytest

from runtime.coding_agents import (
    CodingAgentProviderRegistry, DeterministicCodingAgentProvider,
)
from runtime.coding_agents.exceptions import (
    DuplicateCodingAgentProviderError, NoCompatibleCodingAgentProviderError,
)


def test_registry_selects_available_compatible_provider_by_priority():
    registry = CodingAgentProviderRegistry()
    registry.register_provider(DeterministicCodingAgentProvider("later", priority=20))
    registry.register_provider(DeterministicCodingAgentProvider("first", priority=10))
    assert registry.choose_compatible_provider({"python"}).provider_id == "first"


def test_registry_rejects_duplicates_and_no_match():
    registry = CodingAgentProviderRegistry()
    registry.register_provider(DeterministicCodingAgentProvider())
    with pytest.raises(DuplicateCodingAgentProviderError):
        registry.register_provider(DeterministicCodingAgentProvider())
    with pytest.raises(NoCompatibleCodingAgentProviderError):
        registry.choose_compatible_provider({"rust"})
