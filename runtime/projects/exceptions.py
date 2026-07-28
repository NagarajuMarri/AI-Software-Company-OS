"""Managed-project registry exceptions."""

from runtime.exceptions import DuplicateProjectError, ProjectNotFoundError, RuntimeDomainError


class ProjectRegistryCorruptError(RuntimeDomainError):
    """Persisted project registry data cannot be safely loaded."""
