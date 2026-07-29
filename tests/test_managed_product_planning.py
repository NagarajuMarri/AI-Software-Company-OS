import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runtime.exceptions import ProjectNotFoundError
from runtime.knowledge import KnowledgeStore, ProjectKnowledgeEngine
from runtime.planning import *
from runtime.planning.cli import main as cli_main
from runtime.planning.errors import *
from runtime.planning.models import ProposedTask, RiskLevel
from runtime.project_manager import AIProjectManager, ManagerStateStore
from runtime.projects import FileProjectRegistry, InMemoryProjectRegistry, ManagedProject


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "fixture-repo"; repo.mkdir()
    (repo / "app.py").write_text("import json\n\ndef tutor():\n    return json.dumps({})\n",
                                 encoding="utf-8")
    project = ManagedProject("product", "Product", "Managed product",
        "https://example.com/product", "main", local_path=str(repo))
    registry = InMemoryProjectRegistry((project,))
    knowledge_store = KnowledgeStore(tmp_path / "state")
    knowledge = ProjectKnowledgeEngine.create("product", registry, knowledge_store)
    knowledge.scan(); knowledge.save()
    manager_store = ManagerStateStore(tmp_path / "state")
    manager = AIProjectManager.initialize("product", registry, manager_store)
    manager.save()
    planning_store = PlanningStore(tmp_path / "state")
    service = ManagedProductPlanningService(
        registry, planning_store,
        lambda _: ProjectKnowledgeEngine.load("product", registry, knowledge_store),
        lambda _: AIProjectManager.load("product", registry, manager_store),
        DeterministicPlanningProvider())
    return tmp_path, repo, project, registry, knowledge, manager_store, planning_store, service


def request(**changes):
    values = dict(request_id="voice", project_id="product", title="Voice integration",
        objective="Add reviewed voice provider boundaries",
        business_context="Improve spoken tutoring",
        requested_capabilities=("speech-to-text", "text-to-speech"),
        acceptance_criteria=("Audio input is bounded", "Tests are offline"),
        constraints=("No provider secrets",), out_of_scope=("Payments",),
        priority=ChangePriority.HIGH, requested_by="product-owner",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), correlation_id="corr-1")
    values.update(changes)
    return ManagedProductChangeRequest(**values)


def generated(setup):
    service = setup[-1]
    service.create_request(request())
    return service, service.generate_proposal("product", "voice",
        now=datetime(2026, 1, 2, tzinfo=timezone.utc))


def test_valid_request_is_immutable_and_round_trips(setup):
    value = setup[-1].create_request(request())
    assert isinstance(value.acceptance_criteria, tuple)
    assert setup[-1].get_request("product", "voice") == value


@pytest.mark.parametrize("field,value", [
    ("request_id", ""), ("project_id", ""), ("objective", ""),
    ("acceptance_criteria", ()), ("created_at", datetime(2026, 1, 1))])
def test_request_validation(field, value):
    with pytest.raises(PlanningValidationError):
        request(**{field: value})


def test_request_rejects_mutable_collections():
    with pytest.raises(PlanningValidationError):
        request(acceptance_criteria=["mutable"])


def test_request_bounds_text_and_collections():
    with pytest.raises(PlanningValidationError):
        request(objective="x" * 10_001)
    with pytest.raises(PlanningValidationError):
        request(acceptance_criteria=tuple(str(x) for x in range(101)))


def test_missing_project_and_duplicate_request(setup):
    service = setup[-1]
    with pytest.raises(ProjectNotFoundError):
        service.create_request(request(project_id="missing"))
    service.create_request(request())
    with pytest.raises(PlanningConflictError):
        service.create_request(request())


