"""Allow-listed command execution without a shell."""

import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from runtime.tools.exceptions import (
    CommandCancelledError,
    CommandTimeoutError,
    InvalidCommandError,
    WorkspaceSecurityError,
)
from runtime.tools.models import CommandRequest, CommandResult

_EXECUTABLE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_SECRET = re.compile(r"(TOKEN|SECRET|PASSWORD|API[_-]?KEY|CREDENTIAL)", re.I)


class LocalCommandRunner:
    def __init__(
        self,
        workspace_root: str | Path,
        *,
        allowed_executables: set[str],
        allowed_environment: set[str] = frozenset(),
        max_output_bytes: int = 64_000,
        base_environment: dict[str, str] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.allowed_executables = frozenset(allowed_executables)
        self.allowed_environment = frozenset(allowed_environment)
        self.max_output_bytes = max_output_bytes
        self.base_environment = dict(base_environment or {})

    def execute(self, request: CommandRequest, *, cancellation=None) -> CommandResult:
        self._validate(request)
        if cancellation is not None and cancellation.is_set():
            raise CommandCancelledError("Command was cancelled")
        working_directory = (
            Path(request.working_directory).resolve()
            if request.working_directory is not None
            else self.workspace_root
        )
        self._require_contained(working_directory)
        environment = dict(self.base_environment)
        for key, value in (request.environment or {}).items():
            if key not in self.allowed_environment or _SECRET.search(key):
                raise InvalidCommandError("Environment key is not allowed")
            if "\0" in key or "\0" in value:
                raise InvalidCommandError("Environment contains NUL byte")
            environment[key] = value
        started = datetime.now(timezone.utc)
        process = None
        try:
            process = subprocess.Popen(
                [request.executable, *request.arguments],
                cwd=working_directory,
                env=environment or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                shell=False,
            )
            deadline = time.monotonic() + request.timeout_seconds
            while True:
                if cancellation is not None and cancellation.is_set():
                    process.kill()
                    process.communicate()
                    raise CommandCancelledError("Command was cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    process.communicate()
                    raise CommandTimeoutError("Command exceeded its timeout")
                try:
                    stdout, stderr = process.communicate(
                        timeout=min(remaining, 0.05)
                    )
                    break
                except subprocess.TimeoutExpired:
                    continue
        except FileNotFoundError as error:
            raise InvalidCommandError("Allowed executable is unavailable") from error
        completed = datetime.now(timezone.utc)
        stdout, out_cut = self._bounded(stdout)
        stderr, err_cut = self._bounded(stderr)
        return CommandResult(
            request.executable,
            request.arguments,
            process.returncode,
            stdout,
            stderr,
            started,
            completed,
            (completed - started).total_seconds(),
            out_cut or err_cut,
        )

    def _validate(self, request: CommandRequest) -> None:
        if (
            not _EXECUTABLE.fullmatch(request.executable)
            or request.executable not in self.allowed_executables
            or "\0" in request.executable
        ):
            raise InvalidCommandError("Executable is not allowed")
        if not isinstance(request.arguments, tuple) or any(
            not isinstance(item, str) or "\0" in item
            for item in request.arguments
        ):
            raise InvalidCommandError("Arguments must be NUL-free strings")
        if request.timeout_seconds <= 0:
            raise InvalidCommandError("Timeout must be positive")

    def _require_contained(self, path: Path) -> None:
        if not path.is_dir() or (
            path != self.workspace_root
            and self.workspace_root not in path.parents
        ):
            raise WorkspaceSecurityError("Working directory escapes workspace")

    def _bounded(self, value: bytes) -> tuple[str, bool]:
        truncated = len(value) > self.max_output_bytes
        return (
            value[: self.max_output_bytes].decode("utf-8", errors="replace"),
            truncated,
        )
