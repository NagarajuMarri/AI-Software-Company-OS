"""Immutable structural software-knowledge models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ImportReference:
    module: str
    names: tuple[str, ...] = ()
    line: int | None = None


@dataclass(frozen=True)
class ExportReference:
    name: str
    line: int | None = None


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    qualified_name: str
    line: int
    end_line: int | None = None
    parent: str | None = None
    decorators: tuple[str, ...] = ()
    docstring: str | None = None
    public: bool = True


@dataclass(frozen=True)
class DependencyEdge:
    source: str
    target: str
    kind: str = "import"


@dataclass(frozen=True)
class FileNode:
    path: str
    name: str
    language: str
    size: int
    lines: int
    category: str
    module: str | None = None
    symbols: tuple[Symbol, ...] = ()
    imports: tuple[ImportReference, ...] = ()
    exports: tuple[ExportReference, ...] = ()
    malformed: bool = False


@dataclass(frozen=True)
class DirectoryNode:
    path: str
    file_count: int


@dataclass(frozen=True)
class RepositoryKnowledge:
    repository_id: str
    root: str
    directories: tuple[DirectoryNode, ...]
    files: tuple[FileNode, ...]
    dependencies: tuple[DependencyEdge, ...]


@dataclass(frozen=True)
class LanguageStatistics:
    language: str
    files: int
    lines: int


@dataclass(frozen=True)
class RepositoryStatistics:
    repositories: int
    directories: int
    files: int
    symbols: int
    classes: int
    functions: int
    dependencies: int
    tests: int
    documentation: int
    configuration: int
    languages: tuple[LanguageStatistics, ...]
    largest_files: tuple[str, ...]


@dataclass(frozen=True)
class ProjectKnowledge:
    project_id: str
    schema_version: int = 1
    repositories: tuple[RepositoryKnowledge, ...] = ()
    scanned_at: datetime = field(default_factory=utc_now)