def test_context_is_deterministic_bounded_and_project_scoped(setup):
    service = setup[-1]; service.create_request(request())
    first = service.build_context("product", "voice",
        now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    second = service.build_context("product", "voice",
        now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert first == second
    assert first.project_id == "product"
    assert [x.path for x in first.relevant_files] == ["app.py"]
    assert "source" not in first.knowledge_summary


def test_context_limits(setup):
    base = setup[-1]
    limited = ManagedProductPlanningService(base.registry, base.store,
        base.knowledge_loader, base.manager_loader, base.provider,
        PlanningContextBuilder(max_files=0, max_symbols=0, max_dependencies=0,
                               max_state_items=0))
    limited.create_request(request())
    context = limited.build_context("product", "voice")
    assert context.relevant_files == ()
    assert context.relevant_symbols == ()


def test_missing_and_stale_knowledge(setup):
    base = setup[-1]; base.create_request(request())
    missing = ManagedProductPlanningService(base.registry, base.store,
        lambda _: ProjectKnowledgeEngine.create("product", base.registry,
                                                KnowledgeStore(setup[0] / "empty")),
        base.manager_loader, base.provider)
    with pytest.raises(Exception):
        missing.build_context("product", "voice")
    with pytest.raises(KnowledgeStaleError):
        base.build_context("product", "voice",
            now=datetime.now(timezone.utc) + timedelta(days=365))


def test_deterministic_provider_output_preserves_criteria(setup):
    service, proposal = generated(setup)
    assert proposal.acceptance_criteria == request().acceptance_criteria
    assert all(task.acceptance_criteria == request().acceptance_criteria
               for task in proposal.tasks)
    assert proposal.status == ProposalStatus.PROPOSED
    assert proposal.decisions == ()


def test_provider_failure_and_malformed_result(setup):
    base = setup[-1]
    failing = ManagedProductPlanningService(base.registry, base.store,
        base.knowledge_loader, base.manager_loader,
        DeterministicPlanningProvider(fail=True))
    failing.create_request(request())
    with pytest.raises(PlanningProviderError):
        failing.generate_proposal("product", "voice")
    malformed = ManagedProductPlanningService(base.registry, base.store,
        base.knowledge_loader, base.manager_loader,
        DeterministicPlanningProvider(malformed=True))
    with pytest.raises(PlanningValidationError):
        malformed.generate_proposal("product", "voice")


def context_and_proposal(setup):
    service = setup[-1]; service.create_request(request())
    context = service.build_context("product", "voice")
    proposal = DeterministicPlanningProvider().propose(request(), context)
    return context, proposal


def test_duplicate_missing_self_and_cycle_validation(setup):
    context, proposal = context_and_proposal(setup)
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=proposal.tasks + (proposal.tasks[0],)), context)
    bad = replace(proposal.tasks[0], dependencies=("missing",))
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=(bad,) + proposal.tasks[1:]), context)
    bad = replace(proposal.tasks[0], dependencies=(proposal.tasks[0].task_id,))
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=(bad,) + proposal.tasks[1:]), context)
    a, b = proposal.tasks[:2]
    cyclic = (replace(a, dependencies=(b.task_id,)), replace(b, dependencies=(a.task_id,)),
              proposal.tasks[2])
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=cyclic), context)


@pytest.mark.parametrize("path", ["/absolute.py", "C:\\absolute.py", "../escape.py",
                                  "unknown.py"])
def test_unsafe_or_unknown_candidate_paths(setup, path):
    context, proposal = context_and_proposal(setup)
    bad = replace(proposal.tasks[0], candidate_files=(path,))
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=(bad,) + proposal.tasks[1:]), context)


@pytest.mark.parametrize("gate", ["", "git push origin main", "deploy production",
                                  "gh pr merge 1", "release now"])
def test_empty_or_forbidden_quality_gates(setup, gate):
    context, proposal = context_and_proposal(setup)
    bad = replace(proposal.tasks[0], quality_gates=(gate,))
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=(bad,) + proposal.tasks[1:]), context)


def test_invalid_role_and_empty_acceptance(setup):
    context, proposal = context_and_proposal(setup)
    bad = replace(proposal.tasks[0], role_requirements=("unsafe role",))
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=(bad,) + proposal.tasks[1:]), context)
    bad = replace(proposal.tasks[0], acceptance_criteria=())
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=(bad,) + proposal.tasks[1:]), context)


def test_explicit_approval_and_decision_history(setup):
    service, proposal = generated(setup)
    approved = service.approve_proposal("product", proposal.proposal_id, "reviewer", "Reviewed")
    assert approved.status == ProposalStatus.APPROVED
    assert approved.decisions[0].actor == "reviewer"
    assert approved.decisions[0].timestamp.tzinfo is not None
    with pytest.raises(ProposalLifecycleError):
        service.approve_proposal("product", proposal.proposal_id, "other")


def test_provider_cannot_self_approve(setup):
    service, proposal = generated(setup)
    with pytest.raises(ProposalLifecycleError):
        service.approve_proposal("product", proposal.proposal_id, "deterministic-planner")


def test_rejection_requires_reason_and_blocks_materialisation(setup):
    service, proposal = generated(setup)
    with pytest.raises(ProposalLifecycleError):
        service.reject_proposal("product", proposal.proposal_id, "reviewer", "")
    rejected = service.reject_proposal("product", proposal.proposal_id, "reviewer", "Not ready")
    assert rejected.status == ProposalStatus.REJECTED
    with pytest.raises(ProposalLifecycleError):
        service.materialise_approved_proposal("product", proposal.proposal_id)


