"""Immutable external-tool value models."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class CommandRequest:
    executable: str
    arguments: tuple[str, ...] = ()
    working_directory: Path | None = None
    environment: dict[str, str] | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class CommandResult:
    executable: str
    arguments: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    output_truncated: bool


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    local_path: Path
    created_at: datetime
