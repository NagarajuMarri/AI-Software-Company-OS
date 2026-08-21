"""Errors for governed Day 35 complete runtime acceptance."""


class CompleteRuntimeAcceptanceError(Exception):
    """Base error for complete runtime acceptance."""


class RuntimeAcceptancePolicyError(CompleteRuntimeAcceptanceError):
    """Raised when a requested browser run crosses its authority boundary."""


class RuntimeAcceptanceConflict(CompleteRuntimeAcceptanceError):
    """Raised when immutable execution state conflicts with an existing run."""


class RuntimeAcceptanceNotFound(CompleteRuntimeAcceptanceError):
    """Raised when a persisted Day 35 artifact does not exist."""


class RuntimeAcceptanceCorrupt(CompleteRuntimeAcceptanceError):
    """Raised when persisted Day 35 state is unsafe or corrupt."""
