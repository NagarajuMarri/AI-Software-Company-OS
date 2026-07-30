import json
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from runtime.coding_providers import (
    CodingContextBuilder,
    CodingProviderRegistry,
    CodingProviderService,
    ControlledPatchApplier,
    DeterministicCodingProvider,
    FileOperation,
    FileOperationKind,
    ProviderOperationStore,
)
from runtime.integrations.git import LocalGitProvider
from runtime.integrations.github import InMemoryGitHubProvider
from runtime.integrations.github.models import GitHubRepository
from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.managed_execution import (
    AcceptedCodingResult,
    ChangePolicy,
    ExecutionApprovalError,
    ExecutionMode,
    ExecutionOperationPhase,
    ExecutionPlanStatus,
    ExecutionPolicyError,
    ExecutionReconciliationError,
    ExecutionStateCorruptError,
    ExternalEffectKind,
    ExternalEffectState,
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
from runtime.tools.models import CommandResult


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
        (proposal.tasks[0].task_id,),
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


def _coding_ready(execution):
    service, _, plan = _plan(execution)
    service.create_runtime_work("product", plan.execution_plan_id)
    service.prepare_workspace(
        "product", plan.execution_plan_id, allow_product_write=True)
    service.create_feature_branch(
        "product", plan.execution_plan_id, allow_product_write=True)
    task = plan.ordered_task_executions[0].project_task_id
    request = service.submit_coding_task(
        "product", plan.execution_plan_id, task)
    return service, plan, task, request


def _successful_coding(execution):
    service, plan, task, request = _coding_ready(execution)
    result = _result(request)
    service.process_coding_result(
        "product", plan.execution_plan_id, request, result, "default")
    accepted_id = f"{plan.execution_plan_id}-{task}-accepted-1"
    return service, plan, request, result, accepted_id


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
    service, plan, _, request = _coding_ready(execution)
    with pytest.raises(ExecutionPolicyError):
        service.process_coding_result(
            "product", plan.execution_plan_id, request,
            _result(request, **changes), "default")


def test_coding_result_duplicate_and_failure_blocking(execution):
    service, plan, task, request = _coding_ready(execution)
    result = _result(request)
    assert service.process_coding_result(
        "product", plan.execution_plan_id, request, result, "default") == result
    assert service.manager_loader("product").current_state().task(
        task).status.value == "IN_PROGRESS"
    assert service.process_coding_result(
        "product", plan.execution_plan_id, request, result, "default") == result


def test_coding_result_requires_exact_submitted_request(execution):
    service, plan, _, request = _coding_ready(execution)
    forged = replace(request, objective=f"{request.objective} forged")
    with pytest.raises(ExecutionPolicyError):
        service.process_coding_result(
            "product", plan.execution_plan_id, forged,
            _result(forged), "default")


def test_managed_execution_provider_bridge_uses_observed_workspace(execution):
    service, plan, task_id, _ = _coding_ready(execution)
    provider = DeterministicCodingProvider(file_operations=(
        FileOperation(
            FileOperationKind.UPDATE, "app.py",
            "def value():\n    return 2\n"),))
    service.coding_provider_service = CodingProviderService(
        CodingProviderRegistry((provider,)),
        ProviderOperationStore(execution[4] / "provider-state"),
        CodingContextBuilder(), ControlledPatchApplier(),
        change_policies=tuple(service.change_policies.values()),
        git_provider_factory=service.git_provider_factory)
    operation, provider_request = service.prepare_provider_operation(
        "product", plan.execution_plan_id, task_id, "deterministic")
    result = service.accept_provider_result(
        "product", plan.execution_plan_id, task_id,
        operation.provider_operation_id, provider_request, "default")
    assert result.status == "SUCCEEDED"
    assert result.changed_files == ("app.py",)


@pytest.mark.parametrize("status", [
    "FAILED_RETRYABLE", "FAILED_PERMANENT", "TIMED_OUT", "CANCELLED"])
def test_provider_failures_block_project_task(execution, status):
    service, plan, task, request = _coding_ready(execution)
    service.process_coding_result(
        "product", plan.execution_plan_id, request,
        _result(request, status=status, changed_files=(), artifacts=(),
                provider_task_id=f"provider:{status}"),
        "default")
    assert service.manager_loader("product").current_state().task(
        task).status.value == "BLOCKED"


def test_quality_gate_pass_and_persistence(execution):
    service, plan, _, _, _ = _successful_coding(execution)
    results = service.run_quality_gates("product", plan.execution_plan_id, "offline")
    assert results[0].status == GateStatus.PASSED
    assert service.store.load_gate_results(
        "product", plan.execution_plan_id) == results


def test_review_evidence_digest_and_explicit_approval(execution):
    service, plan, _, _, accepted_id = _successful_coding(execution)
    service.run_quality_gates("product", plan.execution_plan_id, "offline")
    evidence = service.generate_review_evidence(
        "product", plan.execution_plan_id, (accepted_id,))
    assert len(evidence.integrity_digest) == 64
    with pytest.raises(ExecutionApprovalError):
        service.approve_review(
            "product", plan.execution_plan_id, "deterministic")
    decision = service.approve_review(
        "product", plan.execution_plan_id, "human-reviewer")
    assert decision.status == ReviewDecisionStatus.APPROVED


def test_review_rejection_requires_reason(execution):
    service, plan, _, _, accepted_id = _successful_coding(execution)
    service.run_quality_gates("product", plan.execution_plan_id, "offline")
    service.generate_review_evidence(
        "product", plan.execution_plan_id, (accepted_id,))
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
    service, plan, coding_request, result, accepted_id = _successful_coding(execution)
    workspace = service.store.load_workspace("product", plan.workspace_identity)
    path = Path(workspace.local_path) / "app.py"
    path.write_text("def value():\n    return 2\n", encoding="utf-8")
    service.run_quality_gates("product", plan.execution_plan_id, "offline")
    service.generate_review_evidence(
        "product", plan.execution_plan_id, (accepted_id,))
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


def _effect(service, kind):
    return next(
        item for item in service.store.list_effects("product")
        if item.kind == kind)


def test_workspace_crash_after_copy_reconciles_without_duplicate(
    execution, monkeypatch
):
    service, _, plan = _plan(execution)
    original = service.store.save_workspace
    calls = {"count": 0}

    def fail_once(value):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("injected workspace checkpoint failure")
        return original(value)

    monkeypatch.setattr(service.store, "save_workspace", fail_once)
    with pytest.raises(OSError):
        service.prepare_workspace(
            "product", plan.execution_plan_id, allow_product_write=True)
    monkeypatch.setattr(service.store, "save_workspace", original)
    record = service.prepare_workspace(
        "product", plan.execution_plan_id, allow_product_write=True)
    assert Path(record.local_path).is_dir()
    assert _effect(
        service, ExternalEffectKind.WORKSPACE_PREPARATION
    ).state == ExternalEffectState.COMPLETED


def test_branch_crash_after_creation_reconciles_exact_branch(
    execution, monkeypatch
):
    service, _, plan = _plan(execution)
    service.prepare_workspace(
        "product", plan.execution_plan_id, allow_product_write=True)
    git = service._git(plan.workspace_identity)
    original = git.create_branch

    def create_then_fail(path, branch):
        original(path, branch)
        raise OSError("lost branch response")

    monkeypatch.setattr(git, "create_branch", create_then_fail)
    monkeypatch.setattr(service, "git_provider_factory", lambda _: git)
    with pytest.raises(OSError):
        service.create_feature_branch(
            "product", plan.execution_plan_id, allow_product_write=True)
    monkeypatch.setattr(git, "create_branch", original)
    assert service.create_feature_branch(
        "product", plan.execution_plan_id,
        allow_product_write=True) == plan.feature_branch
    assert _effect(
        service, ExternalEffectKind.BRANCH_CREATION
    ).state == ExternalEffectState.COMPLETED


def test_commit_crash_after_success_reuses_exact_commit(execution, monkeypatch):
    service, plan = _reviewed_write(execution)
    git = service._git(plan.workspace_identity)
    original = git.commit
    commits = {"count": 0}

    def commit_then_fail(path, message):
        commits["count"] += 1
        original(path, message)
        raise OSError("lost commit response")

    monkeypatch.setattr(git, "commit", commit_then_fail)
    monkeypatch.setattr(service, "git_provider_factory", lambda _: git)
    with pytest.raises(OSError):
        service.create_commit(
            "product", plan.execution_plan_id, allow_product_write=True)
    monkeypatch.setattr(git, "commit", original)
    recovered = service.create_commit(
        "product", plan.execution_plan_id, allow_product_write=True)
    assert recovered == git.current_commit(
        service.store.load_workspace(
            "product", plan.workspace_identity).local_path)
    assert commits["count"] == 1


def test_push_crash_after_success_reuses_exact_remote_ref(execution, monkeypatch):
    service, plan = _reviewed_write(execution)
    service.create_commit(
        "product", plan.execution_plan_id, allow_product_write=True)
    git = service._git(plan.workspace_identity)
    original = git.push
    pushes = {"count": 0}

    def push_then_fail(path, remote, branch):
        pushes["count"] += 1
        original(path, remote, branch)
        raise OSError("lost push response")

    monkeypatch.setattr(git, "push", push_then_fail)
    monkeypatch.setattr(service, "git_provider_factory", lambda _: git)
    with pytest.raises(OSError):
        service.push_branch(
            "product", plan.execution_plan_id, allow_product_write=True)
    monkeypatch.setattr(git, "push", original)
    assert service.push_branch(
        "product", plan.execution_plan_id,
        allow_product_write=True) == "PUSHED"
    assert pushes["count"] == 1


def test_pr_crash_after_success_reuses_exact_draft(execution, monkeypatch):
    service, plan = _reviewed_write(execution)
    commit = service.create_commit(
        "product", plan.execution_plan_id, allow_product_write=True)
    service.push_branch(
        "product", plan.execution_plan_id, allow_product_write=True)
    service.github_provider.create_branch(
        plan.repository_identity, plan.feature_branch, commit)
    original = service.github_provider.create_draft_pull_request
    creates = {"count": 0}

    def create_then_fail(request):
        creates["count"] += 1
        original(request)
        raise OSError("lost PR response")

    monkeypatch.setattr(
        service.github_provider, "create_draft_pull_request", create_then_fail)
    with pytest.raises(OSError):
        service.create_draft_pull_request(
            "product", plan.execution_plan_id, allow_product_write=True)
    monkeypatch.setattr(
        service.github_provider, "create_draft_pull_request", original)
    recovered = service.create_draft_pull_request(
        "product", plan.execution_plan_id, allow_product_write=True)
    assert recovered.draft is True
    assert creates["count"] == 1


def test_divergent_branch_requires_reconciliation(execution, monkeypatch):
    service, _, plan = _plan(execution)
    service.prepare_workspace(
        "product", plan.execution_plan_id, allow_product_write=True)
    git = service._git(plan.workspace_identity)
    original = git.create_branch

    def create_then_fail(path, branch):
        original(path, branch)
        raise OSError("lost branch response")

    monkeypatch.setattr(git, "create_branch", create_then_fail)
    monkeypatch.setattr(service, "git_provider_factory", lambda _: git)
    with pytest.raises(OSError):
        service.create_feature_branch(
            "product", plan.execution_plan_id, allow_product_write=True)
    monkeypatch.setattr(git, "branch_commit", lambda *_: "divergent")
    with pytest.raises(ExecutionReconciliationError):
        service.create_feature_branch(
            "product", plan.execution_plan_id, allow_product_write=True)


def test_unpersisted_or_failed_coding_result_cannot_generate_evidence(execution):
    service, plan, _, request = _coding_ready(execution)
    service.store.save_operation(replace(
        service._operation(plan),
        phase=ExecutionOperationPhase.QUALITY_GATES_COMPLETED))
    now = datetime(2026, 1, 5, tzinfo=timezone.utc)
    gates = (QualityGateResult(
        f"{plan.execution_plan_id}-gate-1", "offline", GateStatus.PASSED,
        0, "", "", now, now),)
    service.store.save_gate_results("product", plan.execution_plan_id, gates)
    with pytest.raises(Exception):
        service.generate_review_evidence(
            "product", plan.execution_plan_id, ("not-persisted",))
    failed = _result(
        request, status="FAILED_PERMANENT", changed_files=(), artifacts=(),
        provider_task_id="failed:1")
    service.store.save_coding_result(AcceptedCodingResult(
        "failed-accepted", plan.execution_plan_id, plan.version, "product",
        plan.ordered_task_executions[0].project_task_id,
        request.external_task_id, request.workspace_id, request.branch,
        failed.provider_task_id, failed, now))
    with pytest.raises(ExecutionPolicyError):
        service.generate_review_evidence(
            "product", plan.execution_plan_id, ("failed-accepted",))


@pytest.mark.parametrize("stage", ["review", "commit", "push", "pr"])
def test_evidence_tampering_blocks_every_sensitive_stage(execution, stage):
    service, plan = _reviewed_write(execution)
    if stage in {"push", "pr"}:
        service.create_commit(
            "product", plan.execution_plan_id, allow_product_write=True)
    if stage == "pr":
        service.push_branch(
            "product", plan.execution_plan_id, allow_product_write=True)
    evidence = service.store.load_evidence(
        "product", f"{plan.execution_plan_id}-evidence-1")
    service.store.save_evidence(replace(
        evidence, warnings=("tampered",)))
    with pytest.raises(ExecutionPolicyError):
        if stage == "review":
            service.approve_review(
                "product", plan.execution_plan_id, "reviewer")
        elif stage == "commit":
            service.create_commit(
                "product", plan.execution_plan_id, allow_product_write=True)
        elif stage == "push":
            service.push_branch(
                "product", plan.execution_plan_id, allow_product_write=True)
        else:
            service.create_draft_pull_request(
                "product", plan.execution_plan_id, allow_product_write=True)


def test_unallowlisted_gate_executable_is_rejected(execution):
    service, plan, _, _, _ = _successful_coding(execution)
    service.gate_profiles["offline"] = QualityGateProfile(
        "offline", "product",
        (QualityGate("bad", ("bash", "-c", "echo unsafe"), 30),),
        ("python",))
    with pytest.raises(ExecutionPolicyError):
        service.run_quality_gates("product", plan.execution_plan_id, "offline")


def test_gate_environment_redaction_and_output_bounds(execution):
    service, plan, _, _, _ = _successful_coding(execution)

    class CapturingRunner:
        request = None

        def execute(self, request, *, cancellation=None):
            self.request = request
            now = datetime.now(timezone.utc)
            output = ("topsecret literal token=raw-secret " * 500)
            return CommandResult(
                request.executable, request.arguments, 0, output, output,
                now, now, 0.0, False)

    runner = CapturingRunner()
    service.command_runner = runner
    service.gate_environment = {"SAFE": "topsecret", "UNSAFE": "not-passed"}
    service.gate_profiles["offline"] = QualityGateProfile(
        "offline", "product",
        (QualityGate("safe", ("python", "-c", "print('ok')"), 30),),
        ("python",), ("SAFE",), redaction_rules=("literal",))
    result = service.run_quality_gates(
        "product", plan.execution_plan_id, "offline")[0]
    assert runner.request.environment == {"SAFE": "topsecret"}
    assert "topsecret" not in result.stdout
    assert "literal" not in result.stdout
    assert "raw-secret" not in result.stdout
    assert len(result.stdout) <= 4_000


@pytest.mark.parametrize("status", [
    ExecutionPlanStatus.FAILED,
    ExecutionPlanStatus.CANCELLED,
    ExecutionPlanStatus.SUCCEEDED,
    ExecutionPlanStatus.REJECTED,
    ExecutionPlanStatus.SUPERSEDED,
    ExecutionPlanStatus.RECONCILIATION_REQUIRED,
])
def test_terminal_plan_states_block_ordinary_execution(execution, status):
    service, _, plan = _plan(execution)
    service.store.save_plan(replace(plan, status=status))
    with pytest.raises(ExecutionApprovalError):
        service.create_runtime_work("product", plan.execution_plan_id)


def test_review_correction_cannot_proceed_to_commit(execution):
    service, plan, _, _, accepted_id = _successful_coding(execution)
    service.run_quality_gates("product", plan.execution_plan_id, "offline")
    service.generate_review_evidence(
        "product", plan.execution_plan_id, (accepted_id,))
    service.request_correction(
        "product", plan.execution_plan_id, "reviewer", "Correct it")
    with pytest.raises(ExecutionApprovalError):
        service.create_commit(
            "product", plan.execution_plan_id, allow_product_write=True)


def test_partial_runtime_mapping_is_safely_completed(execution):
    service, request, proposal, _, _ = execution
    all_request = replace(
        request, execution_request_id="execute-all",
        selected_task_ids=tuple(task.task_id for task in proposal.tasks),
        requested_branch_name="ascos/all")
    service.create_execution_request(all_request)
    plan = service.generate_execution_plan(
        "product", all_request.execution_request_id)
    plan = service.approve_execution_plan(
        "product", plan.execution_plan_id, "reviewer")
    first = plan.ordered_task_executions[0]
    from runtime.managed_execution import RuntimeTaskMapping
    service.store.save_mapping("product", RuntimeTaskMapping(
        first.project_task_id, first.runtime_work_item_id,
        plan.runtime_work_package_id, plan.execution_request_id,
        plan.execution_plan_id))
    mappings = service.create_runtime_work("product", plan.execution_plan_id)
    assert len(mappings) == len(plan.ordered_task_executions)
    assert len({mapping.runtime_work_item_id for mapping in mappings}) == len(mappings)
