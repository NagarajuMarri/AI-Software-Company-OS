from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import stat
import subprocess

import pytest

from runtime.coding_review import (
    CodingReviewService,
    FileCodingReviewArtifactStore,
    LocalDeterministicCodingReviewProvider,
)
from runtime.github_delivery import (
    ARTIFACT_STATUS,
    BRANCH_STATE,
    DELIVERY_STATE,
    GITHUB_DELIVERY_ACTIONS,
    GITHUB_DELIVERY_CAPABILITIES,
    GITHUB_DELIVERY_TOOL_IDS,
    PILOT_STATUS,
    PULL_REQUEST_STATE,
    SOURCE_STATE,
    WORKSPACE_STATE,
    ControlledGitHubDeliveryProvider,
    DeterministicDraftPullRequestGateway,
    DraftPullRequestReceipt,
    FileGitHubDeliveryArtifactStore,
    GitHubDeliveryAuthority,
    GitHubDeliveryConflict,
    GitHubDeliveryCorrupt,
    GitHubDeliveryPolicyError,
    GitHubDeliveryReconciliationRequired,
    GitHubDeliveryService,
    GitHubDeliveryWorkOrder,
    ReviewedFileBinding,
)
from runtime.product_workspace import (
    FileProductWorkspaceArtifactStore,
    LocalGitWorktreeProvider,
    ProductWorkspaceService,
)
from runtime.workforce_orchestration import FileOrchestrationArtifactStore
from runtime.workforce_qa import FileQAArtifactStore
from runtime.workforce_security import FileSecurityArtifactStore
from tests.test_coding_review import (
    _authority as _coding_authority,
    _work_order as _coding_order,
)
from tests.test_product_workspace import (
    _authority as _workspace_authority,
    _source_repository,
    _work_order as _workspace_order,
)
from tests.test_workforce_leadership import NOW
from tests.test_workforce_orchestration import _run_orchestration


GITHUB_IDENTITY = "https://github.com/acme/ascos-fixture-product.git"
REPOSITORY_FULL_NAME = "acme/ascos-fixture-product"


