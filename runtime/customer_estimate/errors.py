"""Customer delivery-estimate errors."""


class CustomerDeliveryEstimateError(Exception):
    """Base customer delivery-estimate error."""


class CustomerDeliveryEstimateNotFound(CustomerDeliveryEstimateError):
    """No customer delivery-estimate draft exists for the request."""


class CustomerDeliveryEstimateConflict(CustomerDeliveryEstimateError):
    """Estimate authority is missing, stale, or conflicting."""


class CustomerDeliveryEstimateCorrupt(CustomerDeliveryEstimateError):
    """Persisted estimate authority failed integrity validation."""
