"""Typed failures for the bounded Day 26 QA Engineer agent."""


class QAWorkforceError(RuntimeError):
    """Base failure for the QA workforce domain."""


class QAWorkforcePolicyError(QAWorkforceError):
    """A role, authority, source, assignment, or output violated QA policy."""


class QAWorkforceConflict(QAWorkforceError):
    """An immutable QA artifact conflicts with persisted state."""


class QAWorkforceNotFound(QAWorkforceError):
    """A requested QA artifact does not exist."""


class QAWorkforceCorrupt(QAWorkforceError):
    """Persisted QA evidence failed safety or integrity checks."""
