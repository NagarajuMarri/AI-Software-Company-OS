"""Verification, commit, and push services."""

import subprocess
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from runtime.managed_product_implementation.models import (
    CommitResult,
    PushResult,
    VerificationStatus,
    VerificationStep,
    VerificationStepResult,
)

DEFAULT_VERIFICATION_STEPS = (
    VerificationStep("pytest", ("python", "-m", "pytest")),
    VerificationStep("ruff", ("ruff", "check", ".")),
    VerificationStep("mypy", ("mypy", ".")),
    VerificationStep("compileall", ("python", "-m", "compileall", "-q", ".")),
    VerificationStep("git diff --check", ("git", "diff", "--check")),
)


class VerificationService:
    def __init__(
        self,
        *,
        allowed_executables: frozenset[str] = frozenset({"python", "ruff", "mypy", "git"}),
        redacted_values: tuple[str, ...] = (),
        maximum_output_bytes: int = 64_000,
    ) -> None:
        self.allowed_executables = allowed_executables
        self.redacted_values = tuple(value for value in redacted_values if value)
        self.maximum_output_bytes = maximum_output_bytes

    def run(
        self, workspace: Path, steps: tuple[VerificationStep, ...]
    ) -> tuple[VerificationStepResult, ...]:
        results: list[VerificationStepResult] = []
        for step in steps:
            started = datetime.now(timezone.utc)
            try:
                executable = step.command[0]
                if executable not in self.allowed_executables or not re.fullmatch(
                    r"[A-Za-z0-9_.+-]+", executable
                ):
                    raise PermissionError("Verification executable is not allow-listed")
                run = subprocess.run(
                    step.command,
                    cwd=workspace,
                    env=self._environment(),
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=step.timeout_seconds,
                )
                status = VerificationStatus.PASS if run.returncode == 0 else VerificationStatus.FAIL
                output = self._redact((run.stdout + run.stderr)[-self.maximum_output_bytes :])
                code = run.returncode
            except FileNotFoundError:
                status = VerificationStatus.FAIL if step.required else VerificationStatus.SKIPPED
                output, code = "Executable unavailable", None
            except subprocess.TimeoutExpired:
                status, output, code = VerificationStatus.FAIL, "Timed out", None
            except PermissionError as error:
                status = VerificationStatus.FAIL if step.required else VerificationStatus.SKIPPED
                output, code = str(error), None
            except OSError as error:
                status, output, code = VerificationStatus.UNKNOWN, self._redact(str(error)), None
            commit_sha = self._git(workspace, "rev-parse", "HEAD").strip()
            diff = self._git(workspace, "diff", "--binary", "HEAD")
            diff_digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
            results.append(
                VerificationStepResult(
                    step.name,
                    status,
                    step.command,
                    code,
                    output,
                    started,
                    datetime.now(timezone.utc),
                    commit_sha,
                    diff_digest,
                )
            )
            if status is VerificationStatus.FAIL:
                break
        return tuple(results)

    def _environment(self) -> dict[str, str]:
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
        if os.name == "nt":
            environment["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "C:\\Windows")
        return environment

    def _redact(self, value: str) -> str:
        for secret in sorted(set(self.redacted_values), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value

    @staticmethod
    def _git(workspace: Path, *args: str) -> str:
        run = subprocess.run(
            ("git", *args), cwd=workspace, capture_output=True, text=True, shell=False
        )
        return run.stdout if run.returncode == 0 else ""


class CommitService:
    def __init__(self, protected_branches: tuple[str, ...] = ("main", "master")) -> None:
        self.protected_branches = protected_branches

    def commit(
        self,
        workspace: Path,
        paths: tuple[str, ...],
        milestone: str,
        *,
        approved_paths: tuple[str, ...] = (),
    ) -> CommitResult:
        if not paths:
            raise ValueError("At least one changed path is required")
        branch = self._git(workspace, "branch", "--show-current").strip()
        if branch in self.protected_branches:
            raise ValueError("Commit on protected branch is forbidden")
        normalized = tuple(sorted(set(self._validate_path(item) for item in paths)))
        approved = tuple(self._validate_path(item) for item in approved_paths)
        if approved and any(not self._approved(path, approved) for path in normalized):
            raise ValueError("Changed path is outside the approved path scope")
        root = workspace.resolve()
        for path in normalized:
            candidate = workspace / path
            parent = candidate.parent.resolve()
            if root != parent and root not in parent.parents:
                raise ValueError("Changed path escapes workspace through a symlink")
            if candidate.is_symlink():
                raise ValueError("Changed path cannot be a symlink")
        self._git(workspace, "add", "--", *normalized)
        if not milestone.strip() or len(milestone) > 200 or "\n" in milestone or "\0" in milestone:
            raise ValueError("Milestone must produce a bounded single-line commit message")
        message = f"Implement {milestone.strip()}"
        self._git(workspace, "commit", "-m", message)
        sha = self._git(workspace, "rev-parse", "HEAD").strip()
        return CommitResult(sha, message, normalized)

    @staticmethod
    def _approved(path: str, approved: tuple[str, ...]) -> bool:
        return any(path == item or path.startswith(f"{item.rstrip('/')}/") for item in approved)

    @staticmethod
    def _validate_path(value: str) -> str:
        path = PurePosixPath(value.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
            raise ValueError(f"Unsafe changed path: {value}")
        return str(path)

    @staticmethod
    def _git(workspace: Path, *args: str) -> str:
        run = subprocess.run(
            ("git", *args), cwd=workspace, capture_output=True, text=True, shell=False
        )
        if run.returncode:
            raise RuntimeError(run.stderr.strip() or "Git commit operation failed")
        return run.stdout


class GitPushService:
    def __init__(self, protected_branches: tuple[str, ...] = ("main", "master")) -> None:
        self.protected_branches = protected_branches

    def push(
        self,
        workspace: Path,
        branch: str,
        remote: str = "origin",
        *,
        expected_repository: str | None = None,
        expected_commit_sha: str | None = None,
    ) -> PushResult:
        if branch in self.protected_branches:
            return PushResult(
                False, branch, remote, None, "PROTECTED_BRANCH", "Protected branch push refused"
            )
        remotes = self._git(workspace, "remote").splitlines()
        if remote not in remotes:
            return PushResult(
                False, branch, None, None, "REMOTE_MISSING", "Configured remote does not exist"
            )
        current_branch = self._git(workspace, "branch", "--show-current").strip()
        if current_branch != branch:
            return PushResult(
                False,
                branch,
                remote,
                None,
                "BRANCH_MISMATCH",
                "Checked-out branch does not match requested branch",
            )
        remote_url = self._git(workspace, "remote", "get-url", remote).strip()
        if expected_repository is not None and self._normalize_repository(
            remote_url
        ) != self._normalize_repository(expected_repository):
            return PushResult(
                False,
                branch,
                remote,
                None,
                "REMOTE_MISMATCH",
                "Remote repository identity does not match task",
            )
        local_sha = self._git(workspace, "rev-parse", "HEAD").strip()
        if expected_commit_sha is not None and local_sha != expected_commit_sha:
            return PushResult(
                False,
                branch,
                remote,
                None,
                "COMMIT_MISMATCH",
                "Local commit does not match recorded commit",
            )
        run = subprocess.run(
            ("git", "push", "--set-upstream", remote, branch),
            cwd=workspace,
            capture_output=True,
            text=True,
            shell=False,
        )
        if run.returncode:
            return PushResult(
                False,
                branch,
                remote,
                None,
                "RECONCILIATION_REQUIRED",
                self._safe_details(run.stderr),
                reconciliation_required=True,
            )
        tracking = self._git(
            workspace, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"
        ).strip()
        remote_sha = self._git(workspace, "rev-parse", tracking).strip()
        if remote_sha != local_sha:
            return PushResult(
                False,
                branch,
                remote,
                tracking,
                "REMOTE_SHA_MISMATCH",
                "Tracking branch does not match local commit",
                remote_sha,
                True,
            )
        return PushResult(
            True,
            branch,
            remote,
            tracking,
            details=self._safe_details(run.stderr),
            remote_head_sha=remote_sha,
        )

    @staticmethod
    def _normalize_repository(value: str) -> str:
        normalized = (
            value.strip().removesuffix(".git").replace("git@github.com:", "https://github.com/")
        )
        return normalized.rstrip("/").casefold()

    @staticmethod
    def _safe_details(value: str) -> str:
        return re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1[REDACTED]@", value[-4000:])

    @staticmethod
    def _git(workspace: Path, *args: str) -> str:
        run = subprocess.run(
            ("git", *args), cwd=workspace, capture_output=True, text=True, shell=False
        )
        return run.stdout if run.returncode == 0 else ""