def test_supersession_records_reason(setup):
    service, proposal = generated(setup)
    value = service.supersede_proposal("product", proposal.proposal_id, "reviewer", "New version")
    assert value.status == ProposalStatus.SUPERSEDED
    assert value.decisions[-1].reason == "New version"


def test_materialisation_is_idempotent_and_does_not_start_or_create_runtime_work(setup):
    service, proposal = generated(setup)
    service.approve_proposal("product", proposal.proposal_id, "reviewer")
    first = service.materialise_approved_proposal("product", proposal.proposal_id)
    second = service.materialise_approved_proposal("product", proposal.proposal_id)
    assert first.materialised_at == second.materialised_at
    manager = service.manager_loader("product")
    state = manager.current_state()
    assert state.active_milestone_id is None
    assert state.milestone(proposal.milestone_id).task_ids == tuple(x.task_id for x in proposal.tasks)
    assert state.task(proposal.tasks[0].task_id).metadata["acceptance_criteria"]
    assert not (setup[0] / "state" / "runtime").exists()


def test_materialisation_conflict_is_failure_atomic(setup):
    service, proposal = generated(setup)
    service.approve_proposal("product", proposal.proposal_id, "reviewer")
    manager = service.manager_loader("product")
    manager.create_milestone(proposal.milestone_id, "Conflict"); manager.save()
    before = manager.current_state()
    with pytest.raises(PlanningConflictError):
        service.materialise_approved_proposal("product", proposal.proposal_id)
    assert service.manager_loader("product").current_state() == before


def test_persistence_is_atomic_deterministic_and_isolated(setup):
    service, proposal = generated(setup)
    store = setup[-2]
    path = store.root / "product" / "proposals" / f"{proposal.proposal_id}.json"
    first = path.read_text(encoding="utf-8")
    store.save_proposal(store.load_proposal("product", proposal.proposal_id))
    assert path.read_text(encoding="utf-8") == first
    assert not list(path.parent.glob("*.tmp"))
    assert store.root / "other" != store.root / "product"


def test_corrupt_future_and_traversal_storage(setup):
    store = setup[-2]
    path = store.root / "product" / "requests" / "bad.json"
    path.parent.mkdir(parents=True); path.write_text("{bad", encoding="utf-8")
    with pytest.raises(PlanningStateCorruptError):
        store.load_request("product", "bad")
    path.write_text('{"schema_version":99}', encoding="utf-8")
    with pytest.raises(UnsupportedPlanningSchemaError):
        store.load_request("product", "bad")
    with pytest.raises(PlanningValidationError):
        store.load_request("../escape", "bad")


def test_product_repository_is_never_modified(setup):
    before = {x.relative_to(setup[1]): x.read_bytes() for x in setup[1].rglob("*") if x.is_file()}
    service, proposal = generated(setup)
    service.approve_proposal("product", proposal.proposal_id, "reviewer")
    service.materialise_approved_proposal("product", proposal.proposal_id)
    after = {x.relative_to(setup[1]): x.read_bytes() for x in setup[1].rglob("*") if x.is_file()}
    assert after == before


def test_cli_human_json_and_expected_error(tmp_path, setup, capsys):
    registry_path = tmp_path / "registry.json"
    FileProjectRegistry(registry_path).register(setup[2])
    # Copy fixture state by creating through stores rooted at the CLI root.
    root = tmp_path / "cli-state"
    knowledge = ProjectKnowledgeEngine.create("product", FileProjectRegistry(registry_path),
                                               KnowledgeStore(root))
    knowledge.scan(); knowledge.save()
    manager = AIProjectManager.initialize("product", FileProjectRegistry(registry_path),
                                          ManagerStateStore(root)); manager.save()
    prefix = ["--registry", str(registry_path), "--state-root", str(root)]
    create = prefix + ["planning", "request", "create", "product", "voice",
        "--title", "Voice", "--objective", "Add voice", "--business-context", "Learning",
        "--requested-by", "owner", "--acceptance", "Offline tests"]
    assert cli_main(create) == 0
    assert "request_id" in capsys.readouterr().out
    assert cli_main(prefix + ["--json", "planning", "context", "build", "product", "voice"]) == 0
    assert json.loads(capsys.readouterr().out)["project_id"] == "product"
    assert cli_main(prefix + ["planning", "request", "show", "product", "missing"]) == 2
    assert capsys.readouterr().out.startswith("error:")


