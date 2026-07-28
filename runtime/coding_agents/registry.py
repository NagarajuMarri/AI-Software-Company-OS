from runtime.coding_agents.exceptions import (
    CodingAgentProviderNotFoundError,
    CodingAgentProviderUnavailableError,
    DuplicateCodingAgentProviderError,
    NoCompatibleCodingAgentProviderError,
)


class CodingAgentProviderRegistry:
    def __init__(self):
        self._providers = {}

    def register_provider(self, provider):
        if provider.provider_id in self._providers:
            raise DuplicateCodingAgentProviderError(provider.provider_id)
        self._providers[provider.provider_id] = provider
        return provider

    def remove_provider(self, provider_id):
        if provider_id not in self._providers:
            raise CodingAgentProviderNotFoundError(provider_id)
        return self._providers.pop(provider_id)

    def get_provider(self, provider_id):
        try:
            provider = self._providers[provider_id]
        except KeyError as error:
            raise CodingAgentProviderNotFoundError(provider_id) from error
        if not provider.is_available():
            raise CodingAgentProviderUnavailableError(provider_id)
        return provider

    def list_providers(self):
        return tuple(
            sorted(self._providers.values(), key=lambda p: (p.priority, p.provider_id))
        )

    def choose_compatible_provider(self, capabilities):
        required = frozenset(capabilities)
        for provider in self.list_providers():
            if provider.is_available() and required <= frozenset(
                provider.supported_capabilities()
            ):
                return provider
        raise NoCompatibleCodingAgentProviderError(
            "No available provider supports requested capabilities"
        )
