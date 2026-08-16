import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from runtime.product_requirements import *
from runtime.product_requirements.models import RevisionRecord

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
LATER = datetime(2026, 1, 2, tzinfo=timezone.utc)


def requirement(**changes):
    values = dict(requirement_id="req-1", title="Secure login", description="Authenticate learners",
                  rationale="Protect learner data", acceptance_criteria=("Valid login succeeds",),
                  priority=RequirementPriority.CRITICAL, milestone="Milestone 1",
                  status=RequirementStatus.DRAFT, version="1.0", author="owner", approver=None,
                  created_at=NOW, updated_at=NOW, affected_products=("product",),
                  tags=("security",), category=RequirementCategory.SECURITY)
    values.update(changes); return ProductRequirement(**values)


def prd(**changes):
    values = dict(prd_id="prd", product_id="product", title="Product PRD", version="1.0",
                  status=RequirementStatus.DRAFT, author="owner", approver=None,
                  requirements=(requirement(),), explicit_exclusions=("Admin portal",),
                  future_roadmap=("More tutors",),
                  revision_history=(RevisionRecord("1.0", "owner", "CREATED", "Initial", NOW),),
                  created_at=NOW, updated_at=NOW)
    values.update(changes); return ProductRequirementsDocument(**values)


@pytest.fixture
def service(tmp_path):
    return ProductRequirementsService(ProductRequirementsStore(tmp_path))


def test_requirement_model_supports_all_categories_and_metadata():
    assert {item.value for item in RequirementCategory} == {
        "FUNCTIONAL", "NON_FUNCTIONAL", "SECURITY", "PRIVACY", "ACCESSIBILITY",
        "PERFORMANCE", "ARCHITECTURE", "COMMERCIAL", "DEPLOYMENT", "FUTURE_ROADMAP"}
    assert requirement().affected_products == ("product",)


def test_lifecycle_has_exact_controlled_states():
    assert [item.value for item in RequirementStatus] == [
        "DRAFT", "UNDER_REVIEW", "APPROVED", "LOCKED", "IMPLEMENTED", "SUPERSEDED", "ARCHIVED"]


def test_valid_lifecycle_approval_and_lock(service):
    created=service.create_prd(prd()); reviewed=service.submit_for_review(created,"owner",LATER)
    approved=service.approve(reviewed,"reviewer",LATER); locked=service.lock(approved,"reviewer",LATER)
    assert locked.status is RequirementStatus.LOCKED
    assert locked.requirements[0].status is RequirementStatus.LOCKED
    assert [item.action for item in locked.revision_history][-3:] == ["UNDER_REVIEW", "APPROVED", "LOCKED"]


def test_invalid_lifecycle_is_rejected():
    with pytest.raises(ValueError): transition_requirement(requirement(), RequirementStatus.LOCKED, "actor", LATER)


@pytest.mark.parametrize("field,code", [
    ("acceptance_criteria", "MISSING_ACCEPTANCE_CRITERIA"),
    ("rationale", "MISSING_RATIONALE"), ("milestone", "MISSING_MILESTONE")])
def test_validation_detects_missing_fields(field, code):
    value=replace(requirement(), **{field: () if field=="acceptance_criteria" else ""})
    assert code in {item.code for item in validate_requirements((value,))}


def test_validation_detects_missing_approval():
    value=replace(requirement(), status=RequirementStatus.APPROVED)
    assert validate_requirements((value,))[0].code == "MISSING_APPROVAL"


def test_validation_detects_duplicates_and_conflicts():
    duplicate=replace(requirement(), requirement_id="req-2", title="  SECURE   LOGIN ")
    conflict=replace(requirement(), conflicts_with=("req-2",))
    codes={item.code for item in validate_requirements((conflict, duplicate))}
    assert {"DUPLICATE_REQUIREMENT", "CONFLICTING_REQUIREMENTS"} <= codes


def test_store_round_trip_is_atomic_and_versioned(service, tmp_path):
    value=service.create_prd(prd()); loaded=service.store.load_prd("product","prd","1.0")
    assert loaded == value
    assert not list(tmp_path.rglob("*.tmp"))


def test_locked_version_is_immutable(service):
    reviewed=service.submit_for_review(service.create_prd(prd()),"owner",LATER)
    locked=service.lock(service.approve(reviewed,"reviewer",LATER),"reviewer",LATER)
    with pytest.raises(ValueError): service.store.save_prd(replace(locked,title="Changed"))


def test_revision_and_diff(service):
    reviewed=service.submit_for_review(service.create_prd(prd()),"owner",LATER)
    locked=service.lock(service.approve(reviewed,"reviewer",LATER),"reviewer",LATER)
    revised=service.revise(locked,"2.0","owner","New capability",LATER)
    added=replace(revised.requirements[0],requirement_id="req-2",title="New capability")
    revised=replace(revised,requirements=revised.requirements+(added,))
    diff=service.diff(locked,revised)
    assert diff.added == ("req-2",) and diff.changed == ("req-1",)


def test_superseding_records_history(service):
    reviewed=service.submit_for_review(service.create_prd(prd()),"owner",LATER)
    locked=service.lock(service.approve(reviewed,"reviewer",LATER),"reviewer",LATER)
    superseded=service.supersede(locked,"reviewer","Version 2",LATER)
    assert superseded.status is RequirementStatus.SUPERSEDED
    assert superseded.revision_history[-1].reason == "Version 2"


