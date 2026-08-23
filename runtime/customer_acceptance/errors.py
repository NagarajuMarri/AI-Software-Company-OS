"""Typed failures for Completion Module 5 preview and browser acceptance."""


class CustomerAcceptanceError(Exception):
    """Base failure for Completion Module 5."""


class CustomerAcceptanceNotConfigured(CustomerAcceptanceError):
    """The operator did not bind the isolated preview acceptance target."""


class CustomerAcceptanceNotFound(CustomerAcceptanceError):
    """No preview acceptance record exists for the customer request."""


class CustomerAcceptanceConflict(CustomerAcceptanceError):
    """The requested transition is stale or conflicts with durable state."""


class CustomerAcceptancePolicyError(CustomerAcceptanceError):
    """A preview, browser, evidence, or authority boundary was violated."""


class CustomerAcceptanceCorrupt(CustomerAcceptanceError):
    """Persisted preview acceptance evidence is unsafe or corrupt."""


class CustomerAcceptanceReconciliationRequired(CustomerAcceptanceError):
    """A preview/browser effect may exist and requires human reconciliation."""