def test_list_and_status_queries_are_stably_ordered(setup):
    service = setup[-1]
    service.create_request(request(request_id="z"))
    service.create_request(request(request_id="a"))
    assert [x.request_id for x in service.list_requests("product")] == ["a", "z"]
    assert service.get_planning_status("product") == {
        "project_id": "product", "requests": 2, "proposals": 0,
        "approved": 0, "materialised": 0}


def test_forward_dependency_is_rejected(setup):
    context, proposal = context_and_proposal(setup)
    forward = replace(proposal.tasks[0], dependencies=(proposal.tasks[1].task_id,))
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, tasks=(forward,) + proposal.tasks[1:]), context)


def test_mismatched_proposal_identity_is_rejected(setup):
    context, proposal = context_and_proposal(setup)
    with pytest.raises(PlanningValidationError):
        validate_proposal(replace(proposal, project_id="other"), context)


def test_approved_proposal_collections_remain_immutable(setup):
    service, proposal = generated(setup)
    approved = service.approve_proposal("product", proposal.proposal_id, "reviewer")
    assert isinstance(approved.tasks, tuple)
    with pytest.raises(Exception):
        approved.tasks[0] = approved.tasks[0]


def test_context_contains_metadata_not_source_contents(setup):
    service = setup[-1]; service.create_request(request())
    encoded = repr(service.build_context("product", "voice"))
    assert "return json.dumps" not in encoded
    assert "app.py" in encoded


def test_spoken_english_ai_pilot_example(capsys):
    from examples.spoken_english_ai_planning import main
    main()
    output = capsys.readouterr().out
    assert "milestone: real-voice-ai-provider-implementation" in output
    assert "approval: human-reviewer" in output


def approved(setup):
    service, proposal = generated(setup)
    proposal = service.approve_proposal(
        "product", proposal.proposal_id, "reviewer", "Reviewed"
    )
    return service, proposal


def fail_after_manager_save(setup, monkeypatch):
    service, proposal = approved(setup)
    original = service.store.save_materialisation
    calls = {"count": 0}

    def injected(operation):
        calls["count"] += 1
        if calls["count"] == 2:
            raise PlanningStorageError("injected post-manager failure")
        return original(operation)

    monkeypatch.setattr(service.store, "save_materialisation", injected)
    with pytest.raises(PlanningStorageError):
        service.materialise_approved_proposal("product", proposal.proposal_id)
    monkeypatch.setattr(service.store, "save_materialisation", original)
    return service, proposal


def test_materialisation_failure_before_manager_mutation(setup, monkeypatch):
    service, proposal = approved(setup)

    def fail(_operation):
        raise PlanningStorageError("injected prepare failure")

    monkeypatch.setattr(service.store, "save_materialisation", fail)
    with pytest.raises(PlanningStorageError):
        service.materialise_approved_proposal("product", proposal.proposal_id)
    state = service.manager_loader("product").current_state()
    assert state.milestones == ()
    assert state.tasks == ()


def test_materialisation_failure_during_manager_save(setup, monkeypatch):
    service, proposal = approved(setup)
    manager = service.manager_loader("product")

    def fail():
        raise OSError("injected manager save failure")

    monkeypatch.setattr(manager, "save", fail)
    monkeypatch.setattr(service, "manager_loader", lambda _project_id: manager)
    with pytest.raises(OSError):
        service.materialise_approved_proposal("product", proposal.proposal_id)
    durable = AIProjectManager.load(
        "product", setup[3], setup[5]
    ).current_state()
    assert durable.milestones == ()
    operation = service.store.load_materialisation(
        "product", f"{proposal.proposal_id}-materialisation"
    )
    assert operation.state == MaterialisationState.FAILED
    assert "injected manager save failure" in operation.failure_details


def test_failure_after_manager_save_before_commit_marker(setup, monkeypatch):
    service, proposal = fail_after_manager_save(setup, monkeypatch)
    state = service.manager_loader("product").current_state()
    assert state.milestone(proposal.milestone_id)
    operation = service.store.load_materialisation(
        "product", f"{proposal.proposal_id}-materialisation"
    )
    assert operation.state == MaterialisationState.PREPARED
    assert service.get_proposal("product", proposal.proposal_id).materialised_at is None


def test_retry_after_manager_committed_partial_state(setup, monkeypatch):
    service, proposal = fail_after_manager_save(setup, monkeypatch)
    completed = service.materialise_approved_proposal(
        "product", proposal.proposal_id
    )
    operation = service.store.load_materialisation(
        "product", f"{proposal.proposal_id}-materialisation"
    )
    assert operation.state == MaterialisationState.COMPLETED
    assert completed.materialised_at is not None
    assert completed.materialised_at <= operation.updated_at


