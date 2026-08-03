import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.coding_providers import (
    CodexScratchCodingProvider, CodexScratchConfiguration, ProviderStateError,
    ScratchStage,
)
from runtime.tools.models import CommandResult


def run_git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True)


def source_repo(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    run_git(source, "init", "-b", "agent/smoke")
    run_git(source, "config", "user.email", "fixture@example.invalid")
    run_git(source, "config", "user.name", "ASCOS Fixture")
    (source / "README.md").write_text("fixture\n", encoding="utf-8")
    run_git(source, "add", "README.md")
    run_git(source, "commit", "-m", "fixture baseline")
    return source


class FakeRunner:
    def __init__(self, mutation="valid", exit_code=0):
        self.mutation = mutation
        self.exit_code = exit_code
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        now = datetime.now(timezone.utc)
        if request.executable == "git":
            value = subprocess.run(["git", *request.arguments], cwd=request.working_directory,
                                   capture_output=True, text=True)
            return CommandResult("git", request.arguments, value.returncode, value.stdout,
                                 value.stderr, now, now, 0.01, False)
        if request.arguments == ("--version",):
            return CommandResult("codex.cmd", request.arguments, 0, "codex-cli 0.146.0",
                                 "", now, now, 0.01, False)
        root = Path(request.working_directory)
        if self.mutation in {"valid", "extra", "binary", "symlink"}:
            target = root / "docs" / "ascos-codex-smoke.txt"
            target.parent.mkdir(exist_ok=True)
            if self.mutation == "binary":
                target.write_bytes(b"ok\0bad")
            elif self.mutation == "symlink":
                target.symlink_to(root / "README.md")
            else:
                target.write_text("ASCOS_CODEX_PROVIDER_SMOKE_TEST_OK\n", encoding="utf-8")
        if self.mutation == "extra":
            (root / "unexpected.txt").write_text("unexpected", encoding="utf-8")
        output = Path(request.arguments[request.arguments.index("--output-last-message") + 1])
        output.write_text("bounded summary", encoding="utf-8")
        return CommandResult("codex.cmd", request.arguments, self.exit_code, "", "",
                             now, now, 0.02, False)


def provider(tmp_path, mutation="valid", exit_code=0):
    source = source_repo(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    receipts, results, manifests, effects = [], [], [], []
    item = CodexScratchCodingProvider(CodexScratchConfiguration(
        enabled=True, source_workspace=str(source), scratch_root=str(scratch)),
        runner=FakeRunner(mutation, exit_code),
        response_sink=lambda receipt, result: (receipts.append(receipt), results.append(result)),
        manifest_sink=manifests.append, effect_sink=effects.append)
    return item, receipts, results, manifests, effects


def request():
    context = SimpleNamespace(
        objective="Create exact smoke file",
        acceptance_criteria=("exact content",),
        allowed_paths=("docs/ascos-codex-smoke.txt",),
        forbidden_paths=(".git", ".env"), allows_deletions=False,
    )
    return SimpleNamespace(
        provider_operation_id="scratch-operation-1", provider_idempotency_key="scratch-key-1",
        external_task_id="external-1", project_id="fixture", execution_plan_id="plan-1",
        plan_version=1, managed_task_id="task-1", workspace_id="final-workspace",
        branch="agent/final", request_digest="a" * 64, context_digest="b" * 64,
        context=context, timeout_seconds=60, maximum_output_bytes=96_000,
    )


def test_valid_observed_manifest_receipt_and_cleanup(tmp_path):
    item, receipts, results, manifests, effects = provider(tmp_path)
    identifier = item.submit_task(request())
    assert item.submit_task(request()) == identifier
    assert manifests[0].changed_paths == ("docs/ascos-codex-smoke.txt",)
    assert manifests[0].created_paths == manifests[0].changed_paths
    assert receipts[0].structured_result_digest == manifests[0].manifest_digest
    assert results[0].file_operations[0].content.rstrip() == "ASCOS_CODEX_PROVIDER_SMOKE_TEST_OK"
    assert effects[-1].stage == ScratchStage.CLEANUP_COMPLETED
    assert not tuple((tmp_path / "scratch").iterdir())


@pytest.mark.parametrize("mutation, message", [
    ("none", "no observed changes"), ("extra", "outside approved scope"),
    ("binary", "binary"),
])
def test_invalid_observed_changes_are_rejected_and_retained(tmp_path, mutation, message):
    item, receipts, _, _, effects = provider(tmp_path, mutation)
    with pytest.raises(ProviderStateError, match=message):
        item.submit_task(request())
    assert receipts == []
    assert effects[-1].stage == ScratchStage.RECONCILIATION_REQUIRED
    assert tuple((tmp_path / "scratch").iterdir())


def test_symlink_change_is_rejected_where_supported(tmp_path):
    item, receipts, _, _, _ = provider(tmp_path, "symlink")
    try:
        with pytest.raises(ProviderStateError, match="link"):
            item.submit_task(request())
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("symlink privilege unavailable")
        raise
    assert receipts == []


def test_nonzero_exit_with_partial_change_is_not_converted(tmp_path):
    item, receipts, _, manifests, effects = provider(tmp_path, "valid", exit_code=1)
    with pytest.raises(ProviderStateError, match="non-zero"):
        item.submit_task(request())
    assert receipts == [] and manifests == []
    assert effects[-1].stage == ScratchStage.FAILED


def test_prompt_forbids_privileged_external_effects(tmp_path):
    item, *_ = provider(tmp_path)
    item.submit_task(request())
    invocation = next(call for call in item.runner.requests
                      if call.executable == "codex.cmd" and call.arguments != ("--version",))
    prompt = invocation.arguments[-1]
    for word in ("commit", "push", "PR", "merge", "approval", "deployment", "credentials"):
        assert word in prompt
    assert 'approval_policy="never"' in invocation.arguments


def test_windows_policy_precreates_parent_and_preserves_observer_access(tmp_path):
    from runtime.coding_providers import (
        ScratchWorkspaceSecurityMode, ScratchWorkspaceSecurityPolicy,
    )
    root = tmp_path / "workspace"
    (root / ".git").mkdir(parents=True)
    policy = ScratchWorkspaceSecurityPolicy(
        ScratchWorkspaceSecurityMode.WINDOWS_CURRENT_USER,
        acl_reader=lambda _: "inherited-current-user-read")
    if __import__("os").name != "nt":
        with pytest.raises(Exception, match="requires Windows"):
            policy.prepare_and_check(root, ("docs/file.txt",), create_parents=True)
        return
    snapshot = policy.prepare_and_check(root, ("docs/file.txt",), create_parents=True)
    assert snapshot.root_accessible and snapshot.git_accessible
    assert snapshot.approved_parents_accessible and snapshot.probe_passed
    assert not snapshot.explicit_deny_detected
    assert (root / "docs").is_dir()


def test_explicit_deny_is_classified_without_acl_mutation(tmp_path):
    from runtime.coding_providers import ScratchWorkspaceSecurityPolicy
    root = tmp_path / "workspace"
    (root / ".git").mkdir(parents=True)
    policy = ScratchWorkspaceSecurityPolicy(acl_reader=lambda _: "identity:(DENY_OBSERVER)(W)")
    snapshot = policy.prepare_and_check(root, ("docs/file.txt",), create_parents=True)
    assert snapshot.explicit_deny_detected
