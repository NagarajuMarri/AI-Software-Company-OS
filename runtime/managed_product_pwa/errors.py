"""Managed-product PWA verification errors."""


class PwaVerificationError(ValueError):
    """Raised when PWA authority or observed evidence fails closed."""


class PwaPlanError(PwaVerificationError):
    """Raised when immutable PWA authority cannot be persisted or restored."""


class AcceptanceSubmissionError(ValueError):
    """Raised when capability evidence cannot be safely aggregated."""
