"""Typed failures for the bounded Day 29 Documentation Engineer agent."""


class DocumentationWorkforceError(RuntimeError):
    """Base failure for the Documentation workforce domain."""


class DocumentationWorkforcePolicyError(DocumentationWorkforceError):
    """A role, authority, source, assignment, or output violated Documentation policy."""


class DocumentationWorkforceConflict(DocumentationWorkforceError):
    """An immutable Documentation artifact conflicts with persisted state."""


class DocumentationWorkforceNotFound(DocumentationWorkforceError):
    """A requested Documentation artifact does not exist."""


class DocumentationWorkforceCorrupt(DocumentationWorkforceError):
    """Persisted Documentation evidence failed safety or integrity checks."""
