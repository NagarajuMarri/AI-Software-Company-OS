"""Deterministic disposable Git workspaces with credential isolation."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

from runtime.managed_product_implementation.models import (
    ManagedProductTask,
    WorkspaceResult,
    utc_now,
)


class WorkspacePreparationError(RuntimeError):
    pass


class DisposableWorkspaceManager:
    def __init__(self, root: str | Path, *, remove_remotes: bool = False) -> None:
        self.root = Path(root).resolve()
        self.remove_remotes = remove_remotes

    def prepare(self, task: ManagedProductTask) -> WorkspaceResult:
        target = self.root / task.project_id / task.task_id
        if target.exists():
            self._remove(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(target.parent),
        }
        self._run(
            (
                "git",
                "clone",
                "--no-tags",
                "--branch",
                task.branch,
                "--single-branch",
                task.repository,
                str(target),
            ),
            target.parent,
            env,
        )
        actual = self._run(("git", "rev-parse", "HEAD"), target, env).strip()
        if actual != task.expected_commit_sha:
            self._remove(target)
            raise WorkspacePreparationError(f"Expected {task.expected_commit_sha}, got {actual}")
        if self.remove_remotes:
            for remote in self._run(("git", "remote"), target, env).splitlines():
                self._run(("git", "remote", "remove", remote), target, env)
        return WorkspaceResult(
            task.task_id,
            str(target),
            task.repository,
            task.branch,
            actual,
            self.remove_remotes,
            utc_now(),
        )

    def cleanup(self, workspace: WorkspaceResult) -> None:
        path = Path(workspace.path).resolve()
        if self.root != path and self.root in path.parents and path.exists():
            self._remove(path)

    @staticmethod
    def _remove(path: Path) -> None:
        def make_writable(function, value, error):
            os.chmod(value, stat.S_IWRITE)
            function(value)

        shutil.rmtree(path, onerror=make_writable)

    @staticmethod
    def _run(command: tuple[str, ...], cwd: Path, env: dict[str, str]) -> str:
        result = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True, shell=False
        )
        if result.returncode:
            raise WorkspacePreparationError(
                result.stderr.strip() or "Git workspace operation failed"
            )
        return result.stdout
