"""Errors for governed ASCOS V1 hardening and acceptance."""


class V1HardeningAcceptanceError(Exception):
    """Base error for Day 37 hardening and acceptance."""


class V1HardeningPolicyError(V1HardeningAcceptanceError):
    """Raised when a Day 37 request crosses its authority boundary."""


class V1HardeningConflict(V1HardeningAcceptanceError):
    """Raised when immutable Day 37 state conflicts with an existing run."""


class V1HardeningNotFound(V1HardeningAcceptanceError):
    """Raised when a persisted Day 37 artifact does not exist."""


class V1HardeningCorrupt(V1HardeningAcceptanceError):
    """Raised when persisted Day 37 state is unsafe or corrupt."""
