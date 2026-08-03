"""Operator-invoked real Codex CLI fixture; never targets a product repository."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from runtime.coding_providers import (
    CodingContextBuilder, CodingProviderRegistry, CodingProviderService,
    CodexCliCodingProvider, CodexCliProviderConfiguration, ContextLimits,
    ControlledPatchApplier, ProviderOperationStore,
    CodexScratchCodingProvider, CodexScratchConfiguration,
)
from runtime.integrations.git.models import GitStatus
from runtime.managed_execution import ChangePolicy
from runtime.tools.command_runner import LocalCommandRunner
from runtime.tools.models import CommandRequest


EXPECTED_PATH = "docs/ascos-codex-smoke.txt"
EXPECTED_CONTENT = "ASCOS_CODEX_PROVIDER_SMOKE_TEST_OK"


class FixtureGitObserver:
    def __init__(self, root: Path):
        self.root = root

    def status(self, path):
        changed = tuple(sorted(
            item.relative_to(self.root).as_posix()
            for item in self.root.rglob("*")
            if item.is_file() and ".git" not in item.parts
            and ".ascos-provider-staging" not in item.parts))
        return GitStatus("agent/codex-live-smoke", not changed, changed)

    def current_commit(self, path):
        return "fixture-base-sha"

    def diff(self, path):
        target = self.root / EXPECTED_PATH
        return target.read_text(encoding="utf-8") if target.is_file() else ""

    def diff_numstat(self, path):
        target = self.root / EXPECTED_PATH
        return (1, 0) if target.is_file() else (0, 0)


class RunnerGitObserver:
    def __init__(self, root, runner):
        self.root, self.runner = root, runner

    def _git(self, *arguments):
        result = self.runner.execute(CommandRequest("git", tuple(arguments), self.root, {}, 60))
        if result.exit_code:
            raise RuntimeError("Fixture Git observation failed")
        return result.stdout

    def status(self, path):
        output = self._git("status", "--porcelain", "--untracked-files=all")
        changed = tuple(line[3:].replace("\\", "/") for line in output.splitlines() if line)
        return GitStatus(self._git("branch", "--show-current").strip(), not changed, changed)

    def current_commit(self, path):
        return self._git("rev-parse", "HEAD").strip()

    def diff(self, path):
        target = self.root / EXPECTED_PATH
        return self._git("diff", "--no-ext-diff") + (
            target.read_text(encoding="utf-8") if target.is_file() else "")

    def diff_numstat(self, path):
        return (1, 0) if (self.root / EXPECTED_PATH).is_file() else (0, 0)


def _persist_json(root, name, value):
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{name}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(value), sort_keys=True, indent=2,
                                    default=str), encoding="utf-8")
    temporary.replace(target)


def run_live_fixture(state_root: str | Path) -> dict[str, object]:
    """Run one live bounded request and return secret-free observed evidence."""
    with TemporaryDirectory(prefix="ascos-codex-live-") as directory:
        workspace = Path(directory).resolve()
        state = Path(state_root).resolve()
        allowed_environment = {
            key: os.environ[key]
            for key in CodexCliProviderConfiguration().environment_allow_list
            if key in os.environ
        }
        runner = LocalCommandRunner(
            workspace, allowed_executables={"codex.cmd", "git"},
            allowed_environment=set(), max_output_bytes=128_000,
            base_environment=allowed_environment)
        initialized = runner.execute(CommandRequest(
            "git", ("init", "-b", "agent/codex-live-smoke"), workspace, {}, 30))
        if initialized.exit_code:
            raise RuntimeError("Could not initialize the live fixture Git repository")
        store = ProviderOperationStore(state)
        provider = CodexCliCodingProvider(CodexCliProviderConfiguration(
            enabled=True, allowed_workspace_root=str(workspace), health_smoke_test=True),
            runner=runner,
            response_sink=lambda receipt, result: (
                store.save_result(receipt.project_id, receipt.provider_operation_id, result),
                store.save_receipt(receipt),
            ))
        registry = CodingProviderRegistry((provider,))
        plan = SimpleNamespace(
            project_id="codex-live-fixture", execution_plan_id="codex-cli-smoke-v2",
            version=1, workspace_identity="codex-live-fixture-workspace",
            feature_branch="agent/codex-live-smoke")
        task = SimpleNamespace(
            project_task_id="create-smoke-file",
            objective=f"Create only {EXPECTED_PATH} with exact content {EXPECTED_CONTENT}",
            acceptance_criteria=(f"The complete file content is exactly {EXPECTED_CONTENT}",),
            allowed_paths=(EXPECTED_PATH,), forbidden_paths=(".git", ".env"),
            allowed_commands=(), candidate_files=(), allows_no_change_success=False,
            allows_deletions=False)
        coding_request = SimpleNamespace(
            external_task_id="codex-cli-smoke-v2-create-smoke-file-attempt-1",
            timeout_seconds=600)
        observer = FixtureGitObserver(workspace)
        service = CodingProviderService(
            registry, store, CodingContextBuilder(ContextLimits()),
            ControlledPatchApplier(maximum_patch_bytes=1_024,
                                   maximum_file_bytes=1_024),
            change_policies=(ChangePolicy(
                "codex-smoke", (EXPECTED_PATH,), (".git", ".env"),
                maximum_changed_files=1, maximum_additions=1, maximum_deletions=0),),
            git_provider_factory=lambda _: observer)
        operation, request = service.prepare(
            plan=plan, task=task, coding_request=coding_request,
            workspace_path=workspace, provider_id="codex-cli",
            maximum_output_bytes=96_000, maximum_attempts=1)
        submitted = service.submit(
            plan.project_id, operation.provider_operation_id, request,
            allow_live_provider=True)
        service.poll(plan.project_id, operation.provider_operation_id)
        service.result(plan.project_id, operation.provider_operation_id,
                       token_budget=32_000)
        accepted, manifest = service.apply_and_accept(
            plan.project_id, operation.provider_operation_id,
            workspace_path=workspace, task=task, policy_id="codex-smoke")
        duplicate = provider.submit_task(request)
        target = workspace / EXPECTED_PATH
        raw_content = target.read_text(encoding="utf-8")
        content = raw_content.rstrip("\r\n")
        paths = observer.status(workspace).changed_paths
        if content != EXPECTED_CONTENT or paths != (EXPECTED_PATH,):
            raise RuntimeError("Live fixture independent verification failed")
        receipt = store.load_receipt(plan.project_id, operation.provider_operation_id)
        return {
            "provider_id": provider.provider_id,
            "cli_version": provider.cli_version,
            "model": provider.configuration.model,
            "operation_id": operation.provider_operation_id,
            "provider_task_id": submitted.provider_task_id,
            "receipt_id": receipt.provider_operation_id,
            "receipt_digest": receipt.response_digest,
            "manifest_digest": manifest.manifest_digest,
            "changed_paths": paths,
            "content_digest": hashlib.sha256(content.encode()).hexdigest(),
            "duplicate_suppressed": duplicate == submitted.provider_task_id,
            "usage_available": receipt.usage.total_units is not None,
            "terminal_status": accepted.state.value,
            "fixture_cleaned_after_return": True,
        }


def run_live_scratch_fixture(state_root: str | Path) -> dict[str, object]:
    """Run the one authorized disposable-workspace mutation smoke test."""
    with TemporaryDirectory(prefix="ascos-codex-scratch-") as directory:
        root = Path(directory).resolve()
        source, scratch = root / "approved-baseline", root / "scratch"
        source.mkdir()
        scratch.mkdir()
        allowed_environment = {
            key: os.environ[key]
            for key in CodexCliProviderConfiguration().environment_allow_list
            if key in os.environ
        }
        runner = LocalCommandRunner(
            root, allowed_executables={"codex.cmd", "git"}, allowed_environment=set(),
            max_output_bytes=128_000, base_environment=allowed_environment)
        for arguments in (
            ("init", "-b", "agent/codex-scratch-smoke"),
            ("config", "user.email", "fixture@example.invalid"),
            ("config", "user.name", "ASCOS Fixture"),
        ):
            if runner.execute(CommandRequest("git", arguments, source, {}, 30)).exit_code:
                raise RuntimeError("Could not prepare scratch fixture baseline")
        (source / "README.md").write_text("ASCOS disposable fixture baseline\n", encoding="utf-8")
        for commit_arguments in (("add", "README.md"),
                                 ("commit", "-m", "fixture baseline")):
            if runner.execute(CommandRequest(
                    "git", commit_arguments, source, {}, 30)).exit_code:
                raise RuntimeError("Could not commit scratch fixture baseline")
        state = Path(state_root).resolve()
        store = ProviderOperationStore(state)
        manifests, effects = [], []

        def manifest_sink(value):
            manifests.append(value)
            _persist_json(state / "observed-manifests", value.operation_id, value)

        def effect_sink(value):
            effects.append(value)
            _persist_json(state / "scratch-effects", value.operation_id, value)

        provider = CodexScratchCodingProvider(CodexScratchConfiguration(
            enabled=True, source_workspace=str(source), scratch_root=str(scratch)),
            runner=runner,
            response_sink=lambda receipt, result: (
                store.save_result(receipt.project_id, receipt.provider_operation_id, result),
                store.save_receipt(receipt)),
            manifest_sink=manifest_sink, effect_sink=effect_sink)
        registry = CodingProviderRegistry((provider,))
        plan = SimpleNamespace(
            project_id="codex-live-fixture", execution_plan_id="codex-scratch-smoke-v3",
            version=1, workspace_identity="codex-scratch-final-workspace",
            feature_branch="agent/codex-scratch-smoke")
        task = SimpleNamespace(
            project_task_id="create-smoke-file",
            objective=("This is an implementation task. Modify the current scratch workspace "
                       f"now. Create {EXPECTED_PATH} with exactly {EXPECTED_CONTENT}."),
            acceptance_criteria=(f"Normalized complete content equals {EXPECTED_CONTENT}",),
            allowed_paths=(EXPECTED_PATH,), forbidden_paths=(".git", ".env", "README.md"),
            allowed_commands=(), candidate_files=("README.md",),
            allows_no_change_success=False, allows_deletions=False)
        coding_request = SimpleNamespace(
            external_task_id="codex-scratch-smoke-v3-create-file-attempt-1",
            timeout_seconds=600)
        observer = RunnerGitObserver(source, runner)
        service = CodingProviderService(
            registry, store, CodingContextBuilder(ContextLimits()),
            ControlledPatchApplier(maximum_patch_bytes=1_024, maximum_file_bytes=1_024),
            change_policies=(ChangePolicy(
                "codex-scratch-smoke", (EXPECTED_PATH,), (".git", ".env", "README.md"),
                maximum_changed_files=1, maximum_additions=1, maximum_deletions=0),),
            git_provider_factory=lambda _: observer)
        operation, request = service.prepare(
            plan=plan, task=task, coding_request=coding_request, workspace_path=source,
            provider_id="codex-cli-scratch", maximum_output_bytes=96_000)
        submitted = service.submit(plan.project_id, operation.provider_operation_id, request,
                                   allow_live_provider=True)
        service.poll(plan.project_id, operation.provider_operation_id)
        service.result(plan.project_id, operation.provider_operation_id, token_budget=32_000)
        accepted, applied_manifest = service.apply_and_accept(
            plan.project_id, operation.provider_operation_id, workspace_path=source,
            task=task, policy_id="codex-scratch-smoke")
        duplicate = provider.submit_task(request)
        content = (source / EXPECTED_PATH).read_text(encoding="utf-8").rstrip("\r\n")
        observed = manifests[-1]
        receipt = store.load_receipt(plan.project_id, operation.provider_operation_id)
        if content != EXPECTED_CONTENT or observed.changed_paths != (EXPECTED_PATH,):
            raise RuntimeError("Scratch fixture independent verification failed")
        return {
            "operation_id": operation.provider_operation_id,
            "provider_task_id": submitted.provider_task_id,
            "scratch_workspace_id": observed.scratch_workspace_id,
            "exit_code": observed.exit_code,
            "changed_paths": observed.changed_paths,
            "created_paths": observed.created_paths,
            "content_digest": hashlib.sha256(content.encode()).hexdigest(),
            "receipt_id": receipt.provider_operation_id,
            "receipt_digest": receipt.response_digest,
            "observed_manifest_digest": observed.manifest_digest,
            "applied_manifest_digest": applied_manifest.manifest_digest,
            "duplicate_suppressed": duplicate == submitted.provider_task_id,
            "cleanup_stage": effects[-1].stage.value,
            "usage_available": receipt.usage.total_units is not None,
            "terminal_status": accepted.state.value,
        }