def _git(path: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=path,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def _coding_fixture(tmp_path: Path):
    _, _, sources, _, _, _, orchestration = _run_orchestration(tmp_path)
    qa_artifact = sources[3]
    security_artifact = sources[4]
    source, base_commit = _source_repository(tmp_path)
    _git(source, "remote", "set-url", "origin", GITHUB_IDENTITY)
    workspace_order = _workspace_order(
        orchestration,
        base_commit,
        repository_identity=GITHUB_IDENTITY,
    )
    workspace_authority = _workspace_authority(workspace_order)
    workspace_provider = LocalGitWorktreeProvider(tmp_path / "product-workspaces")
    workspace_service = ProductWorkspaceService(
        workspace_provider,
        FileOrchestrationArtifactStore(tmp_path / "orchestration-state"),
        FileProductWorkspaceArtifactStore(tmp_path / "product-workspace-state"),
        clock=lambda: NOW + timedelta(minutes=65),
    )
    day31 = workspace_service.run(
        execution_id="execution-isolated-product-workspace-1",
        work_order=workspace_order,
        authority=workspace_authority,
        orchestration_artifact=orchestration,
        source_repository=source,
    )
    workspace = workspace_provider.root / day31.workspace_relative_path
    coding_order = _coding_order(day31, orchestration, qa_artifact, security_artifact)
    coding_authority = _coding_authority(coding_order)
    coding_service = CodingReviewService(
        LocalDeterministicCodingReviewProvider(),
        FileProductWorkspaceArtifactStore(tmp_path / "product-workspace-state"),
        FileOrchestrationArtifactStore(tmp_path / "orchestration-state"),
        FileQAArtifactStore(tmp_path / "qa-state"),
        FileSecurityArtifactStore(tmp_path / "security-state"),
        FileCodingReviewArtifactStore(tmp_path / "coding-review-state"),
        clock=lambda: NOW + timedelta(minutes=80),
    )
    coding = coding_service.run(
        execution_id="execution-coding-review-1",
        work_order=coding_order,
        authority=coding_authority,
        workspace_artifact=day31,
        orchestration_artifact=orchestration,
        qa_artifact=qa_artifact,
        security_artifact=security_artifact,
        source_repository=source,
        workspace=workspace,
    )
    return source, workspace, coding


def _work_order(coding, **changes) -> GitHubDeliveryWorkOrder:
    values = {
        "work_order_id": "work-order-github-delivery-1",
        "tenant_id": coding.tenant_id,
        "opportunity_id": coding.opportunity_id,
        "assignment_id": "assignment-github-delivery-1",
        "coding_review_artifact_digest": coding.digest,
        "workspace_artifact_digest": coding.workspace_artifact_digest,
        "repository_id": coding.repository_id,
        "repository_identity": coding.repository_identity,
        "repository_full_name": REPOSITORY_FULL_NAME,
        "workspace_id": coding.workspace_id,
        "base_branch": coding.base_branch,
        "base_commit": coding.base_commit,
        "base_tree": coding.base_tree,
        "feature_branch": coding.feature_branch,
        "reviewed_files": tuple(
            ReviewedFileBinding(item.path, item.owner_role, item.content_digest)
            for item in coding.final_files
        ),
        "final_diff_digest": coding.final_diff_digest,
        "commit_message": "Implement reviewed generic product fixture",
        "pull_request_title": "Implement reviewed generic product fixture",
        "pull_request_body": (
            "Exact Day 32 reviewed output. QA and Security passed. "
            "This draft remains unmerged and awaits human review."
        ),
        "objectives": (
            "Verify the exact persisted Day 32 reviewed output",
            "Commit only the reviewed product paths",
            "Push only the isolated product feature branch without force",
            "Open one draft pull request bound to the reviewed commit",
        ),
        "acceptance_checks": (
            "The Day 32 artifact is exact persisted state",
            "Every workspace file digest matches Day 32 review evidence",
            "The source repository remains clean and unchanged",
            "The Git index contains only reviewed paths",
            "The commit has the exact approved base parent",
            "The remote feature branch equals the reviewed commit",
            "The pull request is open, draft, and unmerged",
            "No force push, merge, deployment, or release occurs",
        ),
        "constraints": (
            "One generic fixture only and no official pilot selection",
            "One commit, one non-force push, and one draft pull request only",
            "No unreviewed, deleted, renamed, linked, or special paths",
            "No raw credential or secret value may be persisted or exposed",
            "No general command runner or unapproved network access",
            "No protected-branch write or force update",
            "No pull-request approval or merge",
            "No preview deployment, production deployment, or release",
        ),
        "issued_at": NOW + timedelta(minutes=90),
    }
    values.update(changes)
    return GitHubDeliveryWorkOrder(**values)


def _authority(order: GitHubDeliveryWorkOrder, **changes) -> GitHubDeliveryAuthority:
    values = {
        "authority_id": "authority-github-delivery-1",
        "issuer_id": "founder-product-repository-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "work_order_digest": order.digest,
        "coding_review_artifact_digest": order.coding_review_artifact_digest,
        "repository_id": order.repository_id,
        "workspace_id": order.workspace_id,
        "base_branch": order.base_branch,
        "feature_branch": order.feature_branch,
        "allowed_action_ids": GITHUB_DELIVERY_ACTIONS,
        "allowed_tool_ids": GITHUB_DELIVERY_TOOL_IDS,
        "issued_at": NOW + timedelta(minutes=85),
        "expires_at": NOW + timedelta(hours=8),
        "max_reviewed_paths": 16,
        "max_git_commands": 64,
        "max_controlled_network_calls": 8,
        "repository_write_allowed": True,
        "controlled_network_allowed": True,
        "scoped_credential_handle_allowed": True,
        "commit_allowed": True,
        "push_allowed": True,
        "pull_request_allowed": True,
        "draft_only": True,
        "force_push_allowed": False,
        "merge_allowed": False,
        "deployment_allowed": False,
        "release_allowed": False,
    }
    values.update(changes)
    return GitHubDeliveryAuthority(**values)


def _bare_remote(tmp_path: Path, source: Path) -> Path:
    remote = tmp_path / "fixture-product-remote.git"
    subprocess.run(("git", "init", "--bare", str(remote)), check=True, capture_output=True)
    _git(source, "push", str(remote), "refs/heads/main:refs/heads/main")
    return remote


def _service(tmp_path: Path, provider):
    return GitHubDeliveryService(
        provider,
        FileCodingReviewArtifactStore(tmp_path / "coding-review-state"),
        FileGitHubDeliveryArtifactStore(tmp_path / "github-delivery-state"),
        clock=lambda: NOW + timedelta(minutes=95),
    )


def _fixture(tmp_path: Path, gateway=None):
    source, workspace, coding = _coding_fixture(tmp_path)
    order = _work_order(coding)
    authority = _authority(order)
    remote = _bare_remote(tmp_path, source)
    selected_gateway = gateway or DeterministicDraftPullRequestGateway()
    provider = ControlledGitHubDeliveryProvider(selected_gateway, push_remote=remote)
    service = _service(tmp_path, provider)
    return service, provider, selected_gateway, source, workspace, remote, coding, order, authority


def _run_delivery(tmp_path: Path, gateway=None):
    values = _fixture(tmp_path, gateway)
    service, provider, selected_gateway, source, workspace, remote, coding, order, authority = values
    artifact = service.run(
        execution_id="execution-github-delivery-1",
        work_order=order,
        authority=authority,
        coding_review_artifact=coding,
        source_repository=source,
        workspace=workspace,
    )
    return (*values, artifact)


def test_delivery_commits_pushes_and_opens_one_draft_pr(tmp_path: Path) -> None:
    service, provider, gateway, source, workspace, remote, coding, order, _, artifact = (
        _run_delivery(tmp_path)
    )
    assert provider.execution_count == 1
    assert gateway.query_count == 1 and gateway.create_count == 1
    assert artifact.coding_review_artifact_digest == coding.digest
    assert artifact.capability_ids == GITHUB_DELIVERY_CAPABILITIES
    assert artifact.action_ids == GITHUB_DELIVERY_ACTIONS
    assert artifact.tool_ids == GITHUB_DELIVERY_TOOL_IDS
    assert artifact.staged_paths == artifact.committed_paths == coding.final_changed_paths
    assert artifact.commit_parent == coding.base_commit
    assert artifact.commit_sha == artifact.remote_branch_sha
    assert artifact.pull_request.head_commit == artifact.commit_sha
    assert artifact.pull_request.base_commit == coding.base_commit
    assert artifact.pull_request.draft and not artifact.pull_request.merged
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS
    assert artifact.source_state == SOURCE_STATE and artifact.workspace_state == WORKSPACE_STATE
    assert artifact.branch_state == BRANCH_STATE
    assert artifact.pull_request_state == PULL_REQUEST_STATE
    assert artifact.delivery_state == DELIVERY_STATE
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact
    assert _git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert _git(workspace, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert _git(remote, "rev-parse", f"refs/heads/{order.feature_branch}") == artifact.commit_sha


def test_commit_contains_only_exact_reviewed_files_and_digests(tmp_path: Path) -> None:
    *values, artifact = _run_delivery(tmp_path)
    workspace, coding = values[4], values[6]
    committed = tuple(
        sorted(
            item
            for item in _git(
                workspace,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "-z",
                "HEAD",
            ).split("\0")
            if item
        )
    )
    assert committed == coding.final_changed_paths
    assert _git(workspace, "rev-parse", "HEAD^") == coding.base_commit
    assert _git(workspace, "rev-parse", "HEAD^{tree}") == artifact.commit_tree
    for binding in artifact.reviewed_files:
        assert binding.content_digest == __import__("hashlib").sha256(
            (workspace / binding.path).read_bytes()
        ).hexdigest()


def test_remote_branch_and_draft_pr_bind_exact_commit(tmp_path: Path) -> None:
    *values, artifact = _run_delivery(tmp_path)
    remote, order = values[5], values[7]
    assert _git(remote, "rev-parse", f"refs/heads/{order.feature_branch}") == artifact.commit_sha
    receipt = artifact.pull_request
    assert receipt.repository_full_name == REPOSITORY_FULL_NAME
    assert receipt.base_branch == order.base_branch
    assert receipt.head_branch == order.feature_branch
    assert receipt.title == order.pull_request_title
    assert receipt.body_digest == order.pull_request_body_digest
    assert receipt.url == "https://github.com/acme/ascos-fixture-product/pull/1"


def test_exact_retry_and_restart_do_not_repeat_external_effects(tmp_path: Path) -> None:
    service, provider, gateway, source, workspace, remote, coding, order, authority, expected = (
        _run_delivery(tmp_path)
    )
    kwargs = dict(
        execution_id=expected.execution_id,
        work_order=order,
        authority=authority,
        coding_review_artifact=coding,
        source_repository=source,
        workspace=workspace,
    )
    assert service.run(**kwargs) == expected
    restarted_gateway = DeterministicDraftPullRequestGateway()
    restarted_provider = ControlledGitHubDeliveryProvider(restarted_gateway, push_remote=remote)
    restarted = _service(tmp_path, restarted_provider)
    assert restarted.run(**kwargs) == expected
    assert provider.execution_count == 1 and restarted_provider.execution_count == 0
    assert gateway.create_count == 1 and restarted_gateway.create_count == 0


def test_changed_retry_conflicts_without_another_effect(tmp_path: Path) -> None:
    service, provider, _, source, workspace, _, coding, order, _, artifact = _run_delivery(tmp_path)
    changed = replace(order, commit_message="Different reviewed commit")
    with pytest.raises(GitHubDeliveryConflict):
        service.run(
            execution_id=artifact.execution_id,
            work_order=changed,
            authority=_authority(changed),
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 1


@pytest.mark.parametrize(
    "change",
    (
        {"assignment_id": "wrong-assignment"},
        {"repository_id": "wrong-repository"},
        {"workspace_id": "wrong-workspace"},
        {"coding_review_artifact_digest": "0" * 64},
    ),
)
def test_authority_drift_fails_before_provider(tmp_path: Path, change) -> None:
    service, provider, _, source, workspace, _, coding, order, authority = _fixture(tmp_path)
    with pytest.raises(GitHubDeliveryPolicyError):
        service.run(
            execution_id="execution-invalid-authority",
            work_order=order,
            authority=replace(authority, **change),
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0


def test_unpersisted_or_changed_day32_artifact_fails_before_provider(tmp_path: Path) -> None:
    service, provider, _, source, workspace, _, coding, order, authority = _fixture(tmp_path)
    changed = replace(coding, execution_id="execution-coding-review-other")
    with pytest.raises(GitHubDeliveryPolicyError):
        service.run(
            execution_id="execution-changed-source",
            work_order=order,
            authority=authority,
            coding_review_artifact=changed,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0


def test_reviewed_file_tamper_fails_before_provider(tmp_path: Path) -> None:
    service, provider, _, source, workspace, _, coding, order, authority = _fixture(tmp_path)
    (workspace / order.reviewed_paths[0]).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(GitHubDeliveryPolicyError):
        service.run(
            execution_id="execution-file-tamper",
            work_order=order,
            authority=authority,
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0


def test_unrelated_or_staged_path_fails_before_provider(tmp_path: Path) -> None:
    service, provider, _, source, workspace, _, coding, order, authority = _fixture(tmp_path)
    (workspace / "unrelated.txt").write_text("unsafe\n", encoding="utf-8")
    with pytest.raises(GitHubDeliveryPolicyError):
        service.run(
            execution_id="execution-unrelated",
            work_order=order,
            authority=authority,
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0
    (workspace / "unrelated.txt").unlink()
    _git(workspace, "add", order.reviewed_paths[0])
    with pytest.raises(GitHubDeliveryPolicyError):
        service.run(
            execution_id="execution-prestaged",
            work_order=order,
            authority=authority,
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0


def test_existing_remote_branch_fails_before_workspace_mutation(tmp_path: Path) -> None:
    service, provider, _, source, workspace, remote, coding, order, authority = _fixture(tmp_path)
    _git(source, "push", str(remote), f"HEAD:refs/heads/{order.feature_branch}")
    before = _git(workspace, "status", "--porcelain=v1", "--untracked-files=all")
    with pytest.raises(GitHubDeliveryReconciliationRequired):
        service.run(
            execution_id="execution-remote-exists",
            work_order=order,
            authority=authority,
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert _git(workspace, "rev-parse", "HEAD") == coding.base_commit
    assert _git(workspace, "status", "--porcelain=v1", "--untracked-files=all") == before
    assert provider.execution_count == 1


def test_existing_pull_request_fails_before_workspace_mutation(tmp_path: Path) -> None:
    gateway = DeterministicDraftPullRequestGateway()
    service, provider, _, source, workspace, _, coding, order, authority = _fixture(tmp_path, gateway)
    gateway.seed(
        DraftPullRequestReceipt(
            7,
            "https://github.com/acme/ascos-fixture-product/pull/7",
            REPOSITORY_FULL_NAME,
            order.base_branch,
            order.feature_branch,
            order.base_commit,
            order.base_commit,
            order.pull_request_title,
            order.pull_request_body_digest,
        )
    )
    before = _git(workspace, "status", "--porcelain=v1", "--untracked-files=all")
    with pytest.raises(GitHubDeliveryReconciliationRequired):
        service.run(
            execution_id="execution-pr-exists",
            work_order=order,
            authority=authority,
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert _git(workspace, "rev-parse", "HEAD") == coding.base_commit
    assert _git(workspace, "status", "--porcelain=v1", "--untracked-files=all") == before
    assert provider.execution_count == 1 and gateway.create_count == 0


class _FailingDraftGateway(DeterministicDraftPullRequestGateway):
    def create(self, **kwargs):
        del kwargs
        raise GitHubDeliveryPolicyError("simulated gateway failure")


def test_partial_delivery_requires_reconciliation_and_is_not_reset(tmp_path: Path) -> None:
    service, _, _, source, workspace, remote, coding, order, authority = _fixture(
        tmp_path, _FailingDraftGateway()
    )
    with pytest.raises(GitHubDeliveryReconciliationRequired):
        service.run(
            execution_id="execution-partial",
            work_order=order,
            authority=authority,
            coding_review_artifact=coding,
            source_repository=source,
            workspace=workspace,
        )
    assert _git(workspace, "rev-parse", "HEAD") != coding.base_commit
    assert _git(remote, "rev-parse", f"refs/heads/{order.feature_branch}") == _git(
        workspace, "rev-parse", "HEAD"
    )


def test_persistence_is_mode_0600_and_tamper_evident(tmp_path: Path) -> None:
    *_, artifact = _run_delivery(tmp_path)
    path = (
        tmp_path
        / "github-delivery-state"
        / artifact.tenant_id
        / artifact.execution_id
        / "github-delivery-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = json.loads(path.read_text())
    envelope["record"]["merge_count"] = 1
    path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    os.chmod(path, 0o600)
    store = FileGitHubDeliveryArtifactStore(tmp_path / "github-delivery-state")
    with pytest.raises(GitHubDeliveryCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_persistence_rejects_unknown_entries_permissions_and_escape(tmp_path: Path) -> None:
    *_, artifact = _run_delivery(tmp_path)
    directory = tmp_path / "github-delivery-state" / artifact.tenant_id / artifact.execution_id
    path = directory / "github-delivery-v1.json"
    (directory / "unexpected.txt").write_text("unsafe", encoding="utf-8")
    store = FileGitHubDeliveryArtifactStore(tmp_path / "github-delivery-state")
    with pytest.raises(GitHubDeliveryCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    (directory / "unexpected.txt").unlink()
    os.chmod(path, 0o644)
    with pytest.raises(GitHubDeliveryCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    with pytest.raises(GitHubDeliveryCorrupt):
        store.load("../tenant", "execution")


def test_models_reject_elevated_delivery_authority_and_unsafe_request(tmp_path: Path) -> None:
    _, _, _, _, _, _, _, order, _ = _fixture(tmp_path)
    with pytest.raises(ValueError):
        _authority(order, merge_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, force_push_allowed=True)
    with pytest.raises(ValueError):
        replace(order, feature_branch="main")
    with pytest.raises(ValueError):
        replace(order, repository_identity="https://example.invalid/product.git")
