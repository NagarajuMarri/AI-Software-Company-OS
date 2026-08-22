"""Typed failures for governed customer review and draft delivery."""


class CustomerDeliveryError(Exception):
    """Base failure for Completion Module 4."""


class CustomerDeliveryNotConfigured(CustomerDeliveryError):
    """The operator did not bind a trusted repository delivery target."""


class CustomerDeliveryNotFound(CustomerDeliveryError):
    """No review record exists for the customer request."""


class CustomerDeliveryConflict(CustomerDeliveryError):
    """The requested transition is stale or conflicts with durable state."""


class CustomerDeliveryPolicyError(CustomerDeliveryError):
    """A repository, review, or authority boundary was violated."""


class CustomerDeliveryCorrupt(CustomerDeliveryError):
    """Persisted review or delivery evidence is unsafe or corrupt."""


class CustomerDeliveryReconciliationRequired(CustomerDeliveryError):
    """A delivery effect may exist and must be reconciled by a human."""
