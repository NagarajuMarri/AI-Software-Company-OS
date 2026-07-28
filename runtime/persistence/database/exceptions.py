"""Database persistence and concurrency failures."""

from runtime.persistence.exceptions import PersistenceError


class DatabasePersistenceError(PersistenceError):
    pass


class RuntimeVersionConflictError(DatabasePersistenceError):
    pass


class ConcurrentPersistenceError(DatabasePersistenceError):
    pass


class StaleCheckpointError(DatabasePersistenceError):
    pass


class RuntimeLeaseError(DatabasePersistenceError):
    pass


class LeaseExpiredError(RuntimeLeaseError):
    pass


class LeaseConflictError(RuntimeLeaseError):
    pass


class StaleFencingTokenError(RuntimeLeaseError):
    pass


class DatabaseSchemaError(DatabasePersistenceError):
    pass
