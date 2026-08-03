from dataclasses import replace
from datetime import datetime, timezone

import pytest

from runtime.pilots.first_managed_product import (
    BASE_BRANCH,
    CodexSmokeRootCauseRecord,
    FEATURE_BRANCH,
    KnowledgeSnapshotBinding,
    MILESTONE_ID,
    PILOT_ID,
    PROJECT_ID,
    ManagedProductPilotRecord,
    PilotRecordStore,
    PilotStatus,
    RepositoryBaseline,
    learner_web_shell_request,
    pilot_tasks,
    validate_task_graph,
)


def baseline(**overrides):
    values = dict(
        project_id=PROJECT_ID,
        repository_identity="https://github.com/NagarajuMarri/spoken-english-ai",
        default_branch="main",
        origin_main_sha="4c88b7edcb306ba736237e0cbcc289b5ca479543",
        local_main_sha="4c88b7edcb306ba736237e0cbcc289b5ca479543",
        current_branch="product/milestone-7-ai-conversation-voice",
        local_branches=("main", "product/milestone-7-ai-conversation-voice"),
        remote_branches=("origin/main", "origin/product/milestone-7-ai-conversation-voice"),
        working_tree_clean=True,
        local_main_divergent=False,
        latest_merged_milestone="Product Milestone 6",
        milestone_7_local=True,
        milestone_7_remote=True,
        milestone_7_commit="cdeb27ab9eea2325a2b76c4580b2b1668dc07422",
        milestone_7_reachable_from=("product/milestone-7-ai-conversation-voice",),
        milestone_7_pull_request=None,
        unresolved_discrepancies=("Milestone 7 has no pull request",),
        inspected_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return RepositoryBaseline(**values).with_digest()


@pytest.mark.parametrize("changes", [
    {"milestone_7_local": False, "milestone_7_remote": True},
    {"milestone_7_local": True, "milestone_7_remote": False},
    {"milestone_7_local": False, "milestone_7_remote": False,
     "milestone_7_commit": None, "milestone_7_reachable_from": ()},
    {"milestone_7_local": False, "milestone_7_remote": False,
     "milestone_7_reachable_from": ()},
])
def test_milestone_7_reconciliation_states_are_recorded(changes):
    observed = baseline(**changes)
    assert observed.reconciliation_status == PilotStatus.BASELINE_RECONCILED
    assert len(observed.evidence_digest) == 64


@pytest.mark.parametrize("changes", [
    {"working_tree_clean": False},
    {"local_main_divergent": True},
])
def test_unsafe_repository_state_requires_reconciliation(changes):
    assert baseline(**changes).reconciliation_status == PilotStatus.RECONCILIATION_REQUIRED


def test_request_is_exactly_sha_bound_by_protocol_constraint():
    request = learner_web_shell_request()
    assert request.project_id == PROJECT_ID
    assert request.requested_by == "NagarajuMarri"
    assert request.preferred_base_branch == BASE_BRANCH
    assert "reconciled origin/main SHA" in " ".join(request.constraints)
    assert "STT" in request.out_of_scope


def test_bounded_dependency_ordered_tasks_cover_feature_scope():
    tasks = pilot_tasks()
    validate_task_graph(tasks)
    assert len(tasks) == 6
    assert tasks[-1].dependencies == ("accessibility",)
    assert all(task.maximum_output_bytes <= 96_000 for task in tasks)
    assert all(task.maximum_attempts == 1 for task in tasks)
    assert {task.risk_classification for task in tasks} == {"MEDIUM", "HIGH"}


def test_dependency_order_violation_is_blocked():
    tasks = pilot_tasks()
    with pytest.raises(ValueError, match="dependency ordered"):
        validate_task_graph((replace(tasks[0], dependencies=("missing",)),))


def test_provider_cannot_be_approval_actor():
    request = learner_web_shell_request(requested_by="NagarajuMarri")
    assert request.requested_by != "openai-codex"
    assert request.requested_by != "deterministic"


def test_provider_configuration_required_record_is_durable(tmp_path):
    observed = baseline()
    tasks = pilot_tasks()
    record = ManagedProductPilotRecord(
        PILOT_ID, PROJECT_ID, PilotStatus.PROVIDER_CONFIGURATION_REQUIRED,
        observed.evidence_digest, "knowledge-main-4c88b7e", request_id(),
        "proposal-learner-web-shell-v1", "NagarajuMarri", MILESTONE_ID,
        tuple(task.task_id for task in tasks), None, (), (), None, FEATURE_BRANCH,
        (), (), None, None, None, None, None, "BASELINE_RECONCILED",
        ("Live coding provider credential is not configured.",
         "No product mutation, branch, commit, push, PR, merge, or deployment occurred."),
    )
    store = PilotRecordStore(tmp_path / "ascos-state")
    path = store.save(record)
    assert "spoken-english-ai" in path.parts
    assert path.is_relative_to(tmp_path / "ascos-state")
    assert store.load()["status"] == "PROVIDER_CONFIGURATION_REQUIRED"
    store.update_status(PilotStatus.CODEX_LIVE_SMOKE_TEST_REQUIRED, "Live fixture mismatch.")
    assert store.load()["status"] == "CODEX_LIVE_SMOKE_TEST_REQUIRED"


def test_baseline_and_knowledge_sha_binding_are_durable(tmp_path):
    store = PilotRecordStore(tmp_path)
    observed = baseline()
    binding = KnowledgeSnapshotBinding(
        "snapshot-main", PROJECT_ID, observed.origin_main_sha, "scan-digest",
        (".git", ".env", "node_modules", ".venv"),
        (("api", ("backend/app/api/routes",)),), (("test", "pytest"),),
    )
    assert store.save_baseline(observed).is_file()
    assert store.save_knowledge_binding(binding).is_file()
    root_cause = CodexSmokeRootCauseRecord(
        "operation", "request-digest", 1, "EMPTY_OPERATIONS",
        "VALID_ENVELOPE_WITH_ZERO_OPERATIONS", "NO_WORKSPACE_CHANGES",
        "PROMPT_AMBIGUITY_AND_FORBIDDEN_NO_CHANGE_SUCCESS",
    )
    assert store.save_codex_root_cause(root_cause).is_file()


def request_id():
    return learner_web_shell_request().request_id


def test_pilot_state_cannot_leak_to_unrelated_identity(tmp_path):
    record = ManagedProductPilotRecord(
        "wrong", PROJECT_ID, PilotStatus.FAILED, "digest", "snapshot", "request",
        "proposal", "NagarajuMarri", MILESTONE_ID, (), None, (), (), None,
        FEATURE_BRANCH, (), (), None, None, None, None, None, "FAILED", (),
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        PilotRecordStore(tmp_path).save(record)
