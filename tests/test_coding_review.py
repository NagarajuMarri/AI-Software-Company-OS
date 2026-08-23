from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from runtime.coding_review import (
    ARTIFACT_STATUS,
    CODING_REVIEW_ACTIONS,
    CODING_REVIEW_CAPABILITIES,
    CODING_REVIEW_TOOL_IDS,
    DELIVERY_STATE,
    ENGINEERING_ROLES,
    PILOT_STATUS,
    QA_ROLE,
    ROUTE_STATE,
    SOURCE_STATE,
    WORKSPACE_STATE,
    CodingAssignment,
    CodingReviewAuthority,
    CodingReviewConflict,
    CodingReviewCorrupt,
    CodingReviewFailed,
    CodingReviewPolicyError,
    CodingReviewService,
    CodingReviewWorkOrder,
    CodingRoundPlan,
    FileCodingReviewArtifactStore,
    LocalDeterministicCodingReviewProvider,
    TextPatch,
    default_generic_fixture_plans,
)
from runtime.product_workspace import (
    FileProductWorkspaceArtifactStore,
    LocalGitWorktreeProvider,
    ProductWorkspaceService,
)
from runtime.workforce_orchestration import FileOrchestrationArtifactStore
from runtime.workforce_qa import FileQAArtifactStore
from runtime.workforce_security import FileSecurityArtifactStore
from tests.test_product_workspace import (
    _authority as _workspace_authority,
    _source_repository,
    _work_order as _workspace_order,
)
from tests.test_workforce_leadership import NOW
from tests.test_workforce_orchestration import _run_orchestration


def _git(path: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=path,
        capture_output=True,
        text=True,
        check=check,
    )
    return result.stdout.strip()


def _day31_fixture(tmp_path: Path):
    _, _, sources, _, _, _, orchestration = _run_orchestration(tmp_path)
    qa_artifact = sources[3]
    security_artifact = sources[4]
    source, base_commit = _source_repository(tmp_path)
    order = _workspace_order(orchestration, base_commit)
    authority = _workspace_authority(order)
    provider = LocalGitWorktreeProvider(tmp_path / "product-workspaces")
    service = ProductWorkspaceService(
        provider,
        FileOrchestrationArtifactStore(tmp_path / "orchestration-state"),
        FileProductWorkspaceArtifactStore(tmp_path / "product-workspace-state"),
        clock=lambda: NOW + timedelta(minutes=65),
    )
    artifact = service.run(
        execution_id="execution-isolated-product-workspace-1",
        work_order=order,
        authority=authority,
        orchestration_artifact=orchestration,
        source_repository=source,
    )
    workspace = provider.root / artifact.workspace_relative_path
    return source, workspace, orchestration, qa_artifact, security_artifact, artifact


