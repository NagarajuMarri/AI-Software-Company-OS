"""Typed failures for managed-product browser execution."""


class ManagedProductBrowserError(ValueError):
    """Base class for browser plan, authority, provider, and evidence failures."""


class BrowserAuthorityError(ManagedProductBrowserError):
    """Raised before effects when persisted authority or current policy does not match."""


class BrowserPlanError(ManagedProductBrowserError):
    """Raised for missing, conflicting, or corrupt immutable journey plans."""


class BrowserProviderUnavailable(ManagedProductBrowserError):
    """Raised when the configured browser implementation cannot be loaded."""


class BrowserArtifactError(ManagedProductBrowserError):
    """Raised when evidence cannot be stored without weakening integrity."""
