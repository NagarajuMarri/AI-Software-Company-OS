"""Managed product project registry."""

from runtime.projects.catalog import (
    SPOKEN_ENGLISH_AI,
    register_spoken_english_ai,
)
from runtime.projects.exceptions import (
    DuplicateProjectError,
    ProjectNotFoundError,
    ProjectRegistryCorruptError,
)
from runtime.projects.models import ManagedProject, ProjectLifecycle
from runtime.projects.registry import (
    FileProjectRegistry,
    InMemoryProjectRegistry,
    ProjectRegistry,
)

__all__ = [
    "DuplicateProjectError",
    "FileProjectRegistry",
    "InMemoryProjectRegistry",
    "ManagedProject",
    "ProjectLifecycle",
    "ProjectNotFoundError",
    "ProjectRegistry",
    "ProjectRegistryCorruptError",
    "SPOKEN_ENGLISH_AI",
    "register_spoken_english_ai",
]