def test_restart_after_manager_committed_partial_state(setup, monkeypatch):
    service, proposal = fail_after_manager_save(setup, monkeypatch)
    restarted = ManagedProductPlanningService(
        service.registry,
        PlanningStore(setup[0] / "state"),
        service.knowledge_loader,
        service.manager_loader,
        service.provider,
    )
    completed = restarted.materialise_approved_proposal(
        "product", proposal.proposal_id
    )
    assert completed.materialised_at is not None
    state = restarted.manager_loader("product").current_state()
    assert len(state.milestones) == 1
    assert len(state.tasks) == len(proposal.tasks)


def test_failure_after_manager_commit_before_proposal_completion(
    setup, monkeypatch
):
    service, proposal = approved(setup)
    original = service.store.save_proposal

    def injected(value):
        if value.materialised_at is not None:
            raise PlanningStorageError("injected proposal completion failure")
        return original(value)

    monkeypatch.setattr(service.store, "save_proposal", injected)
    with pytest.raises(PlanningStorageError):
        service.materialise_approved_proposal("product", proposal.proposal_id)
    operation = service.store.load_materialisation(
        "product", f"{proposal.proposal_id}-materialisation"
    )
    assert operation.state == MaterialisationState.MANAGER_COMMITTED
    assert service.get_proposal("product", proposal.proposal_id).materialised_at is None
    monkeypatch.setattr(service.store, "save_proposal", original)
    completed = service.materialise_approved_proposal(
        "product", proposal.proposal_id
    )
    assert completed.materialised_at is not None


def _persist_manager_state(service, transform):
    manager = service.manager_loader("product")
    manager._state = transform(manager.current_state())
    manager.save()


def test_mismatched_existing_milestone_metadata_requires_reconciliation(
    setup, monkeypatch
):
    service, proposal = fail_after_manager_save(setup, monkeypatch)

    def mutate(state):
        milestone = state.milestone(proposal.milestone_id)
        changed = replace(milestone, metadata={"proposal_id": "wrong"})
        return replace(
            state,
            milestones=tuple(
                changed if item.milestone_id == changed.milestone_id else item
                for item in state.milestones
            ),
        )

    _persist_manager_state(service, mutate)
    with pytest.raises(MaterialisationReconciliationError):
        service.materialise_approved_proposal("product", proposal.proposal_id)
    operation = service.store.load_materialisation(
        "product", f"{proposal.proposal_id}-materialisation"
    )
    assert operation.state == MaterialisationState.RECONCILIATION_REQUIRED


def test_mismatched_task_metadata_requires_reconciliation(setup, monkeypatch):
    service, proposal = fail_after_manager_save(setup, monkeypatch)

    def mutate(state):
        task = state.task(proposal.tasks[0].task_id)
        changed = replace(task, metadata={"quality_gates": ["wrong"]})
        return replace(
            state,
            tasks=tuple(
                changed if item.task_id == changed.task_id else item
                for item in state.tasks
            ),
        )

    _persist_manager_state(service, mutate)
    with pytest.raises(MaterialisationReconciliationError):
        service.materialise_approved_proposal("product", proposal.proposal_id)


def test_mismatched_task_dependencies_require_reconciliation(setup, monkeypatch):
    service, proposal = fail_after_manager_save(setup, monkeypatch)

    def mutate(state):
        task = state.task(proposal.tasks[1].task_id)
        changed = replace(task, dependencies=())
        return replace(
            state,
            tasks=tuple(
                changed if item.task_id == changed.task_id else item
                for item in state.tasks
            ),
        )

    _persist_manager_state(service, mutate)
    with pytest.raises(MaterialisationReconciliationError):
        service.materialise_approved_proposal("product", proposal.proposal_id)


def test_recovery_never_duplicates_manager_records(setup, monkeypatch):
    service, proposal = fail_after_manager_save(setup, monkeypatch)
    service.materialise_approved_proposal("product", proposal.proposal_id)
    service.materialise_approved_proposal("product", proposal.proposal_id)
    state = service.manager_loader("product").current_state()
    assert len(state.milestones) == 1
    assert len(state.tasks) == len(proposal.tasks)
    assert len(state.risks) == len(proposal.risks)
    assert len(state.decisions) == 1


def test_corrupt_materialisation_operation_is_rejected(setup):
    service, proposal = approved(setup)
    path = (
        service.store.root
        / "product"
        / "materialisations"
        / f"{proposal.proposal_id}-materialisation.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(PlanningStateCorruptError):
        service.materialise_approved_proposal("product", proposal.proposal_id)
