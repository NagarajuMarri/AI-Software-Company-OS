"""Errors for the governed Day 31 isolated product-workspace boundary."""


class ProductWorkspaceError(Exception):
    """Base error for isolated product-workspace operations."""


class ProductWorkspacePolicyError(ProductWorkspaceError):
    """A request violates an authority, source, repository, or path boundary."""


class ProductWorkspaceNotFound(ProductWorkspaceError):
    """A persisted workspace artifact does not exist."""


class ProductWorkspaceConflict(ProductWorkspaceError):
    """Existing write-once state conflicts with the requested workspace."""


class ProductWorkspaceCorrupt(ProductWorkspaceError):
    """Persisted workspace state is unsafe or corrupt."""


class ProductWorkspaceReconciliationRequired(ProductWorkspaceError):
    """A partial or ambiguous Git/worktree effect requires human reconciliation."""
