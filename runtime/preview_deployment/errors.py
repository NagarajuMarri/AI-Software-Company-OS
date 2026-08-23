"""Errors for governed Day 34 isolated preview deployment."""


class PreviewDeploymentError(Exception):
    """Base error for preview deployment."""


class PreviewDeploymentPolicyError(PreviewDeploymentError):
    """Raised when a requested deployment crosses its authority boundary."""


class PreviewDeploymentConflict(PreviewDeploymentError):
    """Raised when immutable deployment state conflicts with an existing execution."""


class PreviewDeploymentReconciliationRequired(PreviewDeploymentError):
    """Raised when an external effect may exist and must be reconciled by a human."""


class PreviewDeploymentNotFound(PreviewDeploymentError):
    """Raised when a persisted preview artifact does not exist."""


class PreviewDeploymentCorrupt(PreviewDeploymentError):
    """Raised when persisted preview state is unsafe or corrupt."""