def _work_order(workspace, orchestration, qa, security, **changes):
    values = {
        "work_order_id": "work-order-coding-review-1",
        "tenant_id": workspace.tenant_id,
        "opportunity_id": workspace.opportunity_id,
        "assignment_id": "assignment-coding-review-1",
        "orchestration_artifact_digest": orchestration.digest,
        "orchestration_source_set_digest": orchestration.source_set_digest,
        "workspace_artifact_digest": workspace.digest,
        "qa_artifact_digest": qa.digest,
        "security_artifact_digest": security.digest,
        "repository_id": workspace.repository_id,
        "repository_identity": workspace.repository_identity,
        "workspace_id": workspace.workspace_id,
        "base_branch": workspace.base_branch,
        "base_commit": workspace.base_commit,
        "base_tree": workspace.base_tree,
        "feature_branch": workspace.feature_branch,
        "assignments": (
            CodingAssignment(
                "coding-backend-1",
                "BACKEND_ENGINEER",
                "Implement the bounded application and backend behavior",
                ("app.py", "backend.py"),
                ("Application integrates all role outputs", "Release value is covered by QA"),
            ),
            CodingAssignment(
                "coding-frontend-1",
                "FRONTEND_ENGINEER",
                "Implement the bounded presentation behavior",
                ("frontend.py",),
                ("Presentation is deterministic", "Presentation is integrated by the application"),
            ),
            CodingAssignment(
                "coding-ai-1",
                "AI_ENGINEER",
                "Implement deterministic summarization behavior",
                ("ai.py",),
                ("AI behavior is deterministic", "AI behavior is covered by integration tests"),
            ),
            CodingAssignment(
                "coding-data-1",
                "DATA_ENGINEER",
                "Implement deterministic data-record behavior",
                ("data.py",),
                ("Data output is typed by shape", "Data behavior is covered by integration tests"),
            ),
        ),
        "qa_test_paths": ("test_product.py",),
        "objectives": (
            "Implement all four Engineering assignments in the isolated workspace",
            "Materialize the exact bounded QA test specification",
            "Run QA and static Security reviews on every candidate round",
            "Return review failures to the responsible Engineering role",
            "Stop after both reviews pass without Git delivery",
        ),
        "acceptance_checks": (
            "The exact persisted Day 31 workspace is used",
            "The exact persisted Day 30 source set is used",
            "The exact persisted Day 26 QA artifact is used",
            "The exact persisted Day 27 Security artifact is used",
            "All changed paths belong to a role-owned assignment",
            "QA tests execute in the isolated workspace",
            "Static Security review executes after QA passes",
            "Each failure returns to its responsible Engineering role",
            "The final candidate passes QA and Security",
            "The source repository remains clean and unchanged",
            "No file is staged and no commit, push, or pull request occurs",
        ),
        "constraints": (
            "One generic fixture only and no official pilot selection",
            "Text changes are limited to exact role-owned paths",
            "No symbolic links, path escape, deletions, or Git metadata writes",
            "No live coding provider, network, credentials, or general command runner",
            "Only isolated pytest and static Security review may execute",
            "No source-repository product file mutation",
            "No staging, commit, push, pull request, merge, deployment, or release",
            "At most three coding and review rounds",
        ),
        "issued_at": NOW + timedelta(minutes=75),
    }
    values.update(changes)
    return CodingReviewWorkOrder(**values)


def _authority(order: CodingReviewWorkOrder, **changes):
    values = {
        "authority_id": "authority-coding-review-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "work_order_digest": order.digest,
        "workspace_artifact_digest": order.workspace_artifact_digest,
        "allowed_action_ids": CODING_REVIEW_ACTIONS,
        "allowed_tool_ids": CODING_REVIEW_TOOL_IDS,
        "issued_at": NOW + timedelta(minutes=70),
        "expires_at": NOW + timedelta(hours=6),
        "max_review_rounds": 3,
        "max_file_writes": 16,
        "max_tool_calls": 64,
        "live_provider_allowed": False,
        "network_allowed": False,
        "credentials_allowed": False,
        "source_file_writes_allowed": False,
        "workspace_text_writes_allowed": True,
        "commit_allowed": False,
        "push_allowed": False,
        "pull_request_allowed": False,
    }
    values.update(changes)
    return CodingReviewAuthority(**values)


def _service(tmp_path: Path, provider=None):
    selected = provider or LocalDeterministicCodingReviewProvider()
    service = CodingReviewService(
        selected,
        FileProductWorkspaceArtifactStore(tmp_path / "product-workspace-state"),
        FileOrchestrationArtifactStore(tmp_path / "orchestration-state"),
        FileQAArtifactStore(tmp_path / "qa-state"),
        FileSecurityArtifactStore(tmp_path / "security-state"),
        FileCodingReviewArtifactStore(tmp_path / "coding-review-state"),
        clock=lambda: NOW + timedelta(minutes=80),
    )
    return service, selected


def _fixture(tmp_path: Path, provider=None):
    source, workspace, orchestration, qa, security, day31 = _day31_fixture(tmp_path)
    order = _work_order(day31, orchestration, qa, security)
    authority = _authority(order)
    service, selected = _service(tmp_path, provider)
    return service, selected, source, workspace, orchestration, qa, security, day31, order, authority


