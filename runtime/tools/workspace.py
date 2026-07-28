"""Caller-rooted isolated local workspaces."""

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from runtime.tools.exceptions import (
    WorkspaceNotFoundError,
    WorkspaceSecurityError,
)
from runtime.tools.models import Workspace

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class LocalWorkspaceProvider:
    def __init__(self, root_directory: str | Path) -> None:
        self.root = Path(root_directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create_workspace(self, workspace_id: str) -> Workspace:
        if not _ID.fullmatch(workspace_id):
            raise WorkspaceSecurityError("Invalid workspace identifier")
        path = self.root / workspace_id
        path.mkdir(exist_ok=False)
        return Workspace(workspace_id, path, datetime.now(timezone.utc))

    def inspect_workspace(self, workspace_id: str) -> Workspace:
        path = self._workspace_path(workspace_id)
        return Workspace(
            workspace_id, path,
            datetime.fromtimestamp(path.stat().st_ctime, timezone.utc),
        )

    def allocate_task_directory(self, workspace_id: str, task_id: str) -> Path:
        if not _ID.fullmatch(task_id):
            raise WorkspaceSecurityError("Invalid task identifier")
        path = self.resolve_path(workspace_id, f"tasks/{task_id}")
        path.mkdir(parents=True, exist_ok=False)
        return path

    def resolve_path(self, workspace_id: str, relative_path: str = "") -> Path:
        workspace = self._workspace_path(workspace_id)
        candidate = (workspace / relative_path).resolve()
        if candidate != workspace and workspace not in candidate.parents:
            raise WorkspaceSecurityError("Path escapes workspace")
        return candidate

    def validate_repository_location(self, workspace_id: str, path) -> Path:
        resolved = Path(path).resolve()
        workspace = self._workspace_path(workspace_id)
        if resolved != workspace and workspace not in resolved.parents:
            raise WorkspaceSecurityError("Repository escapes workspace")
        if not resolved.is_dir():
            raise WorkspaceNotFoundError("Repository directory does not exist")
        return resolved

    def clean_workspace(self, workspace_id: str) -> None:
        path = self._workspace_path(workspace_id)
        shutil.rmtree(path)

    def _workspace_path(self, workspace_id: str) -> Path:
        if not _ID.fullmatch(workspace_id):
            raise WorkspaceSecurityError("Invalid workspace identifier")
        path = (self.root / workspace_id).resolve()
        if self.root not in path.parents or not path.is_dir():
            raise WorkspaceNotFoundError(workspace_id)
        return path
