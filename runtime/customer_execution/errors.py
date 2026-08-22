"""Customer-dashboard governed execution failures."""


class CustomerExecutionError(Exception):
    """Base failure for the customer execution boundary."""


class CustomerExecutionNotConfigured(CustomerExecutionError):
    """The operator has not bound an approved product workspace."""


class CustomerExecutionConflict(CustomerExecutionError):
    """The request conflicts with current durable execution state."""


class CustomerExecutionCorrupt(CustomerExecutionError):
    """Durable execution authority failed its integrity checks."""


class CustomerExecutionPolicyError(CustomerExecutionError):
    """An execution request violates a fail-closed policy."""


class CustomerExecutionReconciliationRequired(CustomerExecutionError):
    """A persisted live intent may have produced an effect and cannot be retried."""
