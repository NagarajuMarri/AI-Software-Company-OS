"""Validated identity and lifecycle metadata for managed products."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from runtime.exceptions import ValidationError
from runtime.validation import validate_optional_string, validate_required_string


class ProjectLifecycle(str, Enum):
    """High-level operating state of a managed product."""

    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class ManagedProject:
    """Portable product identity and repository routing metadata."""

    project_id: str
    name: str
    description: str
    repository_url: str
    default_branch: str
    local_path: str | None = None
    lifecycle: ProjectLifecycle = ProjectLifecycle.REGISTERED
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_required_string(self.project_id, "ManagedProject.project_id")
        validate_required_string(self.name, "ManagedProject.name")
        validate_required_string(self.description, "ManagedProject.description")
        validate_required_string(
            self.repository_url, "ManagedProject.repository_url"
        )
        parsed = urlparse(self.repository_url)
        if parsed.scheme not in {"http", "https", "ssh"} or not parsed.netloc:
            raise ValidationError(
                "ManagedProject.repository_url must be an absolute HTTP(S) or SSH URL"
            )
        validate_required_string(
            self.default_branch, "ManagedProject.default_branch"
        )
        validate_optional_string(self.local_path, "ManagedProject.local_path")
        if not isinstance(self.lifecycle, ProjectLifecycle):
            raise ValidationError(
                "ManagedProject.lifecycle must be a ProjectLifecycle value"
            )
        if not isinstance(self.tags, tuple):
            raise ValidationError("ManagedProject.tags must be a tuple")
        for tag in self.tags:
            validate_required_string(tag, "ManagedProject.tags item")
        if len(self.tags) != len(set(self.tags)):
            raise ValidationError("ManagedProject.tags must be unique")
