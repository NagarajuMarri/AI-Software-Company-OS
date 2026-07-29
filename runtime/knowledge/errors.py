"""Typed project-knowledge failures."""

from runtime.exceptions import RuntimeDomainError


class KnowledgeError(RuntimeDomainError):
    """Base knowledge-engine failure."""


class KnowledgeNotFoundError(KnowledgeError):
    pass


class KnowledgeCorruptError(KnowledgeError):
    pass


class UnsupportedKnowledgeSchemaError(KnowledgeError):
    pass


class RepositoryUnavailableError(KnowledgeError):
    pass


class KnowledgeStorageError(KnowledgeError):
    pass
