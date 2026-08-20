"""Typed failures for managed-product runtime configuration."""


class ManagedProductRuntimeConfigurationError(ValueError):
    """Base error for invalid or unavailable runtime configuration."""


class RuntimeConfigurationConflictError(ManagedProductRuntimeConfigurationError):
    """Raised when immutable configuration history or optimistic versioning conflicts."""


class RuntimeConfigurationNotFoundError(ManagedProductRuntimeConfigurationError):
    """Raised when a requested runtime configuration does not exist."""


class RuntimeConfigurationCorruptError(ManagedProductRuntimeConfigurationError):
    """Raised when persisted runtime configuration cannot be trusted."""


class RuntimeConfigurationPolicyError(ManagedProductRuntimeConfigurationError):
    """Raised when a declaration exceeds operator-owned execution policy."""
