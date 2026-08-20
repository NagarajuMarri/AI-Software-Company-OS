"""Customer application domain errors."""


class CustomerApplicationError(Exception):
    """Base error for the customer application boundary."""


class ProductRequestNotFound(CustomerApplicationError):
    """The customer-scoped product request does not exist."""


class ProductRequestConflict(CustomerApplicationError):
    """A write-once request identity was reused with different content."""


class ProductRequestCorrupt(CustomerApplicationError):
    """Persisted product-request authority failed integrity validation."""
