"""Persistence-specific runtime failures."""

from runtime.exceptions import RuntimeDomainError


class PersistenceError(RuntimeDomainError):
    """Base class for persistence failures."""


class PersistenceConfigurationError(PersistenceError):
    pass


class CheckpointNotFoundError(PersistenceError):
    pass


class DuplicateCheckpointError(PersistenceError):
    pass


class CheckpointCorruptedError(PersistenceError):
    pass


class UnsupportedCheckpointVersionError(PersistenceError):
    pass


class RuntimeRestoreError(PersistenceError):
    pass


class PersistenceCommitError(PersistenceError):
    pass


class PersistenceIntegrityError(PersistenceError):
    pass
