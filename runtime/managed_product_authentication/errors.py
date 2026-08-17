"""Typed failures for exact-commit authentication verification."""


class AuthenticationVerificationError(ValueError):
    """Authentication evidence authority or integrity was invalid."""


class AuthenticationPlanError(AuthenticationVerificationError):
    """An immutable authentication verification plan was invalid or corrupt."""
