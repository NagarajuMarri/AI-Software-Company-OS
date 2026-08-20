"""Customer-facing PRD draft errors."""


class CustomerPrdError(Exception):
    """Base customer PRD error."""


class CustomerPrdNotFound(CustomerPrdError):
    """No PRD draft exists for the customer request."""


class CustomerPrdConflict(CustomerPrdError):
    """PRD generation authority is missing, stale, or conflicting."""


class CustomerPrdCorrupt(CustomerPrdError):
    """Persisted customer PRD authority failed integrity validation."""
