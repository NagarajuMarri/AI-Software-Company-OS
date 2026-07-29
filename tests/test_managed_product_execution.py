import json
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from runtime.integrations.git import LocalGitProvider
from runtime.integrations.github import InMemoryGitHubProvider
from runtime.integrations.github.models import GitHubRepository
from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.managed_execution import (
    ChangePolicy,
    ExecutionApprovalError,
    ExecutionMode,
    ExecutionOperationPhase,
    ExecutionPolicyError,
    ExecutionReconciliationError,
    ExecutionStateCorruptError,
    ExecutionValidationError,
    GateStatus,
    ManagedExecutionStore,
    ManagedProductExecutionRequest,
    ManagedProductExecutionService,
    QualityGate,
    QualityGateProfile,
    QualityGateResult,
    ReviewDecisionStatus,
    ValidatedCodingResult,
)
from runtime.managed_execution.cli import main as execution_cli_main
from runtime.managed_execution.policy import safe_relative_path, validate_branch
from runtime.planning import (
    ChangePriority,
    DeterministicPlanningProvider,
    ManagedProductChangeRequest,
    ManagedProductPlanningService,
    PlanningStore,
)
from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import FileProjectRegistry, InMemoryProjectRegistry, ManagedProject
from runtime.tools import LocalCommandRunner, LocalWorkspaceProvider


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


