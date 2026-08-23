"""Typed failures for the bounded Day 24 Software Architect agent."""


class ArchitectureWorkforceError(RuntimeError):
    """Base failure for the Software Architect workforce domain."""


class ArchitectureWorkforcePolicyError(ArchitectureWorkforceError):
    """A role, authority, source, or provider output violated policy."""


class ArchitectureWorkforceConflict(ArchitectureWorkforceError):
    """An immutable architecture artifact conflicts with persisted state."""


class ArchitectureWorkforceNotFound(ArchitectureWorkforceError):
    """A requested architecture artifact does not exist."""


class ArchitectureWorkforceCorrupt(ArchitectureWorkforceError):
    """Persisted architecture evidence failed safety or integrity checks."""