def _run_coding_review(tmp_path: Path, provider=None):
    values = _fixture(tmp_path, provider)
    service, selected, source, workspace, orchestration, qa, security, day31, order, authority = values
    artifact = service.run(
        execution_id="execution-coding-review-1",
        work_order=order,
        authority=authority,
        workspace_artifact=day31,
        orchestration_artifact=orchestration,
        qa_artifact=qa,
        security_artifact=security,
        source_repository=source,
        workspace=workspace,
    )
    return (*values, artifact)


def test_coding_review_implements_all_roles_and_stops_before_delivery(tmp_path: Path) -> None:
    service, provider, source, workspace, orchestration, qa, security, day31, order, _, artifact = (
        _run_coding_review(tmp_path)
    )
    assert provider.execution_count == 1
    assert artifact.workspace_artifact_digest == day31.digest
    assert artifact.orchestration_artifact_digest == orchestration.digest
    assert artifact.qa_artifact_digest == qa.digest
    assert artifact.security_artifact_digest == security.digest
    assert artifact.capability_ids == CODING_REVIEW_CAPABILITIES
    assert artifact.action_ids == CODING_REVIEW_ACTIONS
    assert artifact.tool_ids == CODING_REVIEW_TOOL_IDS
    assert artifact.final_changed_paths == (
        "ai.py",
        "app.py",
        "backend.py",
        "data.py",
        "frontend.py",
        "test_product.py",
    )
    assert {item.owner_role for item in artifact.final_files} == set(ENGINEERING_ROLES) | {QA_ROLE}
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS
    assert artifact.source_state == SOURCE_STATE
    assert artifact.workspace_state == WORKSPACE_STATE
    assert artifact.delivery_state == DELIVERY_STATE
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact
    assert _git(source, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert _git(workspace, "rev-parse", "HEAD") == order.base_commit


def test_failed_qa_and_security_return_to_responsible_engineer(tmp_path: Path) -> None:
    *_, artifact = _run_coding_review(tmp_path)
    assert len(artifact.rounds) == 3
    first, second, third = artifact.rounds
    assert (first.qa_status, first.security_status) == ("FAIL", "NOT_RUN_QA_FAILED")
    assert first.failure_codes == ("QA_TEST_FAILURE",)
    assert second.resolved_feedback_codes == first.failure_codes
    assert (second.qa_status, second.security_status) == ("PASS", "FAIL")
    assert second.failure_codes == ("UNSAFE_DYNAMIC_EXECUTION",)
    assert third.resolved_feedback_codes == second.failure_codes
    assert (third.qa_status, third.security_status, third.findings) == ("PASS", "PASS", ())
    assert tuple(item.reviewer_role for item in artifact.failure_routes) == (
        QA_ROLE,
        "SECURITY_ENGINEER",
    )
    assert all(item.responsible_role == "BACKEND_ENGINEER" for item in artifact.failure_routes)
    assert all(item.state == ROUTE_STATE for item in artifact.failure_routes)


def test_final_candidate_physically_passes_product_tests(tmp_path: Path) -> None:
    values = _run_coding_review(tmp_path)
    workspace, artifact = values[3], values[-1]
    result = subprocess.run(
        (sys.executable, "-m", "pytest", "-q", "test_product.py"),
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "2 passed" in result.stdout
    assert artifact.qa_execution_count == 3
    assert artifact.security_execution_count == 2
    assert artifact.product_file_write_count == 8
    assert artifact.specialized_command_count == 5


def test_workspace_is_dirty_unstaged_uncommitted_and_source_preserved(tmp_path: Path) -> None:
    _, _, source, workspace, _, _, _, day31, _, _, artifact = _run_coding_review(tmp_path)
    assert _git(workspace, "status", "--porcelain=v1", "--untracked-files=all")
    assert _git(workspace, "diff", "--cached", "--name-only") == ""
    assert _git(workspace, "rev-parse", "HEAD") == day31.base_commit
    assert _git(workspace, "rev-parse", "HEAD^{tree}") == day31.base_tree
    assert _git(source, "branch", "--show-current") == day31.base_branch
    assert _git(source, "rev-parse", "HEAD") == day31.base_commit
    assert artifact.staged_path_count == artifact.commit_count == 0
    assert artifact.push_count == artifact.pull_request_count == 0
    assert artifact.network_call_count == artifact.general_command_count == 0
    assert artifact.credential_access_count == 0


def test_exact_retry_and_restart_do_not_repeat_coding_effects(tmp_path: Path) -> None:
    service, provider, source, workspace, orchestration, qa, security, day31, order, authority, expected = (
        _run_coding_review(tmp_path)
    )
    kwargs = dict(
        execution_id=expected.execution_id,
        work_order=order,
        authority=authority,
        workspace_artifact=day31,
        orchestration_artifact=orchestration,
        qa_artifact=qa,
        security_artifact=security,
        source_repository=source,
        workspace=workspace,
    )
    assert service.run(**kwargs) == expected
    restarted, restarted_provider = _service(tmp_path)
    assert restarted.run(**kwargs) == expected
    assert provider.execution_count == 1 and restarted_provider.execution_count == 0


def test_changed_retry_conflicts_without_second_provider_effect(tmp_path: Path) -> None:
    service, provider, source, workspace, orchestration, qa, security, day31, order, _, artifact = (
        _run_coding_review(tmp_path)
    )
    changed = replace(order, workspace_id="workspace-changed")
    with pytest.raises(CodingReviewConflict):
        service.run(
            execution_id=artifact.execution_id,
            work_order=changed,
            authority=_authority(changed),
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 1


@pytest.mark.parametrize(
    "authority_change",
    (
        {"assignment_id": "wrong-assignment"},
        {"workspace_artifact_digest": "0" * 64},
    ),
)
def test_authority_drift_fails_before_provider(tmp_path: Path, authority_change) -> None:
    service, provider, source, workspace, orchestration, qa, security, day31, order, authority = (
        _fixture(tmp_path)
    )
    with pytest.raises(CodingReviewPolicyError):
        service.run(
            execution_id="execution-invalid-authority",
            work_order=order,
            authority=replace(authority, **authority_change),
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0


def test_source_substitution_fails_before_provider(tmp_path: Path) -> None:
    service, provider, source, workspace, orchestration, qa, security, day31, order, authority = (
        _fixture(tmp_path)
    )
    with pytest.raises(CodingReviewPolicyError):
        service.run(
            execution_id="execution-invalid-source",
            work_order=order,
            authority=authority,
            workspace_artifact=replace(day31, orchestration_artifact_digest="0" * 64),
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0


def test_dirty_workspace_fails_before_provider(tmp_path: Path) -> None:
    service, provider, source, workspace, orchestration, qa, security, day31, order, authority = (
        _fixture(tmp_path)
    )
    (workspace / "unrelated.txt").write_text("do not touch", encoding="utf-8")
    with pytest.raises(CodingReviewPolicyError):
        service.run(
            execution_id="execution-dirty-workspace",
            work_order=order,
            authority=authority,
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )
    assert provider.execution_count == 0
    assert (workspace / "unrelated.txt").read_text() == "do not touch"


def test_unapproved_or_wrong_role_patch_fails_without_writing_target(tmp_path: Path) -> None:
    plans = default_generic_fixture_plans()
    outside = replace(
        plans[0],
        patches=(TextPatch("BACKEND_ENGINEER", "outside.py", "unsafe = True\n"),),
    )
    provider = LocalDeterministicCodingReviewProvider((outside,))
    values = _fixture(tmp_path, provider)
    service, _, source, workspace, orchestration, qa, security, day31, order, authority = values
    with pytest.raises(CodingReviewPolicyError):
        service.run(
            execution_id="execution-unapproved-path",
            work_order=order,
            authority=authority,
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )
    assert not (workspace / "outside.py").exists()

    wrong = replace(
        plans[0],
        patches=(TextPatch("FRONTEND_ENGINEER", "backend.py", "unsafe = True\n"),),
    )
    provider = LocalDeterministicCodingReviewProvider((wrong,))
    service, _ = _service(tmp_path, provider)
    with pytest.raises(CodingReviewPolicyError):
        service.run(
            execution_id="execution-wrong-role",
            work_order=order,
            authority=authority,
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )


def test_feedback_must_be_consumed_exactly(tmp_path: Path) -> None:
    plans = default_generic_fixture_plans()
    invalid = (plans[0], replace(plans[1], resolves_feedback_codes=("WRONG",)), plans[2])
    provider = LocalDeterministicCodingReviewProvider(invalid)
    service, _, source, workspace, orchestration, qa, security, day31, order, authority = (
        _fixture(tmp_path, provider)
    )
    with pytest.raises(CodingReviewPolicyError):
        service.run(
            execution_id="execution-feedback-drift",
            work_order=order,
            authority=authority,
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )


def test_review_round_exhaustion_never_persists_success(tmp_path: Path) -> None:
    first = default_generic_fixture_plans()[0]
    provider = LocalDeterministicCodingReviewProvider((first,))
    service, _, source, workspace, orchestration, qa, security, day31, order, authority = (
        _fixture(tmp_path, provider)
    )
    with pytest.raises(CodingReviewFailed):
        service.run(
            execution_id="execution-review-exhausted",
            work_order=order,
            authority=authority,
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )
    with pytest.raises(Exception):
        service.get(order.tenant_id, "execution-review-exhausted")


class _SourceDriftingProvider(LocalDeterministicCodingReviewProvider):
    def __init__(self, source: Path) -> None:
        super().__init__()
        self._source = source

    def execute(self, workspace, work_order, authority):
        observation = super().execute(workspace, work_order, authority)
        (self._source / "source-drift.txt").write_text("unsafe", encoding="utf-8")
        return observation


def test_source_drift_is_detected_after_provider_execution(tmp_path: Path) -> None:
    source, workspace, orchestration, qa, security, day31 = _day31_fixture(tmp_path)
    order = _work_order(day31, orchestration, qa, security)
    authority = _authority(order)
    provider = _SourceDriftingProvider(source)
    service, _ = _service(tmp_path, provider)
    with pytest.raises(CodingReviewPolicyError):
        service.run(
            execution_id="execution-source-drift",
            work_order=order,
            authority=authority,
            workspace_artifact=day31,
            orchestration_artifact=orchestration,
            qa_artifact=qa,
            security_artifact=security,
            source_repository=source,
            workspace=workspace,
        )


def test_persistence_is_mode_0600_and_tamper_evident(tmp_path: Path) -> None:
    *_, artifact = _run_coding_review(tmp_path)
    path = (
        tmp_path
        / "coding-review-state"
        / artifact.tenant_id
        / artifact.execution_id
        / "coding-review-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = json.loads(path.read_text())
    envelope["record"]["delivery_state"] = "DELIVERED"
    path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    os.chmod(path, 0o600)
    store = FileCodingReviewArtifactStore(tmp_path / "coding-review-state")
    with pytest.raises(CodingReviewCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_persistence_rejects_unknown_entries_permissions_and_path_escape(tmp_path: Path) -> None:
    *_, artifact = _run_coding_review(tmp_path)
    directory = tmp_path / "coding-review-state" / artifact.tenant_id / artifact.execution_id
    path = directory / "coding-review-v1.json"
    (directory / "unexpected.txt").write_text("unsafe", encoding="utf-8")
    store = FileCodingReviewArtifactStore(tmp_path / "coding-review-state")
    with pytest.raises(CodingReviewCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    (directory / "unexpected.txt").unlink()
    os.chmod(path, 0o644)
    with pytest.raises(CodingReviewCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    with pytest.raises(CodingReviewCorrupt):
        store.load("../tenant", "execution")


def test_models_reject_delivery_authority_and_unsafe_paths(tmp_path: Path) -> None:
    source, workspace, orchestration, qa, security, day31 = _day31_fixture(tmp_path)
    assert source.is_dir() and workspace.is_dir()
    order = _work_order(day31, orchestration, qa, security)
    with pytest.raises(ValueError):
        _authority(order, commit_allowed=True)
    with pytest.raises(ValueError):
        TextPatch("BACKEND_ENGINEER", "../escape.py", "unsafe")
    with pytest.raises(ValueError):
        CodingRoundPlan(1, (), (), "BACKEND_ENGINEER")
