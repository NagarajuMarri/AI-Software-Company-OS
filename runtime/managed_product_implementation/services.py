"""Verification, commit, and push services."""

import subprocess
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
    def run(
        self, workspace: Path, steps: tuple[VerificationStep, ...]
    ) -> tuple[VerificationStepResult, ...]:
        results: list[VerificationStepResult] = []
        for step in steps:
            started = datetime.now(timezone.utc)
            try:
                run = subprocess.run(
                    step.command,
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=step.timeout_seconds,
                )
                status = VerificationStatus.PASS if run.returncode == 0 else VerificationStatus.FAIL
                output = (run.stdout + run.stderr)[-64_000:]
                code = run.returncode
            except FileNotFoundError:
                status = VerificationStatus.FAIL if step.required else VerificationStatus.SKIPPED
                output, code = "Executable unavailable", None
            except subprocess.TimeoutExpired:
                status, output, code = VerificationStatus.FAIL, "Timed out", None
            results.append(
                VerificationStepResult(
                    step.name,
                    status,
                    step.command,
                    code,
                    output,
                    started,
                    datetime.now(timezone.utc),
                )
            )
            if status is VerificationStatus.FAIL:
                break
        return tuple(results)


class CommitService:
    def commit(self, workspace: Path, paths: tuple[str, ...], milestone: str) -> CommitResult:
        if not paths:
            raise ValueError("At least one changed path is required")
        normalized = tuple(sorted(set(self._validate_path(item) for item in paths)))
        self._git(workspace, "add", "--", *normalized)
        message = f"Implement {milestone}"
        self._git(workspace, "commit", "-m", message)
        sha = self._git(workspace, "rev-parse", "HEAD").strip()
        return CommitResult(sha, message, normalized)

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

    def push(self, workspace: Path, branch: str, remote: str = "origin") -> PushResult:
        if branch in self.protected_branches:
            return PushResult(
                False, branch, remote, None, "PROTECTED_BRANCH", "Protected branch push refused"
            )
        remotes = self._git(workspace, "remote").splitlines()
        if remote not in remotes:
            return PushResult(
                False, branch, None, None, "REMOTE_MISSING", "Configured remote does not exist"
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
                False, branch, remote, None, "NETWORK_OR_REMOTE_FAILURE", run.stderr[-4000:]
            )
        tracking = self._git(
            workspace, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"
        ).strip()
        return PushResult(True, branch, remote, tracking, details=run.stderr[-4000:])

    @staticmethod
    def _git(workspace: Path, *args: str) -> str:
        run = subprocess.run(
            ("git", *args), cwd=workspace, capture_output=True, text=True, shell=False
        )
        return run.stdout if run.returncode == 0 else ""
