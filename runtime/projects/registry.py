"""Provider-neutral and durable managed-project registries."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from runtime.events.types import EventType
from runtime.exceptions import ValidationError
from runtime.projects.exceptions import (
    DuplicateProjectError,
    ProjectNotFoundError,
    ProjectRegistryCorruptError,
)
from runtime.projects.models import ManagedProject, ProjectLifecycle
from runtime.validation import validate_required_string


@runtime_checkable
class ProjectRegistry(Protocol):
    """Storage-neutral project registration contract."""

    def register(self, project: ManagedProject) -> ManagedProject: ...
    def get(self, project_id: str) -> ManagedProject: ...
    def find_by_repository(self, repository_url: str) -> ManagedProject: ...
    def list_projects(
        self, lifecycle: ProjectLifecycle | None = None
    ) -> tuple[ManagedProject, ...]: ...


class InMemoryProjectRegistry:
    """Deterministic registry implementation for composition and tests."""

    def __init__(
        self,
        projects: Iterable[ManagedProject] = (),
        event_publisher=None,
    ) -> None:
        self._projects: dict[str, ManagedProject] = {}
        self._repositories: dict[str, str] = {}
        self.event_publisher = event_publisher
        for project in projects:
            self.register(project)

    def register(self, project: ManagedProject) -> ManagedProject:
        if not isinstance(project, ManagedProject):
            raise ValidationError("project must be a ManagedProject value")
        repository_key = _repository_key(project.repository_url)
        if project.project_id in self._projects:
            raise DuplicateProjectError(
                f"Project {project.project_id!r} is already registered"
            )
        if repository_key in self._repositories:
            raise DuplicateProjectError(
                "Repository is already registered as project "
                f"{self._repositories[repository_key]!r}"
            )
        self._projects[project.project_id] = project
        self._repositories[repository_key] = project.project_id
        if self.event_publisher is not None:
            self.event_publisher.publish(
                EventType.PROJECT_REGISTERED,
                "PROJECT",
                project.project_id,
                {
                    "repository_url": project.repository_url,
                    "lifecycle": project.lifecycle.value,
                },
            )
        return project

    def get(self, project_id: str) -> ManagedProject:
        validate_required_string(project_id, "project_id")
        try:
            return self._projects[project_id]
        except KeyError as error:
            raise ProjectNotFoundError(
                f"Project {project_id!r} is not registered"
            ) from error

    def find_by_repository(self, repository_url: str) -> ManagedProject:
        validate_required_string(repository_url, "repository_url")
        try:
            return self.get(self._repositories[_repository_key(repository_url)])
        except KeyError as error:
            raise ProjectNotFoundError(
                f"Repository {repository_url!r} is not registered"
            ) from error

    def list_projects(
        self, lifecycle: ProjectLifecycle | None = None
    ) -> tuple[ManagedProject, ...]:
        if lifecycle is not None and not isinstance(lifecycle, ProjectLifecycle):
            raise ValidationError("lifecycle must be a ProjectLifecycle value")
        return tuple(
            project
            for project in sorted(
                self._projects.values(), key=lambda item: item.project_id
            )
            if lifecycle is None or project.lifecycle == lifecycle
        )


class FileProjectRegistry(InMemoryProjectRegistry):
    """Schema-versioned JSON registry with atomic file replacement."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__(self._load())

    def register(self, project: ManagedProject) -> ManagedProject:
        registered = super().register(project)
        try:
            self._save()
        except Exception:
            self._projects.pop(project.project_id, None)
            self._repositories.pop(_repository_key(project.repository_url), None)
            raise
        return registered

    def _load(self) -> tuple[ManagedProject, ...]:
        if not self.path.exists():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version") != self.SCHEMA_VERSION
                or not isinstance(payload.get("projects"), list)
            ):
                raise ValueError("unsupported registry schema")
            return tuple(
                ManagedProject(
                    project_id=value["project_id"],
                    name=value["name"],
                    description=value["description"],
                    repository_url=value["repository_url"],
                    default_branch=value["default_branch"],
                    local_path=value.get("local_path"),
                    lifecycle=ProjectLifecycle(value["lifecycle"]),
                    tags=tuple(value.get("tags", ())),
                )
                for value in payload["projects"]
            )
        except Exception as error:
            raise ProjectRegistryCorruptError(
                f"Project registry {self.path} cannot be safely loaded"
            ) from error

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "projects": [
                {
                    "project_id": item.project_id,
                    "name": item.name,
                    "description": item.description,
                    "repository_url": item.repository_url,
                    "default_branch": item.default_branch,
                    "local_path": item.local_path,
                    "lifecycle": item.lifecycle.value,
                    "tags": list(item.tags),
                }
                for item in self.list_projects()
            ],
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def _repository_key(repository_url: str) -> str:
    return repository_url.rstrip("/").removesuffix(".git").casefold()