@pytest.fixture
def execution(tmp_path):
    product = tmp_path / "product"
    product.mkdir()
    (product / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (product / "test_app.py").write_text(
        "from app import value\n\ndef test_value(): assert value() == 1\n",
        encoding="utf-8",
    )
    _git(product, "init", "-b", "main")
    _git(product, "config", "user.email", "test@example.com")
    _git(product, "config", "user.name", "Test")
    _git(product, "add", "app.py", "test_app.py")
    _git(product, "commit", "-m", "base")
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True, capture_output=True)
    _git(product, "remote", "add", "origin", str(remote))
    _git(product, "push", "-u", "origin", "main")
    project = ManagedProject(
        "product", "Product", "Fixture", "https://example.com/product",
        "main", local_path=str(product))
    registry = InMemoryProjectRegistry((project,))
    state_root = tmp_path / "state"
    knowledge_store = KnowledgeStore(state_root)
    knowledge = ProjectKnowledgeEngine.create("product", registry, knowledge_store)
    knowledge.scan()
    knowledge.save()
    manager_store = ManagerStateStore(state_root)
    AIProjectManager.initialize("product", registry, manager_store).save()
    planning_store = PlanningStore(state_root)
    planning = ManagedProductPlanningService(
        registry,
        planning_store,
        lambda _: ProjectKnowledgeEngine.load("product", registry, knowledge_store),
        lambda _: AIProjectManager.load("product", registry, manager_store),
        DeterministicPlanningProvider(),
    )
    change = ManagedProductChangeRequest(
        "voice", "product", "Voice", "Add voice boundaries", "Fixture",
        ("voice",), ("Offline tests pass",), (), (), ChangePriority.NORMAL,
        "owner", datetime(2026, 1, 1, tzinfo=timezone.utc))
    planning.create_request(change)
    proposal = planning.generate_proposal(
        "product", "voice", now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    planning.approve_proposal("product", proposal.proposal_id, "planner-reviewer")
    proposal = planning.materialise_approved_proposal("product", proposal.proposal_id)

    execution_store = ManagedExecutionStore(state_root)
    workspaces = LocalWorkspaceProvider(tmp_path / "workspaces")
    runner = LocalCommandRunner(
        tmp_path / "workspaces", allowed_executables={"git", "python"},
        max_output_bytes=4_000)

    def git_factory(workspace_id):
        return LocalGitProvider(
            runner, workspaces, workspace_id,
            repository_url_policy=lambda _: True)

    github = InMemoryGitHubProvider()
    github.register_repository(GitHubRepository(project.repository_url, "main"))
    github.create_branch(project.repository_url, "main", "base")
    policy = ChangePolicy("default", ("",), (
        ".github/workflows/", ".env", "deploy/", "infrastructure/",
        "payment/", "migrations/"))
    profile = QualityGateProfile(
        "offline", "product",
        (QualityGate("offline", ("python", "-c", "print('gate passed')"), 30),),
        ("python",))
    service = ManagedProductExecutionService(
        registry, planning_store, execution_store,
        lambda _: AIProjectManager.load("product", registry, manager_store),
        workspace_provider=workspaces,
        git_provider_factory=git_factory,
        github_provider=github,
        command_runner=runner,
        change_policies=(policy,),
        quality_gate_profiles=(profile,),
    )
    request = ManagedProductExecutionRequest(
        "execute-voice", "product", proposal.proposal_id, proposal.milestone_id,
        tuple(task.task_id for task in proposal.tasks),
        "operator", datetime(2026, 1, 3, tzinfo=timezone.utc), "corr-exec",
        "main", "ascos/voice-foundation", ExecutionMode.CONTROLLED_WRITE,
        "offline", "python", "isolated", "human-review",
        10, 500, 60, (), ("fixture only",))
    return service, request, proposal, product, tmp_path


def _plan(execution, *, approve=True):
    service, request, _, _, _ = execution
    service.create_execution_request(request)
    plan = service.generate_execution_plan("product", request.execution_request_id)
    if approve:
        plan = service.approve_execution_plan(
            "product", plan.execution_plan_id, "execution-reviewer")
    return service, request, plan


def test_valid_execution_request_and_round_trip(execution):
    service, request, _ = _plan(execution, approve=False)
    assert service.store.load_request("product", request.execution_request_id) == request
    assert service.list_executions("product")[0].project_id == "product"


def test_immutable_request_collections_and_bounded_limits(execution):
    request = execution[1]
    with pytest.raises(ExecutionValidationError):
        replace(request, selected_task_ids=list(request.selected_task_ids))
    with pytest.raises(ExecutionValidationError):
        replace(request, maximum_changed_files=501)
    with pytest.raises(ExecutionValidationError):
        replace(request, requested_at=datetime(2026, 1, 1))


def test_missing_project_unapproved_and_incomplete_materialisation(execution):
    service, request, proposal, _, _ = execution
    with pytest.raises(Exception):
        service.create_execution_request(replace(request, project_id="missing"))
    service.planning_store.save_proposal(replace(proposal, materialised_at=None))
    with pytest.raises(ExecutionValidationError):
        service.create_execution_request(request)


def test_wrong_milestone_unrelated_task_and_unsafe_branch(execution):
    service, request, _, _, _ = execution
    for changed in (
        replace(request, milestone_id="wrong"),
        replace(request, selected_task_ids=("unrelated",)),
        replace(request, requested_branch_name="main"),
        replace(request, requested_branch_name="../escape"),
    ):
        with pytest.raises((ExecutionValidationError, ExecutionPolicyError)):
            service.create_execution_request(changed)


def test_deterministic_plan_and_project_isolation(execution):
    service, request, first = _plan(execution, approve=False)
    second = service.generate_execution_plan("product", request.execution_request_id)
    assert first == second
    assert first.generated_at == request.requested_at
    with pytest.raises(Exception):
        service.get_execution_plan("other", first.execution_plan_id)


def test_explicit_approval_provider_self_approval_and_rejection(execution):
    service, _, plan = _plan(execution, approve=False)
    with pytest.raises(ExecutionApprovalError):
        service.create_runtime_work("product", plan.execution_plan_id)
    with pytest.raises(ExecutionApprovalError):
        service.approve_execution_plan("product", plan.execution_plan_id, "deterministic")
    approved = service.approve_execution_plan(
        "product", plan.execution_plan_id, "human")
    assert approved.decisions[-1].plan_version == approved.version
    assert approved.decisions[-1].status == ReviewDecisionStatus.APPROVED


def test_runtime_mapping_is_idempotent_and_traceable(execution):
    service, _, plan = _plan(execution)
    first = service.create_runtime_work("product", plan.execution_plan_id)
    second = service.create_runtime_work("product", plan.execution_plan_id)
    assert first == second
    assert tuple(item.project_task_id for item in first) == tuple(
        task.project_task_id for task in plan.ordered_task_executions)
    assert len({item.runtime_work_item_id for item in first}) == len(first)


def test_plan_revision_invalidates_prior_approval(execution):
    service, _, plan = _plan(execution)
    revised = replace(plan, version=2)
    service.store.save_plan(revised)
    with pytest.raises(ExecutionApprovalError):
        service.create_runtime_work("product", revised.execution_plan_id)


def test_partial_runtime_mapping_requires_reconciliation(execution):
    service, _, plan = _plan(execution)
    task = plan.ordered_task_executions[0]
    from runtime.managed_execution import RuntimeTaskMapping
    service.store.save_mapping("product", RuntimeTaskMapping(
        task.project_task_id, task.runtime_work_item_id,
        plan.runtime_work_package_id, "corr", plan.execution_plan_id))
    with pytest.raises(ExecutionReconciliationError):
        service.create_runtime_work("product", plan.execution_plan_id)


def test_workspace_requires_write_flag_and_is_isolated(execution):
    service, _, plan = _plan(execution)
    with pytest.raises(ExecutionPolicyError):
        service.prepare_workspace("product", plan.execution_plan_id)
    record = service.prepare_workspace(
        "product", plan.execution_plan_id, allow_product_write=True)
    assert Path(record.local_path).is_relative_to(execution[4] / "workspaces")
    assert Path(record.local_path) != execution[3]


def test_workspace_symlink_escape_rejected(execution):
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks unsupported")
    external = execution[4] / "external.txt"
    external.write_text("outside", encoding="utf-8")
    link = execution[3] / "escape"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("symlink creation unavailable")
    service, _, plan = _plan(execution)
    with pytest.raises(ExecutionPolicyError):
        service.prepare_workspace(
            "product", plan.execution_plan_id, allow_product_write=True)


def test_branch_safety_and_dirty_base_rejection(execution):
    service, _, plan = _plan(execution)
    record = service.prepare_workspace(
        "product", plan.execution_plan_id, allow_product_write=True)
    Path(record.local_path, "dirty.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(ExecutionPolicyError):
        service.create_feature_branch(
            "product", plan.execution_plan_id, allow_product_write=True)


def test_controlled_branch_creation(execution):
    service, _, plan = _plan(execution)
    service.prepare_workspace("product", plan.execution_plan_id, allow_product_write=True)
    assert service.create_feature_branch(
        "product", plan.execution_plan_id,
        allow_product_write=True) == plan.feature_branch


def test_coding_request_is_deterministic_and_stable(execution):
    service, _, plan = _plan(execution)
    task_id = plan.ordered_task_executions[0].project_task_id
    first = service.build_coding_request("product", plan.execution_plan_id, task_id)
    second = service.build_coding_request("product", plan.execution_plan_id, task_id)
    assert first == second
    assert first.provider_idempotency_key == second.provider_idempotency_key
    assert first.allowed_commands and isinstance(first.allowed_commands[0], tuple)


def _result(request, **changes):
    values = dict(
        external_task_id=request.external_task_id,
        workspace_id=request.workspace_id,
        status="SUCCEEDED",
        changed_files=("app.py",),
        additions=2,
        deletions=1,
        executed_gates=(),
        artifacts=request.expected_artifacts,
        summary="Bounded implementation",
        provider_task_id="deterministic:1",
        progress_sequences=(1, 2),
    )
    values.update(changes)
    return ValidatedCodingResult(**values)


@pytest.mark.parametrize("changes", [
    {"external_task_id": "wrong"},
    {"workspace_id": "wrong"},
    {"changed_files": ("../escape",)},
    {"changed_files": tuple(f"file-{x}.py" for x in range(11))},
    {"additions": 501},
    {"progress_sequences": (1, 3)},
    {"status": "UNKNOWN"},
    {"summary": "please deploy now"},
])
def test_coding_result_validation_rejects_unsafe_results(execution, changes):
    service, _, plan = _plan(execution)
    task = plan.ordered_task_executions[0].project_task_id
    request = service.build_coding_request("product", plan.execution_plan_id, task)
    with pytest.raises(ExecutionPolicyError):
        service.process_coding_result(
            "product", plan.execution_plan_id, request,
            _result(request, **changes), "default")


def test_coding_result_duplicate_and_failure_blocking(execution):
    service, _, plan = _plan(execution)
    task = plan.ordered_task_executions[0].project_task_id
    request = service.submit_coding_task("product", plan.execution_plan_id, task)
    result = _result(request)
    assert service.process_coding_result(
        "product", plan.execution_plan_id, request, result, "default") == result
    assert service.manager_loader("product").current_state().task(
        task).status.value == "IN_PROGRESS"
    assert service.process_coding_result(
        "product", plan.execution_plan_id, request, result, "default") == result


@pytest.mark.parametrize("status", [
    "FAILED_RETRYABLE", "FAILED_PERMANENT", "TIMED_OUT", "CANCELLED"])
def test_provider_failures_block_project_task(execution, status):
    service, _, plan = _plan(execution)
    task = plan.ordered_task_executions[0].project_task_id
    request = service.submit_coding_task("product", plan.execution_plan_id, task)
    service.process_coding_result(
        "product", plan.execution_plan_id, request,
        _result(request, status=status, changed_files=(), artifacts=(),
                provider_task_id=f"provider:{status}"),
        "default")
    assert service.manager_loader("product").current_state().task(
        task).status.value == "BLOCKED"


def test_quality_gate_pass_and_persistence(execution):
    service, _, plan = _plan(execution)
    service.prepare_workspace("product", plan.execution_plan_id, allow_product_write=True)
    results = service.run_quality_gates("product", plan.execution_plan_id, "offline")
    assert results[0].status == GateStatus.PASSED
    assert service.store.load_gate_results(
        "product", plan.execution_plan_id) == results


def test_review_evidence_digest_and_explicit_approval(execution):
    service, _, plan = _plan(execution)
    service.prepare_workspace("product", plan.execution_plan_id, allow_product_write=True)
    service.run_quality_gates("product", plan.execution_plan_id, "offline")
    task = plan.ordered_task_executions[0].project_task_id
    request = service.build_coding_request("product", plan.execution_plan_id, task)
    result = _result(request)
    evidence = service.generate_review_evidence(
        "product", plan.execution_plan_id, result)
    assert len(evidence.integrity_digest) == 64
    with pytest.raises(ExecutionApprovalError):
        service.approve_review(
            "product", plan.execution_plan_id, "deterministic")
    decision = service.approve_review(
        "product", plan.execution_plan_id, "human-reviewer")
    assert decision.status == ReviewDecisionStatus.APPROVED


def test_review_rejection_requires_reason(execution):
    service, _, plan = _plan(execution)
    service.prepare_workspace("product", plan.execution_plan_id, allow_product_write=True)
    service.run_quality_gates("product", plan.execution_plan_id, "offline")
    task = plan.ordered_task_executions[0].project_task_id
    request = service.build_coding_request("product", plan.execution_plan_id, task)
    service.generate_review_evidence(
        "product", plan.execution_plan_id, _result(request))
    with pytest.raises(ExecutionApprovalError):
        service.reject_review("product", plan.execution_plan_id, "human", "")
    decision = service.request_correction(
        "product", plan.execution_plan_id, "human", "Fix evidence")
    assert decision.status == ReviewDecisionStatus.CORRECTION_REQUESTED


def test_commit_requires_review_approval(execution):
    service, _, plan = _plan(execution)
    with pytest.raises(ExecutionApprovalError):
        service.create_commit(
            "product", plan.execution_plan_id, allow_product_write=True)


def _reviewed_write(execution):
    service, _, plan = _plan(execution)
    service.create_runtime_work("product", plan.execution_plan_id)
    workspace = service.prepare_workspace(
        "product", plan.execution_plan_id, allow_product_write=True)
    service.create_feature_branch(
        "product", plan.execution_plan_id, allow_product_write=True)
    task = plan.ordered_task_executions[0].project_task_id
    coding_request = service.submit_coding_task(
        "product", plan.execution_plan_id, task)
    path = Path(workspace.local_path) / "app.py"
    path.write_text("def value():\n    return 2\n", encoding="utf-8")
    result = _result(coding_request)
    service.process_coding_result(
        "product", plan.execution_plan_id, coding_request, result, "default")
    service.run_quality_gates("product", plan.execution_plan_id, "offline")
    service.generate_review_evidence(
        "product", plan.execution_plan_id, result)
    service.approve_review(
        "product", plan.execution_plan_id, "human-reviewer")
    return service, plan


def test_stage_only_reviewed_files_and_commit_idempotency(execution):
    service, plan = _reviewed_write(execution)
    first = service.create_commit(
        "product", plan.execution_plan_id, allow_product_write=True)
    second = service.create_commit(
        "product", plan.execution_plan_id, allow_product_write=True)
    assert first == second
    assert len(first) == 40


def test_push_and_draft_pr_are_idempotent_without_merge(execution):
    service, plan = _reviewed_write(execution)
    commit = service.create_commit(
        "product", plan.execution_plan_id, allow_product_write=True)
    assert service.push_branch(
        "product", plan.execution_plan_id, allow_product_write=True) == "PUSHED"
    assert service.push_branch(
        "product", plan.execution_plan_id, allow_product_write=True) == "PUSHED"
    service.github_provider.create_branch(
        plan.repository_identity, plan.feature_branch, commit)
    first = service.create_draft_pull_request(
        "product", plan.execution_plan_id, allow_product_write=True)
    second = service.create_draft_pull_request(
        "product", plan.execution_plan_id, allow_product_write=True)
    assert first == second
    assert first.draft is True
    assert first.state.value == "OPEN"


def test_cancellation_and_operation_persistence(execution):
    service, _, plan = _plan(execution)
    cancelled = service.cancel_execution(
        "product", plan.execution_plan_id, "operator", "Stopped")
    assert cancelled.status.value == "CANCELLED"
    operation = service.store.load_operation(
        "product", f"{plan.execution_plan_id}-operation")
    assert operation.phase == ExecutionOperationPhase.CANCELLED


def test_corruption_rejection_and_traversal(execution):
    service, _, plan = _plan(execution)
    path = service.store.root / "product" / "operations" / (
        f"{plan.execution_plan_id}-operation.json")
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ExecutionStateCorruptError):
        service.store.load_operation(
            "product", f"{plan.execution_plan_id}-operation")
    with pytest.raises(ExecutionValidationError):
        service.store.load_request("../escape", "x")


def test_no_real_product_repository_mutation(execution):
    before = {
        path.relative_to(execution[3]): path.read_bytes()
        for path in execution[3].rglob("*") if path.is_file()
    }
    service, _, plan = _plan(execution)
    service.prepare_workspace("product", plan.execution_plan_id, allow_product_write=True)
    after = {
        path.relative_to(execution[3]): path.read_bytes()
        for path in execution[3].rglob("*") if path.is_file()
    }
    assert after == before


def _cli_prefix(execution, tmp_path):
    service = execution[0]
    registry_path = tmp_path / "registry.json"
    FileProjectRegistry(registry_path).register(service.registry.get("product"))
    state_root = service.store.root.parent
    return [
        "--registry", str(registry_path),
        "--planning-state-root", str(state_root),
        "--execution-state-root", str(state_root),
    ]


def test_cli_human_and_json_status(execution, tmp_path, capsys):
    _, _, plan = _plan(execution)
    prefix = _cli_prefix(execution, tmp_path)
    assert execution_cli_main(
        prefix + ["status", "product", plan.execution_plan_id]) == 0
    assert "operation_phase:" in capsys.readouterr().out
    assert execution_cli_main(
        prefix + ["--json", "status", "product", plan.execution_plan_id]) == 0
    assert json.loads(capsys.readouterr().out)["project_id"] == "product"


def test_cli_expected_error_and_write_flag(execution, tmp_path, capsys):
    prefix = _cli_prefix(execution, tmp_path)
    assert execution_cli_main(
        prefix + ["status", "product", "missing"]) == 2
    assert capsys.readouterr().out.startswith("error:")
    from runtime.managed_execution.cli import build_parser
    parsed = build_parser().parse_args(
        prefix + ["--allow-product-write", "list", "product"])
    assert parsed.allow_product_write is True


@pytest.mark.parametrize("mode", tuple(ExecutionMode))
def test_all_execution_modes_are_typed(execution, mode):
    request = replace(execution[1], execution_mode=mode)
    assert request.execution_mode is mode


@pytest.mark.parametrize("branch", [
    "main", "master", "../escape", "/absolute", "bad..branch",
    "bad branch", "feature.lock", "feature@{bad",
])
def test_unsafe_and_protected_branches_are_rejected(branch):
    with pytest.raises(ExecutionPolicyError):
        validate_branch(branch)


@pytest.mark.parametrize("path", [
    "../escape.py", "/absolute.py", "C:\\absolute.py",
    "nested/../../escape", "", "safe/\0secret",
])
def test_unsafe_policy_paths_are_rejected(path):
    with pytest.raises(ExecutionPolicyError):
        safe_relative_path(path)


@pytest.mark.parametrize("phase", tuple(ExecutionOperationPhase))
def test_every_operation_phase_round_trips(execution, phase):
    service, _, plan = _plan(execution)
    identifier = f"{plan.execution_plan_id}-operation"
    operation = service.store.load_operation("product", identifier)
    changed = replace(operation, phase=phase)
    service.store.save_operation(changed)
    assert service.store.load_operation("product", identifier) == changed


@pytest.mark.parametrize("status", tuple(GateStatus))
def test_every_quality_gate_status_round_trips(execution, status):
    service = execution[0]
    now = datetime(2026, 1, 4, tzinfo=timezone.utc)
    values = (QualityGateResult(
        f"gate-{status.value.lower()}", "gate", status,
        0 if status == GateStatus.PASSED else None,
        "", "", now, now),)
    service.store.save_gate_results("product", "status-roundtrip", values)
    assert service.store.load_gate_results(
        "product", "status-roundtrip") == values
