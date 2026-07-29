"""Typed failures for deterministic project management."""

from runtime.exceptions import RuntimeDomainError


class ProjectManagerError(RuntimeDomainError):
    """Base project-manager failure."""


class ManagerStateNotFoundError(ProjectManagerError):
    pass


class ManagerStateCorruptError(ProjectManagerError):
    pass


class UnsupportedManagerSchemaError(ProjectManagerError):
    pass


class DuplicateMilestoneError(ProjectManagerError):
    pass


class UnknownMilestoneError(ProjectManagerError):
    pass


class DuplicateTaskError(ProjectManagerError):
    pass


class UnknownTaskError(ProjectManagerError):
    pass


class UnknownDependencyError(ProjectManagerError):
    pass


class InvalidTaskTransitionError(ProjectManagerError):
    pass


class InvalidMilestoneTransitionError(ProjectManagerError):
    pass


class UnmetTaskDependenciesError(ProjectManagerError):
    pass


class IncompleteMilestoneError(ProjectManagerError):
    pass


class ManagerStorageError(ProjectManagerError):
    pass
