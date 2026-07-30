"""Coding-provider boundary failures."""


class CodingProviderError(Exception):
    pass


class ProviderConfigurationError(CodingProviderError):
    pass


class ProviderRegistryError(CodingProviderError):
    pass


class ProviderPolicyError(CodingProviderError):
    pass


class ProviderStateError(CodingProviderError):
    pass


class ProviderReconciliationError(CodingProviderError):
    pass
