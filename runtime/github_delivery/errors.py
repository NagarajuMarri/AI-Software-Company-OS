"""Errors for governed Day 33 controlled GitHub delivery."""


class GitHubDeliveryError(Exception):
    """Base error for controlled GitHub delivery."""


class GitHubDeliveryPolicyError(GitHubDeliveryError):
    """A request crossed an authority, repository, or delivery boundary."""


class GitHubDeliveryNotFound(GitHubDeliveryError):
    """A persisted delivery artifact does not exist."""


class GitHubDeliveryConflict(GitHubDeliveryError):
    """Write-once delivery state conflicts with the requested execution."""


class GitHubDeliveryCorrupt(GitHubDeliveryError):
    """Persisted delivery state is unsafe or corrupt."""


class GitHubDeliveryReconciliationRequired(GitHubDeliveryError):
    """A partial or ambiguous external effect requires human reconciliation."""
