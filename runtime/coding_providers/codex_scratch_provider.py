"""Codex CLI execution in disposable workspaces with ASCOS-observed results."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from runtime.coding_providers.errors import ProviderConfigurationError, ProviderStateError
from runtime.coding_providers.models import (
    FileOperation, FileOperationKind, ProviderCapability, ProviderProgressEvent,
    ProviderResponseReceipt, ProviderResultStatus, ProviderTaskResult, ProviderUsage,
)
from runtime.coding_providers.path_policy import allowed_path, secure_destination
from runtime.tools.models import CommandRequest


_VERSION = re.compile(r"codex-cli\s+(\d+)\.(\d+)\.(\d+)")
_SECRET = re.compile(r"(?:SECRET|TOKEN|PASSWORD|PRIVATE KEY|API[_-]?KEY|CREDENTIAL)", re.I)
_EXCLUDED = {".env", ".venv", "node_modules", ".ascos-state", ".ascos-codex"}


class ScratchStage(str, Enum):
    SCRATCH_PREPARED = "SCRATCH_PREPARED"
    PROVIDER_STARTED = "PROVIDER_STARTED"
    PROVIDER_EXITED = "PROVIDER_EXITED"
    OBSERVATION_STARTED = "OBSERVATION_STARTED"
    MANIFEST_PERSISTED = "MANIFEST_PERSISTED"
    RESULT_CONVERTED = "RESULT_CONVERTED"
    RESULT_ACCEPTED = "RESULT_ACCEPTED"
    CLEANUP_COMPLETED = "CLEANUP_COMPLETED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    FAILED = "FAILED"


class ScratchWorkspaceSecurityMode(str, Enum):
    PORTABLE_BASELINE = "PORTABLE_BASELINE"
    WINDOWS_CURRENT_USER = "WINDOWS_CURRENT_USER"
    POSIX_RESTRICTIVE = "POSIX_RESTRICTIVE"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class ScratchAccessSnapshot:
    mode: ScratchWorkspaceSecurityMode
    root_accessible: bool
    git_accessible: bool
    approved_parents_accessible: bool
    probe_passed: bool
    explicit_deny_detected: bool
    reparse_detected: bool
    acl_digest: str


class ScratchWorkspaceSecurityPolicy:
    """Platform-aware observer access checks; never broadens native ACLs."""

    def __init__(self, mode=ScratchWorkspaceSecurityMode.PORTABLE_BASELINE,
                 *, acl_reader=None):
        self.mode = mode
        self.acl_reader = acl_reader or (lambda path: "")

    def prepare_and_check(self, root, approved_paths, *, create_parents=False):
        root = Path(root).resolve()
        parents = tuple(sorted({(root / path).parent for path in approved_paths}, key=str))
        if create_parents:
            for parent in parents:
                secure_destination(root, parent.relative_to(root).as_posix())
                parent.mkdir(parents=True, exist_ok=True)
        reparse = any(path.is_symlink() for path in (root, root / ".git", *parents))
        root_ok = self._enumerable(root)
        git_ok = self._enumerable(root / ".git")
        parents_ok = all(self._enumerable(parent) for parent in parents)
        probe_ok = False
        control = root / ".ascos-observer-control"
        try:
            control.mkdir(exist_ok=False)
            probe = control / f"probe-{secrets.token_hex(6)}"
            probe.write_text("observer", encoding="utf-8")
            probe_ok = probe.read_text(encoding="utf-8") == "observer"
            probe.unlink(); control.rmdir()
        except OSError:
            probe_ok = False
        acl_values = tuple(self.acl_reader(path) for path in (root, root / ".git", *parents))
        deny = any("(DENY_OBSERVER)" in value.upper() for value in acl_values)
        acl_digest = hashlib.sha256("\n".join(acl_values).encode()).hexdigest()
        snapshot = ScratchAccessSnapshot(
            self.mode, root_ok, git_ok, parents_ok, probe_ok, deny, reparse, acl_digest)
        if not all((root_ok, git_ok, parents_ok, probe_ok)) or reparse:
            raise ProviderStateError("Scratch workspace access pre/postflight failed")
        if self.mode == ScratchWorkspaceSecurityMode.WINDOWS_CURRENT_USER and os.name != "nt":
            raise ProviderConfigurationError("Windows policy requires Windows")
        return snapshot

    @staticmethod
    def _enumerable(path):
        try:
            tuple(Path(path).iterdir())
            return True
        except OSError:
            return False


@dataclass(frozen=True)
class ObservedCodexFile:
    path: str
    change_kind: str
    prior_digest: str | None
    resulting_digest: str | None
    utf8_valid: bool


@dataclass(frozen=True)
class ObservedCodexPatchManifest:
    schema_version: int
    operation_id: str
    provider_id: str
    cli_version: str
    model: str
    scratch_workspace_id: str
    baseline_commit_sha: str
    baseline_tree_digest: str
    exit_code: int
    started_at: datetime
    completed_at: datetime
    changed_paths: tuple[str, ...]
    created_paths: tuple[str, ...]
    modified_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]
    files: tuple[ObservedCodexFile, ...]
    git_diff_digest: str
    additions: int
    deletions: int
    total_patch_bytes: int
    total_resulting_content_bytes: int
    workspace_classification: str
    prohibited_paths_passed: bool
    symlink_reparse_passed: bool
    manifest_digest: str


@dataclass(frozen=True)
class ScratchEffect:
    operation_id: str
    scratch_workspace_id: str
    scratch_path: str
    source_path: str
    request_digest: str
    context_digest: str
    stage: ScratchStage
    baseline_commit_sha: str
    baseline_tree_digest: str
    manifest_digest: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class CodexScratchConfiguration:
    provider_id: str = "codex-cli-scratch"
    executable: str = "codex.cmd"
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "high"
    minimum_cli_version: tuple[int, int, int] = (0, 146, 0)
    maximum_cli_version: tuple[int, int, int] = (0, 146, 999)
    source_workspace: str = ""
    scratch_root: str = ""
    timeout_seconds: int = 600
    maximum_stdout_bytes: int = 128_000
    maximum_stderr_bytes: int = 16_000
    maximum_changed_files: int = 12
    maximum_file_bytes: int = 256_000
    maximum_total_patch_bytes: int = 128_000
    enabled: bool = False
    retain_on_failure: bool = True


class CodexScratchCodingProvider:
    provider_id = "codex-cli-scratch"

    def __init__(self, configuration, *, runner, response_sink, manifest_sink, effect_sink,
                 security_policy=None):
        self.configuration = configuration
        self.runner = runner
        self.response_sink = response_sink
        self.manifest_sink = manifest_sink
        self.effect_sink = effect_sink
        self.security_policy = security_policy or ScratchWorkspaceSecurityPolicy()
        self.cli_version = None
        self._validated = False
        self._tasks = {}
        self._keys = {}

    def validate_configuration(self):
        if self._validated:
            return
        config = self.configuration
        source, scratch = Path(config.source_workspace).resolve(), Path(config.scratch_root).resolve()
        if not config.enabled or not source.is_dir() or not (source / ".git").is_dir():
            raise ProviderConfigurationError("Scratch provider source is unavailable")
        scratch.mkdir(parents=True, exist_ok=True)
        secure_destination(scratch.parent, scratch.name)
        if scratch.is_symlink():
            raise ProviderConfigurationError("Scratch root cannot be a link")
        result = self.runner.execute(CommandRequest(
            config.executable, ("--version",), scratch, {}, 30))
        match = _VERSION.search(result.stdout)
        if result.exit_code or not match:
            raise ProviderConfigurationError("Codex CLI version could not be verified")
        version = tuple(int(item) for item in match.groups())
        if not config.minimum_cli_version <= version <= config.maximum_cli_version:
            raise ProviderConfigurationError("Codex CLI version is unsupported")
        self.cli_version = ".".join(str(item) for item in version)
        self._validated = True

    def capabilities(self):
        return (
            ProviderCapability.CODE_GENERATION, ProviderCapability.CODE_MODIFICATION,
            ProviderCapability.TEST_GENERATION, ProviderCapability.DOCUMENTATION,
            ProviderCapability.REFACTORING, ProviderCapability.FRONTEND_IMPLEMENTATION,
            ProviderCapability.REPOSITORY_ANALYSIS, ProviderCapability.STRUCTURED_PROGRESS,
            ProviderCapability.IDEMPOTENT_SUBMISSION, ProviderCapability.RESULT_ARTIFACTS,
        )

    def submit_task(self, request):
        self.validate_configuration()
        if request.provider_idempotency_key in self._keys:
            return self._keys[request.provider_idempotency_key]
        scratch, identity = self._prepare(request)
        baseline_commit = self._git(scratch, "rev-parse", "HEAD").stdout.strip()
        baseline_tree = self._tree_digest(scratch)
        preflight = self.security_policy.prepare_and_check(
            scratch, request.context.allowed_paths, create_parents=True)
        effect = ScratchEffect(
            request.provider_operation_id, identity, str(scratch),
            str(Path(self.configuration.source_workspace).resolve()), request.request_digest,
            request.context_digest, ScratchStage.SCRATCH_PREPARED, baseline_commit, baseline_tree)
        self.effect_sink(effect)
        started = datetime.now(timezone.utc)
        self.effect_sink(replace(effect, stage=ScratchStage.PROVIDER_STARTED, updated_at=started))
        result_path = scratch / f".ascos-summary-{request.request_digest[:16]}.txt"
        prompt = self._prompt(request)
        command = self.runner.execute(CommandRequest(
            self.configuration.executable,
            ("exec", "--ephemeral", "--ignore-rules", "--sandbox", "workspace-write",
             "-c", 'approval_policy="never"', "--model", self.configuration.model,
             "-c", f'model_reasoning_effort="{self.configuration.reasoning_effort}"',
             "--output-last-message", str(result_path), prompt),
            scratch, {}, min(request.timeout_seconds, self.configuration.timeout_seconds)))
        completed = datetime.now(timezone.utc)
        exited = replace(effect, stage=ScratchStage.PROVIDER_EXITED, updated_at=completed)
        self.effect_sink(exited)
        summary = result_path.read_text(encoding="utf-8", errors="replace")[:2_000] \
            if result_path.is_file() else ""
        result_path.unlink(missing_ok=True)
        if command.exit_code:
            self.effect_sink(replace(exited, stage=ScratchStage.FAILED))
            raise ProviderStateError("Codex scratch process exited non-zero")
        try:
            postflight = self.security_policy.prepare_and_check(
                scratch, request.context.allowed_paths, create_parents=False)
        except Exception:
            self.effect_sink(replace(
                exited, stage=ScratchStage.RECONCILIATION_REQUIRED,
                updated_at=datetime.now(timezone.utc)))
            raise
        if (preflight.mode == ScratchWorkspaceSecurityMode.WINDOWS_CURRENT_USER
                and postflight.explicit_deny_detected):
            self.effect_sink(replace(exited, stage=ScratchStage.RECONCILIATION_REQUIRED))
            raise ProviderStateError("Windows postflight detected an explicit deny ACL")
        self.effect_sink(replace(exited, stage=ScratchStage.OBSERVATION_STARTED))
        try:
            manifest, operations = self._observe(
                request, scratch, identity, baseline_commit,
                baseline_tree, command, started, completed)
        except Exception:
            self.effect_sink(replace(
                exited, stage=ScratchStage.RECONCILIATION_REQUIRED,
                updated_at=datetime.now(timezone.utc)))
            raise
        self.manifest_sink(manifest)
        persisted = replace(exited, stage=ScratchStage.MANIFEST_PERSISTED,
                            manifest_digest=manifest.manifest_digest)
        self.effect_sink(persisted)
        identifier = f"codex-scratch-{request.provider_operation_id}"
        result = ProviderTaskResult(
            identifier, request.external_task_id, request.workspace_id, request.branch,
            ProviderResultStatus.SUCCEEDED, summary, operations,
            ("Observed disposable workspace changes",), (manifest.manifest_digest,), (), (),
            (1,), False, ProviderUsage(duration_seconds=command.duration_seconds,
                                       model=self.configuration.model))
        serialized = json.dumps(asdict(result), sort_keys=True, separators=(",", ":"),
                                default=str).encode()
        receipt = ProviderResponseReceipt(
            request.provider_operation_id, identifier, request.external_task_id,
            self.provider_id, request.project_id, request.execution_plan_id,
            request.plan_version, request.managed_task_id, request.workspace_id, request.branch,
            request.request_digest, request.context_digest, request.provider_idempotency_key,
            hashlib.sha256(serialized).hexdigest(), completed, result.usage, 1,
            "CODEX_CLI_DISPOSABLE_WORKSPACE", self.cli_version, self.configuration.model,
            manifest.manifest_digest, manifest.changed_paths, started, completed, "SUCCEEDED")
        self.effect_sink(replace(persisted, stage=ScratchStage.RESULT_CONVERTED))
        self.response_sink(receipt, result)
        self.effect_sink(replace(persisted, stage=ScratchStage.RESULT_ACCEPTED))
        progress = (ProviderProgressEvent(request.provider_operation_id, 1, "RESULT_AVAILABLE",
                                          "Observed scratch manifest converted", completed),)
        self._tasks[identifier] = (request, progress, result)
        self._keys[request.provider_idempotency_key] = identifier
        self._cleanup(scratch)
        self.effect_sink(replace(persisted, stage=ScratchStage.CLEANUP_COMPLETED,
                                 scratch_path=""))
        return identifier

    @staticmethod
    def _cleanup(path):
        def writable(function, target, error):
            os.chmod(target, 0o700)
            function(target)
        shutil.rmtree(path, onerror=writable)

    def _prepare(self, request):
        root = Path(self.configuration.scratch_root).resolve()
        identity = f"scratch-{request.provider_operation_id}-{secrets.token_hex(6)}"
        destination = secure_destination(root, identity)
        if destination.exists():
            raise ProviderStateError("Scratch workspace already exists")
        source = Path(self.configuration.source_workspace).resolve()

        def ignored(path, names):
            rejected = []
            for name in names:
                lower = name.casefold()
                if lower in _EXCLUDED or lower.startswith(".env") or lower.startswith(".ascos"):
                    rejected.append(name)
            return rejected

        shutil.copytree(source, destination, ignore=ignored, symlinks=False)
        for path in destination.rglob("*"):
            if path.is_symlink():
                raise ProviderStateError("Scratch baseline contains a link")
        for remote in self._git(destination, "remote").stdout.splitlines():
            self._git(destination, "remote", "remove", remote)
        if self._git(destination, "status", "--porcelain", "--untracked-files=all").stdout:
            raise ProviderStateError("Scratch baseline is not clean")
        return destination, identity

    def _observe(self, request, scratch, identity, baseline_commit, baseline_tree,
                 command, started, completed):
        if self._git(scratch, "rev-parse", "HEAD").stdout.strip() != baseline_commit:
            raise ProviderStateError("Codex changed Git commit metadata")
        status = self._git(scratch, "status", "--porcelain", "--untracked-files=all").stdout
        entries = [line for line in status.splitlines() if line]
        paths = tuple(sorted(line[3:].replace("\\", "/") for line in entries))
        if not paths:
            raise ProviderStateError("Codex implementation produced no observed changes")
        if len(paths) > self.configuration.maximum_changed_files:
            raise ProviderStateError("Codex changed too many scratch paths")
        if any(not allowed_path(path, request.context.allowed_paths,
                                request.context.forbidden_paths) for path in paths):
            raise ProviderStateError("Codex changed a path outside approved scope")
        created, modified, deleted, files, operations = [], [], [], [], []
        additions = deletions = patch_bytes = resulting_bytes = 0
        source = Path(self.configuration.source_workspace).resolve()
        for line, path in zip(sorted(entries, key=lambda value: value[3:]), paths):
            target, prior = scratch / path, source / path
            if target.is_symlink():
                raise ProviderStateError("Codex introduced a link or reparse point")
            kind = "DELETE" if line[:2].strip() == "D" else ("CREATE" if line.startswith("??") else "UPDATE")
            if kind == "DELETE" and not getattr(request.context, "allows_deletions", False):
                raise ProviderStateError("Codex deleted an unapproved file")
            prior_raw = prior.read_bytes() if prior.is_file() else None
            raw = target.read_bytes() if target.is_file() else None
            if raw is not None and (b"\0" in raw or len(raw) > self.configuration.maximum_file_bytes):
                raise ProviderStateError("Codex created binary or oversized content")
            try: content = raw.decode("utf-8") if raw is not None else ""
            except UnicodeDecodeError as error: raise ProviderStateError("Codex content is not UTF-8") from error
            if _SECRET.search(content):
                raise ProviderStateError("Codex introduced credential-shaped content")
            prior_digest = hashlib.sha256(prior_raw).hexdigest() if prior_raw is not None else None
            result_digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
            files.append(ObservedCodexFile(path, kind, prior_digest, result_digest, True))
            (created if kind == "CREATE" else modified if kind == "UPDATE" else deleted).append(path)
            additions += len(content.splitlines()) if kind != "DELETE" else 0
            deletions += len(prior_raw.decode("utf-8").splitlines()) if kind == "DELETE" and prior_raw else 0
            patch_bytes += len(raw or b"") + len(prior_raw or b"")
            resulting_bytes += len(raw or b"")
            operations.append(FileOperation(FileOperationKind(kind), path,
                                            content if kind != "DELETE" else None, prior_digest))
        if patch_bytes > self.configuration.maximum_total_patch_bytes:
            raise ProviderStateError("Observed Codex patch exceeded limit")
        diff = self._git(scratch, "diff", "--no-ext-diff", "--binary").stdout
        observed_payload = (status + diff + json.dumps([asdict(item) for item in files],
                                                       sort_keys=True)).encode()
        values = dict(
            schema_version=1, operation_id=request.provider_operation_id,
            provider_id=self.provider_id, cli_version=self.cli_version,
            model=self.configuration.model, scratch_workspace_id=identity,
            baseline_commit_sha=baseline_commit, baseline_tree_digest=baseline_tree,
            exit_code=command.exit_code, started_at=started, completed_at=completed,
            changed_paths=paths, created_paths=tuple(created), modified_paths=tuple(modified),
            deleted_paths=tuple(deleted), files=tuple(files),
            git_diff_digest=hashlib.sha256(observed_payload).hexdigest(), additions=additions,
            deletions=deletions, total_patch_bytes=patch_bytes,
            total_resulting_content_bytes=resulting_bytes,
            workspace_classification="OBSERVED_APPROVED_CHANGES",
            prohibited_paths_passed=True, symlink_reparse_passed=True, manifest_digest="")
        manifest_digest = hashlib.sha256(json.dumps(
            values, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return ObservedCodexPatchManifest(**{**values, "manifest_digest": manifest_digest}), tuple(operations)

    def _tree_digest(self, root):
        output = self._git(root, "ls-files", "-s").stdout
        return hashlib.sha256(output.encode()).hexdigest()

    def _git(self, root, *arguments):
        result = self.runner.execute(CommandRequest("git", tuple(arguments), root, {}, 60))
        if result.exit_code:
            raise ProviderStateError("Scratch Git observation failed")
        return result

    def _prompt(self, request):
        return (
            "This is an implementation task. Modify the current scratch workspace now. "
            f"Objective: {request.context.objective}. Allowed paths: {request.context.allowed_paths}. "
            f"Prohibited paths: {request.context.forbidden_paths}. Acceptance criteria: "
            f"{request.context.acceptance_criteria}. Do not merely explain or propose the change. "
            "Do not change any other path. Do not run Git commit, push, PR, merge, approval, or "
            "deployment operations. Do not access credentials. Stop after making the approved edits."
        )

    def get_task_status(self, identifier): return self.get_task_result(identifier).status
    def get_task_progress(self, identifier): return self._tasks[identifier][1]
    def get_task_result(self, identifier): return self._tasks[identifier][2]
    def get_task_identity(self, identifier): return self._tasks[identifier][0]
    def cancel_task(self, identifier): raise ProviderStateError("Synchronous scratch task ended")
    def reconcile_task(self, idempotency_key, provider_task_id=None):
        found = self._keys.get(idempotency_key)
        return (found,) if found and (provider_task_id is None or found == provider_task_id) else ()
