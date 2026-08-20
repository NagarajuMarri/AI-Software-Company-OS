"""Typed failures for bounded CEO and Product Manager work."""


class LeadershipWorkforceError(RuntimeError):
    """Base failure for the Day 23 workforce domain."""


class LeadershipWorkforcePolicyError(LeadershipWorkforceError):
    """A role, authority, handoff, or output violated the bounded contract."""


class LeadershipWorkforceConflict(LeadershipWorkforceError):
    """An immutable workforce artifact conflicts with persisted state."""


class LeadershipWorkforceNotFound(LeadershipWorkforceError):
    """A requested workforce artifact does not exist."""


class LeadershipWorkforceCorrupt(LeadershipWorkforceError):
    """Persisted workforce evidence failed integrity or safety validation."""
