"""Provider registration and capability-safe selection."""

from dataclasses import dataclass

from runtime.coding_providers.errors import ProviderRegistryError


@dataclass(frozen=True)
class ProviderRegistration:
    provider: object
    enabled: bool


class CodingProviderRegistry:
    def __init__(self, providers=()):
        self._providers = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider, *, enabled=True):
        if not provider.provider_id or provider.provider_id in self._providers:
            raise ProviderRegistryError("Provider ID must be unique and non-empty")
        self._providers[provider.provider_id] = ProviderRegistration(provider, enabled)
        return provider

    def set_enabled(self, provider_id, enabled):
        registration = self._registration(provider_id)
        self._providers[provider_id] = ProviderRegistration(
            registration.provider, bool(enabled))

    def get(self, provider_id, required_capabilities=()):
        registration = self._registration(provider_id)
        if not registration.enabled:
            raise ProviderRegistryError("Provider is disabled")
        registration.provider.validate_configuration()
        required = frozenset(required_capabilities)
        if not required <= frozenset(registration.provider.capabilities()):
            raise ProviderRegistryError("Provider lacks required capabilities")
        return registration.provider

    def list(self):
        return tuple(
            (identifier, item.enabled, tuple(item.provider.capabilities()))
            for identifier, item in sorted(self._providers.items()))

    def _registration(self, provider_id):
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise ProviderRegistryError("Unknown provider") from error
