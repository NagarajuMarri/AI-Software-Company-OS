"""Local exact-SHA workspace, process, and readiness provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from runtime.managed_product_environment.errors import (
    EnvironmentCommandError,
    EnvironmentReadinessError,
    EnvironmentShutdownError,
    EnvironmentWorkspaceError,
)
from runtime.managed_product_environment.models import (
    EnvironmentObservation,
    EnvironmentObservationKind,
    EnvironmentObservationOutcome,
    PreparedEnvironment,
    empty_output_digest,
)
from runtime.managed_product_runtime.models import (
    CommandSpec,
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    OneShotCommand,
)


@dataclass
class _ServiceHandle:
    process: subprocess.Popen[bytes]
    service_id: str


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class LocalManagedProductEnvironmentProvider:
    """Execute a verified declaration without a shell inside a disposable clone."""

    def __init__(
        self,
        root_directory: str | Path,
        *,
        git_executable: str = "git",
        maximum_output_bytes: int = 16_000,
    ) -> None:
        if os.name != "posix":
            raise EnvironmentWorkspaceError(
                "PLATFORM_UNSUPPORTED",
                "Local environment execution requires a POSIX process-group adapter",
            )
        if not git_executable or any(character.isspace() for character in git_executable):
            raise ValueError("Git executable must be a simple command name")
        if maximum_output_bytes < 1 or maximum_output_bytes > 1_000_000:
            raise ValueError("Environment output limit is outside policy")
        self._configured_root = Path(root_directory).absolute()
        self.root = self._configured_root.resolve()
        self.git_executable = git_executable
        self.maximum_output_bytes = maximum_output_bytes
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def prepare(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        run_id: str,
    ) -> tuple[PreparedEnvironment, EnvironmentObservation]:
        started = _now()
        self._prepare_root()
        target = self.root / configuration.project_id / configuration.configuration_id / run_id
        resolved_parent = target.parent.resolve()
        if self.root not in resolved_parent.parents:
            raise EnvironmentWorkspaceError(
                "WORKSPACE_ESCAPE", "Environment workspace path escaped its approved root"
            )
        if target.exists() or target.is_symlink():
            raise EnvironmentWorkspaceError(
                "WORKSPACE_EXISTS", "Environment workspace already exists"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        environment = self._git_environment(target.parent)
        clone = self._prepare_git(
            (
                "clone",
                "--no-tags",
                "--branch",
                configuration.branch,
                "--single-branch",
                configuration.repository_url,
                str(target),
            ),
            target.parent,
            environment,
            target,
        )
        if clone.returncode != 0:
            retained = not self._discard_partial(target)
            raise EnvironmentWorkspaceError(
                "SOURCE_CLONE_FAILED",
                "Configured source could not be cloned",
                reconciliation_required=retained,
            )
        checkout = self._prepare_git(
            ("checkout", "--detach", configuration.commit_sha),
            target,
            environment,
            target,
        )
        actual = self._prepare_git(
            ("rev-parse", "HEAD"), target, environment, target
        )
        observed = actual.stdout.decode("utf-8", errors="replace").strip()
        if checkout.returncode != 0 or actual.returncode != 0 or observed != configuration.commit_sha:
            retained = not self._discard_partial(target)
            raise EnvironmentWorkspaceError(
                "SOURCE_COMMIT_MISMATCH",
                "Prepared source does not match the configured exact commit",
                reconciliation_required=retained,
            )
        remotes = self._prepare_git(("remote",), target, environment, target)
        for remote in remotes.stdout.decode("utf-8", errors="replace").splitlines():
            if remote:
                removed = self._prepare_git(
                    ("remote", "remove", remote), target, environment, target
                )
                if removed.returncode != 0:
                    retained = not self._discard_partial(target)
                    raise EnvironmentWorkspaceError(
                        "SOURCE_REMOTE_REMOVAL_FAILED",
                        "Prepared source remote could not be removed",
                        reconciliation_required=retained,
                    )
        if target.is_symlink() or not (target / ".git").is_dir():
            retained = not self._discard_partial(target)
            raise EnvironmentWorkspaceError(
                "SOURCE_LAYOUT_INVALID",
                "Prepared source layout is not trusted",
                reconciliation_required=retained,
            )
        tree_error: EnvironmentWorkspaceError | None = None
        try:
            self._validate_workspace_tree(target.resolve())
        except EnvironmentWorkspaceError as error:
            tree_error = error
        if tree_error is not None:
            retained = not self._discard_partial(target)
            raise EnvironmentWorkspaceError(
                tree_error.code,
                str(tree_error),
                reconciliation_required=retained,
            )
        prepared = PreparedEnvironment(
            f"{configuration.project_id}.{run_id}", target.resolve(), observed
        )
        completed = _now()
        return prepared, EnvironmentObservation(
            EnvironmentObservationKind.SOURCE,
            configuration.configuration_id,
            EnvironmentObservationOutcome.PASS,
            started,
            completed,
            "Exact configured commit prepared in an isolated workspace",
            empty_output_digest(),
            0,
        )

    def run_migration(
        self,
        workspace: PreparedEnvironment,
        command: OneShotCommand,
        environment: dict[str, str],
        redactions: tuple[str, ...],
    ) -> EnvironmentObservation:
        return self._run_one_shot(
            workspace,
            command,
            EnvironmentObservationKind.MIGRATION,
            environment,
            redactions,
        )

    def start_service(
        self,
        workspace: PreparedEnvironment,
        service: ManagedRuntimeService,
        environment: dict[str, str],
    ) -> tuple[object, EnvironmentObservation]:
        started = _now()
        cwd = self._working_directory(workspace, service.start_command)
        process_environment = self._process_environment(environment)
        failure: OSError | None = None
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                [service.start_command.executable, *service.start_command.arguments],
                cwd=cwd,
                env=process_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                start_new_session=os.name != "nt",
            )
        except OSError as error:
            failure = error
        if failure is not None or process is None:
            raise EnvironmentCommandError(
                "SERVICE_START_FAILED", "Declared runtime service could not be started"
            )
        if process.poll() is not None:
            stopped = self._wait_or_terminate(process, 1)
            observation = self._simple_observation(
                EnvironmentObservationKind.SERVICE_STARTUP,
                service.service_id,
                EnvironmentObservationOutcome.FAIL,
                started,
                "Declared runtime service exited during startup",
                process.returncode,
            )
            raise EnvironmentCommandError(
                "SERVICE_START_FAILED",
                "Declared runtime service exited during startup",
                observation=observation,
                reconciliation_required=not stopped,
            )
        return _ServiceHandle(process, service.service_id), self._simple_observation(
            EnvironmentObservationKind.SERVICE_STARTUP,
            service.service_id,
            EnvironmentObservationOutcome.PASS,
            started,
            "Declared runtime service process started",
            None,
        )

    def await_readiness(
        self,
        handle: object,
        service: ManagedRuntimeService,
    ) -> EnvironmentObservation:
        process = self._handle(handle, service)
        started = _now()
        deadline = time.monotonic() + min(
            service.startup_timeout_seconds,
            service.readiness_probe.timeout_seconds,
        )
        last_status: int | None = None
        while time.monotonic() < deadline:
            if process.process.poll() is not None:
                observation = self._simple_observation(
                    EnvironmentObservationKind.READINESS,
                    service.readiness_probe.probe_id,
                    EnvironmentObservationOutcome.FAIL,
                    started,
                    "Runtime service exited before readiness",
                    process.process.returncode,
                )
                raise EnvironmentReadinessError(
                    "SERVICE_EXITED_BEFORE_READY",
                    "Runtime service exited before readiness",
                    observation=observation,
                )
            remaining = max(0.1, deadline - time.monotonic())
            request = Request(service.readiness_probe.url, method="GET")
            try:
                with self._opener.open(request, timeout=min(remaining, 5.0)) as response:
                    last_status = int(response.status)
            except HTTPError as error:
                last_status = error.code
            except (URLError, TimeoutError, OSError):
                last_status = None
            if last_status in service.readiness_probe.expected_status_codes:
                return self._simple_observation(
                    EnvironmentObservationKind.READINESS,
                    service.readiness_probe.probe_id,
                    EnvironmentObservationOutcome.PASS,
                    started,
                    "Declared readiness endpoint returned an expected status",
                    last_status,
                )
            time.sleep(min(service.readiness_probe.interval_seconds, remaining))
        observation = self._simple_observation(
            EnvironmentObservationKind.READINESS,
            service.readiness_probe.probe_id,
            EnvironmentObservationOutcome.FAIL,
            started,
            "Declared readiness endpoint did not become ready",
            last_status,
        )
        raise EnvironmentReadinessError(
            "READINESS_TIMEOUT",
            "Declared readiness endpoint did not become ready",
            observation=observation,
        )

    def stop_service(
        self,
        workspace: PreparedEnvironment,
        handle: object,
        service: ManagedRuntimeService,
        environment: dict[str, str],
        redactions: tuple[str, ...],
    ) -> EnvironmentObservation:
        process = self._handle(handle, service)
        started = _now()
        stop_failure: EnvironmentCommandError | None = None
        try:
            self._run_one_shot(
                workspace,
                service.stop_command,
                EnvironmentObservationKind.SERVICE_STOP,
                environment,
                redactions,
            )
        except EnvironmentCommandError as error:
            stop_failure = error
        stopped = self._wait_or_terminate(process.process, service.shutdown_timeout_seconds)
        if stop_failure is not None or not stopped:
            observation = self._simple_observation(
                EnvironmentObservationKind.SERVICE_STOP,
                service.service_id,
                EnvironmentObservationOutcome.FAIL,
                started,
                "Declared runtime service shutdown required intervention",
                process.process.returncode,
            )
            raise EnvironmentShutdownError(
                "SERVICE_SHUTDOWN_FAILED",
                "Declared runtime service could not be stopped cleanly",
                observation=observation,
                reconciliation_required=not stopped,
            )
        return self._simple_observation(
            EnvironmentObservationKind.SERVICE_STOP,
            service.service_id,
            EnvironmentObservationOutcome.PASS,
            started,
            "Declared runtime service stopped",
            process.process.returncode,
        )

    def cleanup(self, workspace: PreparedEnvironment) -> EnvironmentObservation:
        started = _now()
        path = workspace.path.resolve()
        if self.root not in path.parents or path.is_symlink() or not path.exists():
            raise EnvironmentWorkspaceError(
                "WORKSPACE_CLEANUP_UNSAFE",
                "Environment workspace could not be cleaned safely",
                reconciliation_required=True,
            )
        failure: OSError | None = None
        try:
            self._remove(path)
        except OSError as error:
            failure = error
        if failure is not None:
            raise EnvironmentWorkspaceError(
                "WORKSPACE_CLEANUP_FAILED",
                "Environment workspace cleanup failed",
                reconciliation_required=True,
            )
        return self._simple_observation(
            EnvironmentObservationKind.CLEANUP,
            workspace.workspace_id,
            EnvironmentObservationOutcome.PASS,
            started,
            "Disposable environment workspace removed",
            0,
        )

    def _run_one_shot(
        self,
        workspace: PreparedEnvironment,
        command: OneShotCommand,
        kind: EnvironmentObservationKind,
        environment: dict[str, str],
        redactions: tuple[str, ...],
    ) -> EnvironmentObservation:
        started = _now()
        cwd = self._working_directory(workspace, command.command)
        failure: str | None = None
        result: subprocess.CompletedProcess[bytes] | None = None
        try:
            result = subprocess.run(
                [command.command.executable, *command.command.arguments],
                cwd=cwd,
                env=self._process_environment(environment),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                shell=False,
                timeout=command.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            failure = "COMMAND_TIMEOUT"
        except OSError:
            failure = "COMMAND_START_FAILED"
        if result is None:
            observation = self._simple_observation(
                kind,
                command.command_id,
                EnvironmentObservationOutcome.FAIL,
                started,
                "Declared runtime command did not complete",
                None,
            )
            raise EnvironmentCommandError(
                failure or "COMMAND_FAILED",
                "Declared runtime command did not complete",
                observation=observation,
            )
        digest = self._output_digest(result.stdout, result.stderr, redactions)
        outcome = (
            EnvironmentObservationOutcome.PASS
            if result.returncode == 0
            else EnvironmentObservationOutcome.FAIL
        )
        observation = EnvironmentObservation(
            kind,
            command.command_id,
            outcome,
            started,
            _now(),
            "Declared runtime command completed"
            if result.returncode == 0
            else "Declared runtime command failed",
            digest,
            result.returncode,
        )
        if result.returncode != 0:
            raise EnvironmentCommandError(
                "COMMAND_EXITED_NONZERO",
                "Declared runtime command failed",
                observation=observation,
            )
        return observation

    def _working_directory(
        self, workspace: PreparedEnvironment, command: CommandSpec
    ) -> Path:
        self._validate_workspace_tree(workspace.path)
        candidate = (workspace.path / command.working_directory).resolve()
        if (
            candidate != workspace.path
            and workspace.path not in candidate.parents
        ) or not candidate.is_dir():
            raise EnvironmentWorkspaceError(
                "COMMAND_WORKSPACE_ESCAPE",
                "Declared command working directory is not contained",
            )
        return candidate

    @staticmethod
    def _validate_workspace_tree(workspace: Path) -> None:
        for directory, directory_names, file_names in os.walk(
            workspace, followlinks=False
        ):
            parent = Path(directory)
            for name in (*directory_names, *file_names):
                candidate = parent / name
                if not candidate.is_symlink():
                    continue
                resolved = candidate.resolve()
                if resolved != workspace and workspace not in resolved.parents:
                    raise EnvironmentWorkspaceError(
                        "WORKSPACE_SYMLINK_ESCAPE",
                        "Environment workspace contains an escaping symlink",
                    )

    def _prepare_root(self) -> None:
        if self._configured_root.exists() and self._configured_root.is_symlink():
            raise EnvironmentWorkspaceError(
                "WORKSPACE_ROOT_UNSAFE", "Environment workspace root cannot be a symlink"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise EnvironmentWorkspaceError(
                "WORKSPACE_ROOT_UNAVAILABLE", "Environment workspace root is unavailable"
            )
        self.root.chmod(0o700)

    def _git(
        self, arguments: tuple[str, ...], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        failure = False
        result: subprocess.CompletedProcess[bytes] | None = None
        try:
            result = subprocess.run(
                [self.git_executable, *arguments],
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=300,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            failure = True
        if failure or result is None:
            raise EnvironmentWorkspaceError(
                "GIT_OPERATION_FAILED", "Git workspace operation failed"
            )
        return result

    def _prepare_git(
        self,
        arguments: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
        target: Path,
    ) -> subprocess.CompletedProcess[bytes]:
        failure = False
        result: subprocess.CompletedProcess[bytes] | None = None
        try:
            result = self._git(arguments, cwd, environment)
        except EnvironmentWorkspaceError:
            failure = True
        if failure or result is None:
            retained = not self._discard_partial(target)
            raise EnvironmentWorkspaceError(
                "GIT_OPERATION_FAILED",
                "Git workspace operation failed",
                reconciliation_required=retained,
            )
        return result

    def _discard_partial(self, target: Path) -> bool:
        if not target.exists() and not target.is_symlink():
            return True
        if target.is_symlink():
            return False
        try:
            self._remove(target)
            return True
        except OSError:
            return False

    def _git_environment(self, home: Path) -> dict[str, str]:
        result = {
            "PATH": os.environ.get("PATH", os.defpath),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "HOME": str(home),
        }
        if os.name == "nt":
            result["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        return result

    @staticmethod
    def _process_environment(values: dict[str, str]) -> dict[str, str]:
        result = {"PATH": os.environ.get("PATH", os.defpath)}
        if os.name == "nt":
            result["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        result.update(values)
        return result

    def _output_digest(
        self, stdout: bytes, stderr: bytes, redactions: tuple[str, ...]
    ) -> str:
        bounded = stdout[: self.maximum_output_bytes] + b"\0" + stderr[
            : self.maximum_output_bytes
        ]
        decoded = bounded.decode("utf-8", errors="replace")
        for value in sorted({item for item in redactions if item}, key=len, reverse=True):
            decoded = decoded.replace(value, "[REDACTED]")
        return hashlib.sha256(decoded.encode()).hexdigest()

    @staticmethod
    def _simple_observation(
        kind: EnvironmentObservationKind,
        subject_id: str,
        outcome: EnvironmentObservationOutcome,
        started: datetime,
        summary: str,
        exit_code: int | None,
    ) -> EnvironmentObservation:
        return EnvironmentObservation(
            kind,
            subject_id,
            outcome,
            started,
            _now(),
            summary,
            empty_output_digest(),
            exit_code,
        )

    @staticmethod
    def _handle(handle: object, service: ManagedRuntimeService) -> _ServiceHandle:
        if not isinstance(handle, _ServiceHandle) or handle.service_id != service.service_id:
            raise EnvironmentShutdownError(
                "SERVICE_HANDLE_MISMATCH", "Runtime service handle is not authoritative"
            )
        return handle

    @staticmethod
    def _wait_or_terminate(process: subprocess.Popen[bytes], timeout: int) -> bool:
        if not LocalManagedProductEnvironmentProvider._process_group_alive(process):
            return True
        if process.poll() is None:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                pass
        if not LocalManagedProductEnvironmentProvider._process_group_alive(process):
            return True
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=min(timeout, 5))
            return True
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
            return True
        except (OSError, subprocess.TimeoutExpired):
            return not LocalManagedProductEnvironmentProvider._process_group_alive(
                process
            )

    @staticmethod
    def _process_group_alive(process: subprocess.Popen[bytes]) -> bool:
        if os.name == "nt":
            return process.poll() is None
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def _remove(path: Path) -> None:
        def make_writable(function, value, _error):  # noqa: ANN001
            os.chmod(value, stat.S_IWRITE)
            function(value)

        shutil.rmtree(path, onerror=make_writable)


def _now() -> datetime:
    return datetime.now(timezone.utc)
