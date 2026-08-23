from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import stat
import subprocess

import pytest

from runtime.product_workspace import (
    ARTIFACT_STATUS,
    BRANCH_STATE,
    PILOT_STATUS,
    SOURCE_STATE,
    WORKSPACE_ACTIONS,
    WORKSPACE_CAPABILITIES,
    WORKSPACE_STATE,
    WORKSPACE_TOOL_IDS,
    FileProductWorkspaceArtifactStore,
    LocalGitWorktreeProvider,
    ProductWorkspaceAuthority,
    ProductWorkspaceConflict,
    ProductWorkspaceCorrupt,
    ProductWorkspacePolicyError,
    ProductWorkspaceReconciliationRequired,
    ProductWorkspaceService,
    ProductWorkspaceWorkOrder,
    WorkspacePreparationObservation,
)
from runtime.workforce_orchestration import FileOrchestrationArtifactStore
from tests.test_workforce_leadership import NOW
from tests.test_workforce_orchestration import _run_orchestration


REPOSITORY_IDENTITY = "https://example.invalid/ascos-fixture-product.git"


def _git(path: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=path,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def _source_repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "fixture-product"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.email", "fixture@example.invalid")
    _git(source, "config", "user.name", "ASCOS Fixture")
    (source / "app.py").write_text("def value():\n    return 31\n", encoding="utf-8")
    (source / "README.md").write_text("# Generic product fixture\n", encoding="utf-8")
    _git(source, "add", "app.py", "README.md")
    _git(source, "commit", "-m", "Approved generic base")
    _git(source, "remote", "add", "origin", REPOSITORY_IDENTITY)
    return source, _git(source, "rev-parse", "HEAD")


def _work_order(orchestration, base_commit: str, **changes) -> ProductWorkspaceWorkOrder:
    values = {
        "work_order_id": "work-order-isolated-product-workspace-1",
        "tenant_id": orchestration.tenant_id,
        "opportunity_id": orchestration.opportunity_id,
        "assignment_id": "assignment-isolated-product-workspace-1",
        "orchestration_artifact_digest": orchestration.digest,
        "repository_id": "generic-product-fixture",
        "repository_identity": REPOSITORY_IDENTITY,
        "base_branch": "main",
        "expected_base_commit": base_commit,
        "feature_branch": "agent/day31-generic-product-workspace",
        "workspace_id": "workspace-day31-generic-product",
        "objectives": (
            "Verify the exact approved product base",
            "Create one isolated Git worktree",
            "Create one protected feature branch at the exact base",
            "Prove the approved source and unrelated work remain unchanged",
        ),
        "acceptance_checks": (
            "The orchestration source matches persisted Day 30 state",
            "The source repository identity and base commit are exact",
            "The source repository is clean before and after preparation",
            "The workspace is contained under the caller-owned root",
            "The feature branch and workspace head equal the approved base",
            "No source product file or unrelated path is changed",
            "No network or general command capability is used",
            "No coding, commit, push, pull request, deployment, or release occurs",
        ),
        "constraints": (
            "One generic fixture workspace only",
            "No official pilot product selection",
            "No symbolic links, submodules, executable Git hooks, or custom filters",
            "No source product-file mutation or unrelated-path mutation",
            "No network, credentials, general command runner, or live provider",
            "No coding, QA execution, Security scan, commit, push, pull request, merge, deployment, or release",
        ),
        "issued_at": NOW + timedelta(minutes=60),
    }
    values.update(changes)
    return ProductWorkspaceWorkOrder(**values)


def _authority(order: ProductWorkspaceWorkOrder, **changes) -> ProductWorkspaceAuthority:
    values = {
        "authority_id": "authority-isolated-product-workspace-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "work_order_digest": order.digest,
        "orchestration_artifact_digest": order.orchestration_artifact_digest,
        "allowed_action_ids": WORKSPACE_ACTIONS,
        "allowed_tool_ids": WORKSPACE_TOOL_IDS,
        "issued_at": NOW + timedelta(minutes=55),
        "expires_at": NOW + timedelta(hours=4),
        "max_workspaces": 1,
        "max_tool_calls": 24,
        "network_allowed": False,
        "source_file_writes_allowed": False,
        "workspace_file_mutation_allowed": False,
    }
    values.update(changes)
    return ProductWorkspaceAuthority(**values)


def _fixture(tmp_path: Path, provider=None):
    *_, orchestration = _run_orchestration(tmp_path)
    source, base_commit = _source_repository(tmp_path)
    order = _work_order(orchestration, base_commit)
    authority = _authority(order)
    selected = provider or LocalGitWorktreeProvider(tmp_path / "product-workspaces")
    service = ProductWorkspaceService(
        selected,
        orchestration_store=FileOrchestrationArtifactStore(tmp_path / "orchestration-state"),
        store=FileProductWorkspaceArtifactStore(tmp_path / "product-workspace-state"),
        clock=lambda: NOW + timedelta(minutes=65),
    )
    return service, selected, orchestration, source, order, authority


def _run_workspace(tmp_path: Path, *, provider=None):
    service, selected, orchestration, source, order, authority = _fixture(tmp_path, provider)
    artifact = service.run(
        execution_id="execution-isolated-product-workspace-1",
        work_order=order,
        authority=authority,
        orchestration_artifact=orchestration,
        source_repository=source,
    )
    return service, selected, orchestration, source, order, authority, artifact


def test_workspace_is_exact_isolated_clean_and_source_preserving(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, _, artifact = _run_workspace(tmp_path)
    target = provider.root / order.workspace_id
    assert provider.execution_count == 1
    assert target.is_dir() and target != source
    assert _git(source, "branch", "--show-current") == "main"
    assert _git(source, "rev-parse", "HEAD") == order.expected_base_commit
    assert _git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert _git(target, "branch", "--show-current") == order.feature_branch
    assert _git(target, "rev-parse", "HEAD") == order.expected_base_commit
    assert _git(target, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert artifact.orchestration_artifact_digest == orchestration.digest
    assert artifact.workspace_head == artifact.base_commit == order.expected_base_commit
    assert artifact.workspace_tree == artifact.base_tree
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS
    assert artifact.source_state == SOURCE_STATE
    assert artifact.workspace_state == WORKSPACE_STATE
    assert artifact.branch_state == BRANCH_STATE
    assert artifact.capability_ids == WORKSPACE_CAPABILITIES
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_exact_retry_and_restart_do_not_repeat_git_effect(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority, expected = _run_workspace(tmp_path)
    kwargs = dict(
        execution_id=expected.execution_id,
        work_order=order,
        authority=authority,
        orchestration_artifact=orchestration,
        source_repository=source,
    )
    again = service.run(**kwargs)
    restarted_provider = LocalGitWorktreeProvider(provider.root)
    restarted = ProductWorkspaceService(
        restarted_provider,
        service._orchestration_store,
        service._store,
        clock=lambda: NOW + timedelta(minutes=70),
    )
    reopened = restarted.run(**kwargs)
    assert again == reopened == expected
    assert provider.execution_count == 1 and restarted_provider.execution_count == 0


def test_changed_retry_conflicts_without_second_git_effect(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority, artifact = _run_workspace(tmp_path)
    changed = replace(order, workspace_id="workspace-day31-changed")
    with pytest.raises(ProductWorkspaceConflict):
        service.run(
            execution_id=artifact.execution_id,
            work_order=changed,
            authority=_authority(changed),
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    assert provider.execution_count == 1


def test_orchestration_substitution_and_authority_drift_fail_before_git(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority = _fixture(tmp_path)
    changed = replace(order, orchestration_artifact_digest="0" * 64)
    with pytest.raises(ProductWorkspacePolicyError):
        service.run(
            execution_id="execution-invalid-source",
            work_order=changed,
            authority=_authority(changed),
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    with pytest.raises(ProductWorkspacePolicyError):
        service.run(
            execution_id="execution-invalid-authority",
            work_order=order,
            authority=replace(authority, assignment_id="assignment-wrong"),
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    assert provider.execution_count == 0


def test_dirty_source_is_rejected_without_workspace_or_branch(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority = _fixture(tmp_path)
    (source / "unrelated.txt").write_text("do not touch", encoding="utf-8")
    with pytest.raises(ProductWorkspacePolicyError):
        service.run(
            execution_id="execution-dirty-source",
            work_order=order,
            authority=authority,
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    assert not (provider.root / order.workspace_id).exists()
    assert _git(source, "show-ref", "--verify", f"refs/heads/{order.feature_branch}", check=False) == ""
    assert (source / "unrelated.txt").read_text() == "do not touch"


@pytest.mark.parametrize(
    "change",
    (
        {"expected_base_commit": "1" * 40},
        {"repository_identity": "https://example.invalid/wrong.git"},
        {"base_branch": "different"},
    ),
)
def test_wrong_base_branch_commit_or_repository_identity_fails_closed(tmp_path: Path, change) -> None:
    service, provider, orchestration, source, order, _ = _fixture(tmp_path)
    changed = replace(order, **change)
    with pytest.raises(ProductWorkspacePolicyError):
        service.run(
            execution_id="execution-wrong-base",
            work_order=changed,
            authority=_authority(changed),
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    assert not (provider.root / changed.workspace_id).exists()


def test_existing_destination_or_branch_requires_reconciliation(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority = _fixture(tmp_path)
    target = provider.root / order.workspace_id
    target.mkdir(parents=True)
    with pytest.raises(ProductWorkspaceReconciliationRequired):
        service.run(
            execution_id="execution-existing-target",
            work_order=order,
            authority=authority,
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    target.rmdir()
    _git(source, "branch", order.feature_branch, order.expected_base_commit)
    with pytest.raises(ProductWorkspaceReconciliationRequired):
        service.run(
            execution_id="execution-existing-branch",
            work_order=order,
            authority=authority,
            orchestration_artifact=orchestration,
            source_repository=source,
        )


def test_symlink_destination_is_rejected(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority = _fixture(tmp_path)
    provider.root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (provider.root / order.workspace_id).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ProductWorkspaceReconciliationRequired):
        service.run(
            execution_id="execution-symlink-target",
            work_order=order,
            authority=authority,
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    assert not (outside / "app.py").exists()


def test_tracked_symlink_or_custom_filter_is_rejected_before_checkout(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority = _fixture(tmp_path)
    target = source / "unsafe-link"
    try:
        target.symlink_to(source / "app.py")
    except OSError:
        pytest.skip("symlinks are unavailable")
    _git(source, "add", "unsafe-link")
    _git(source, "commit", "-m", "unsafe tree")
    changed = replace(order, expected_base_commit=_git(source, "rev-parse", "HEAD"))
    with pytest.raises(ProductWorkspacePolicyError):
        service.run(
            execution_id="execution-unsafe-tree",
            work_order=changed,
            authority=_authority(changed),
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    assert not (provider.root / order.workspace_id).exists()


def test_executable_git_configuration_is_rejected(tmp_path: Path) -> None:
    service, provider, orchestration, source, order, authority = _fixture(tmp_path)
    _git(source, "config", "filter.unsafe.smudge", "touch should-not-run")
    with pytest.raises(ProductWorkspacePolicyError):
        service.run(
            execution_id="execution-unsafe-config",
            work_order=order,
            authority=authority,
            orchestration_artifact=orchestration,
            source_repository=source,
        )
    assert not (provider.root / order.workspace_id).exists()


class _DriftingProvider:
    provider_id = "drifting-workspace-provider"

    def prepare(self, source_repository, work_order, authority):
        return WorkspacePreparationObservation(
            provider_id=self.provider_id,
            workspace_relative_path=work_order.workspace_id,
            source_branch_before=work_order.base_branch,
            source_branch_after=work_order.base_branch,
            source_head_before=work_order.expected_base_commit,
            source_head_after=work_order.expected_base_commit,
            source_tree_before="a" * 40,
            source_tree_after="a" * 40,
            workspace_branch=work_order.feature_branch,
            workspace_head=work_order.expected_base_commit,
            workspace_tree="b" * 40,
            source_clean_before=True,
            source_clean_after=True,
            workspace_clean=True,
            branch_created=True,
            workspace_created=True,
            git_command_count=19,
            network_call_count=0,
            general_command_count=0,
            product_file_write_count=0,
            unrelated_path_change_count=0,
        )


def test_provider_cannot_report_workspace_tree_drift(tmp_path: Path) -> None:
    service, _, orchestration, source, order, authority = _fixture(
        tmp_path, _DriftingProvider()
    )
    with pytest.raises(ProductWorkspacePolicyError):
        service.run(
            execution_id="execution-provider-drift",
            work_order=order,
            authority=authority,
            orchestration_artifact=orchestration,
            source_repository=source,
        )


def test_persistence_is_mode_0600_closed_and_tamper_evident(tmp_path: Path) -> None:
    service, _, _, _, _, _, artifact = _run_workspace(tmp_path)
    directory = (
        tmp_path / "product-workspace-state" / artifact.tenant_id / artifact.execution_id
    )
    path = directory / "isolated-product-workspace-v1.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = json.loads(path.read_text())
    envelope["record"]["workspace_state"] = "USED"
    path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    os.chmod(path, 0o600)
    with pytest.raises(ProductWorkspaceCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)


def test_persistence_rejects_unknown_entries_and_unsafe_permissions(tmp_path: Path) -> None:
    service, _, _, _, _, _, artifact = _run_workspace(tmp_path)
    directory = (
        tmp_path / "product-workspace-state" / artifact.tenant_id / artifact.execution_id
    )
    path = directory / "isolated-product-workspace-v1.json"
    (directory / "unexpected.txt").write_text("unsafe")
    with pytest.raises(ProductWorkspaceCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)
    (directory / "unexpected.txt").unlink()
    os.chmod(path, 0o644)
    with pytest.raises(ProductWorkspaceCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)


def test_artifact_store_rejects_path_escape(tmp_path: Path) -> None:
    store = FileProductWorkspaceArtifactStore(tmp_path / "state")
    with pytest.raises(ProductWorkspaceCorrupt):
        store.load("../tenant", "execution")


def test_model_rejects_protected_feature_branch_and_local_path_identity(tmp_path: Path) -> None:
    *_, orchestration = _run_orchestration(tmp_path)
    source, base = _source_repository(tmp_path)
    assert source.is_dir()
    with pytest.raises(ValueError):
        _work_order(orchestration, base, feature_branch="main")
    with pytest.raises(ValueError):
        _work_order(orchestration, base, repository_identity=str(source))
