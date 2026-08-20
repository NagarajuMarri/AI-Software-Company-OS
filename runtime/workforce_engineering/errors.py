"""Typed failures for the bounded Day 25 Engineering agent family."""


class EngineeringWorkforceError(RuntimeError):
    """Base failure for the Engineering workforce domain."""


class EngineeringWorkforcePolicyError(EngineeringWorkforceError):
    """A role, authority, source, assignment, or output violated policy."""


class EngineeringWorkforceConflict(EngineeringWorkforceError):
    """An immutable Engineering artifact conflicts with persisted state."""


class EngineeringWorkforceNotFound(EngineeringWorkforceError):
    """A requested Engineering artifact does not exist."""


class EngineeringWorkforceCorrupt(EngineeringWorkforceError):
    """Persisted Engineering evidence failed safety or integrity checks."""