def test_roadmap_uses_only_approved_requirements(service):
    draft=prd(requirements=(requirement(),replace(requirement(),requirement_id="req-2",title="Draft",milestone="Milestone 2")))
    assert service.roadmap(draft) == ()
    reviewed=service.submit_for_review(service.create_prd(draft),"owner",LATER)
    approved=service.approve(reviewed,"reviewer",LATER)
    assert [item.milestone for item in service.roadmap(approved)] == ["Milestone 1", "Milestone 2"]


def test_traceability_persists_complete_chain(service):
    reviewed=service.submit_for_review(service.create_prd(prd()),"owner",LATER)
    approved=service.approve(reviewed,"reviewer",LATER)
    trace=ImplementationTrace("trace-1","req-1","task-1","a"*40,"https://example.test/pr/1","release-1",LATER)
    service.trace_implementation(approved,trace)
    assert service.store.load_trace("product","trace-1") == trace


def test_trace_rejects_unknown_or_unapproved_requirement(service):
    trace=ImplementationTrace("trace-1","missing","task-1","a"*40,"https://example.test/pr/1","release-1",LATER)
    with pytest.raises(ValueError): service.trace_implementation(prd(),trace)


@pytest.mark.parametrize("sha", ["short", "z"*40])
def test_trace_requires_full_commit_sha(sha):
    with pytest.raises(ValueError): ImplementationTrace("t","r","task",sha,"https://x.test/pr/1","rel",NOW)


def test_decision_log_supports_all_types(service):
    for index,kind in enumerate(DecisionType):
        service.record_decision("product",DecisionLogEntry(f"d-{index}",kind,"Title","Decision","Reason","actor",("req-1",),NOW,"product","reviewer"))
    assert {item.decision_type for item in service.store.list_decisions("product")} == set(DecisionType)


def test_storage_rejects_traversal(tmp_path):
    store=ProductRequirementsStore(tmp_path)
    with pytest.raises(ValueError): store.load_prd("../escape","prd","1.0")


def test_official_spoken_english_prd_is_locked_complete_and_frozen():
    value=load_prd_artifact("product_requirements/spoken-english-ai/prd-v1.0.json")
    assert value.version == "1.0" and value.status is RequirementStatus.LOCKED
    assert len(value.requirements) == 29
    assert not validate_prd(value)
    titles={item.title for item in value.requirements}
    assert {"Installable PWA","Payments","Indian English only","Animated 2D avatars"} <= titles
    assert {"Parent Portal","Native iOS implementation","IELTS"} <= set(value.explicit_exclusions)
    assert {"3D avatars","Video avatars","Interview Coach"} <= set(value.future_roadmap)


def test_official_artifact_is_valid_json():
    data=json.loads(open("product_requirements/spoken-english-ai/prd-v1.0.json",encoding="utf-8").read())
    assert data["schema_version"] == 1


def test_requirement_groups_and_approval_history_round_trip(service):
    grouped = prd(
        requirement_groups=(RequirementGroup("core", "Core", ("req-1",), "Core scope"),),
        approval_history=(RequirementApproval("approval-1", ("req-1",), "reviewer", "APPROVE", "Ready", NOW),),
    )
    service.create_prd(grouped)
    assert service.store.load_prd("product", "prd", "1.0") == grouped


def test_circular_superseding_is_detected():
    one = requirement(supersedes="req-2")
    two = replace(requirement(), requirement_id="req-2", title="Second", supersedes="req-1")
    assert {issue.code for issue in validate_superseding((one, two))} == {"CIRCULAR_SUPERSEDING"}


def test_change_request_and_restart_recovery(service, tmp_path):
    service.create_prd(prd())
    request = RequirementChangeRequest("change-1", "product", ("req-1",), "owner", "Improve", "Add criterion")
    service.create_change_request(request)
    restarted = ProductRequirementsService(ProductRequirementsStore(tmp_path))
    assert restarted.store.list_change_requests("product") == (request,)


def test_bidirectional_trace_queries(service):
    reviewed = service.submit_for_review(service.create_prd(prd()), "owner", LATER)
    locked = service.lock(service.approve(reviewed, "reviewer", LATER), "reviewer", LATER)
    trace = ImplementationTrace("trace-1", "req-1", "task-1", "a"*40,
                                "https://example.test/pr/1", "release-1", LATER, "impl-1")
    service.trace_implementation(locked, trace)
    assert service.query_traces("product", requirement_id="req-1") == (trace,)
    assert service.query_traces("product", task_id="task-1", commit_sha="a"*40) == (trace,)
    assert service.query_traces("product", pull_request_url="https://example.test/pr/1", release_id="release-1") == (trace,)


def test_unlocked_implementation_request_is_rejected(service):
    with pytest.raises(ValueError, match="LOCKED"):
        service.validate_implementation_request(prd(), ("req-1",))


def test_roadmap_items_are_derived_only_from_governed_requirements(service):
    assert service.roadmap_items(prd()) == ()
    reviewed = service.submit_for_review(service.create_prd(prd()), "owner", LATER)
    approved = service.approve(reviewed, "reviewer", LATER)
    assert service.roadmap_items(approved)[0].requirement_ids == ("req-1",)


def test_decision_history_queries_by_requirement(service):
    first = DecisionLogEntry("decision-1", DecisionType.SECURITY, "Secure", "Use boundary", "Protect data",
                             "architect", ("req-1",), NOW, "product", "reviewer")
    service.record_decision("product", first)
    assert service.decision_history("product", "req-1") == (first,)
    assert service.decision_history("product", "missing") == ()
