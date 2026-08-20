"""Customer-facing PRD draft errors."""


class CustomerPrdError(Exception):
    """Base customer PRD error."""


class CustomerPrdNotFound(CustomerPrdError):
    """No PRD draft exists for the customer request."""


class CustomerPrdConflict(CustomerPrdError):
    """PRD generation authority is missing, stale, or conflicting."""


class CustomerPrdCorrupt(CustomerPrdError):
    """Persisted customer PRD authority failed integrity validation."""


class CustomerPrdApprovalError(CustomerPrdError):
    """Base customer PRD approval error."""


class CustomerPrdApprovalNotFound(CustomerPrdApprovalError):
    """No locked customer PRD approval exists for the request."""


class CustomerPrdApprovalConflict(CustomerPrdApprovalError):
    """PRD approval authority is missing, stale, or conflicting."""


class CustomerPrdApprovalCorrupt(CustomerPrdApprovalError):
    """Persisted customer PRD approval failed integrity validation."""
