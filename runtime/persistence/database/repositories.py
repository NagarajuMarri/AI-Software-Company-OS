"""Repository aliases backed by the transactional provider."""

from runtime.persistence.database.provider import DatabasePersistenceProvider

DatabaseCheckpointRepository = DatabasePersistenceProvider
DatabaseEventRepository = DatabasePersistenceProvider
