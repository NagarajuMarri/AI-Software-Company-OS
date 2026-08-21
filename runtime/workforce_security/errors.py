"""Typed failures for the bounded Day 27 Security Engineer agent."""


class SecurityWorkforceError(RuntimeError):
    """Base failure for the Security workforce domain."""


class SecurityWorkforcePolicyError(SecurityWorkforceError):
    """A role, authority, source, assignment, or output violated Security policy."""


class SecurityWorkforceConflict(SecurityWorkforceError):
    """An immutable Security artifact conflicts with persisted state."""


class SecurityWorkforceNotFound(SecurityWorkforceError):
    """A requested Security artifact does not exist."""


class SecurityWorkforceCorrupt(SecurityWorkforceError):
    """Persisted Security evidence failed safety or integrity checks."""
