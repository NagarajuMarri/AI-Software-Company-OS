"""Errors for governed Day 36 end-to-end product-pilot verification."""


class EndToEndProductPilotError(Exception):
    """Base error for the first end-to-end product pilot."""


class ProductPilotPolicyError(EndToEndProductPilotError):
    """Raised when a pilot request crosses its authority boundary."""


class ProductPilotConflict(EndToEndProductPilotError):
    """Raised when immutable pilot state conflicts with an existing run."""


class ProductPilotNotFound(EndToEndProductPilotError):
    """Raised when a persisted Day 36 artifact does not exist."""


class ProductPilotCorrupt(EndToEndProductPilotError):
    """Raised when persisted Day 36 state is unsafe or corrupt."""
