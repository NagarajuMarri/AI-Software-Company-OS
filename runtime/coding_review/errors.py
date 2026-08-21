"""Errors for the governed Day 32 coding and review loop."""


class CodingReviewError(Exception):
    """Base error for coding and review operations."""


class CodingReviewPolicyError(CodingReviewError):
    """A request crossed an authority, source, path, or execution boundary."""


class CodingReviewNotFound(CodingReviewError):
    """A persisted coding-review artifact does not exist."""


class CodingReviewConflict(CodingReviewError):
    """Write-once coding-review state conflicts with the requested execution."""


class CodingReviewCorrupt(CodingReviewError):
    """Persisted coding-review state is unsafe or corrupt."""


class CodingReviewFailed(CodingReviewError):
    """The bounded review rounds ended without QA and Security approval."""


class CodingReviewReconciliationRequired(CodingReviewError):
    """A partial or ambiguous workspace effect requires human reconciliation."""
