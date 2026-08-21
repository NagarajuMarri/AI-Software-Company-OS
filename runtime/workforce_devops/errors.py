"""Typed failures for the bounded Day 28 DevOps Engineer agent."""


class DevOpsWorkforceError(RuntimeError):
    """Base failure for the DevOps workforce domain."""


class DevOpsWorkforcePolicyError(DevOpsWorkforceError):
    """A role, authority, source, assignment, or output violated DevOps policy."""


class DevOpsWorkforceConflict(DevOpsWorkforceError):
    """An immutable DevOps artifact conflicts with persisted state."""


class DevOpsWorkforceNotFound(DevOpsWorkforceError):
    """A requested DevOps artifact does not exist."""


class DevOpsWorkforceCorrupt(DevOpsWorkforceError):
    """Persisted DevOps evidence failed safety or integrity checks."""
