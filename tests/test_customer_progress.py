from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from runtime.customer_application import CustomerPortalApplication, ProductRequestNotFound
from runtime.customer_estimate import CustomerDeliveryEstimateApplication
from runtime.customer_prd import CustomerPrdApplication, CustomerPrdApprovalApplication
from runtime.customer_progress import (
    GENERATION_PROFILE,
    PROJECT_STATUS,
    CustomerProjectProgressApplication,
    CustomerProjectProgressConflict,
    CustomerProjectProgressService,
    progress_id_for,
    task_id_for,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApplication,
    CustomerWorkspaceApplication,
)
from runtime.customer_roadmap import (
    CustomerRoadmapApplication,
    CustomerRoadmapApprovalApplication,
)
from tests.test_customer_estimate import _generate, _services
from tests.test_customer_prd_approval import _call


def _ready(root: Path):
    values = _services(root)
    estimate = _generate(values[18], values[16])
    progress = CustomerProjectProgressService(values[18])
    return values, estimate, progress


def _application(root: Path, *, generate_estimate: bool = True):
    values = _services(root)
    if generate_estimate:
        _generate(values[18], values[16])
    progress = CustomerProjectProgressService(values[18])
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(values[0]),
        CustomerRequirementsApplication(values[1]),
        CustomerRequirementsApprovalApplication(values[2]),
        CustomerPrdApplication(values[3], values[4]),
        CustomerPrdApprovalApplication(values[4]),
        CustomerRoadmapApplication(values[12], values[15]),
        CustomerRoadmapApprovalApplication(values[15]),
        CustomerDeliveryEstimateApplication(values[18]),
        CustomerProjectProgressApplication(progress),
    )
    return application, values, progress


def test_progress_and_task_identities_are_stable_bounded_and_safe():
    assert progress_id_for("req-1") == progress_id_for("req-1")
    assert progress_id_for("req-1") != progress_id_for("req-2")
    assert task_id_for("req-1", "REQ-FEATURE-001") == task_id_for(
        "req-1", "REQ-FEATURE-001"
    )
    assert task_id_for("req-1", "REQ-FEATURE-001") != task_id_for(
        "req-1", "REQ-FEATURE-002"
    )
    with pytest.raises(ValueError):
        progress_id_for("../unsafe")
    with pytest.raises(ValueError):
        task_id_for("req-1", "unsafe")


def test_progress_projects_exact_scope_through_existing_project_manager_domain(tmp_path):
    values, estimate, progress = _ready(tmp_path)
    prd, roadmap = values[8], values[13]
    snapshot = progress.view("customer-1", "req-1")

    assert snapshot.generation_profile == GENERATION_PROFILE
    assert snapshot.status == PROJECT_STATUS
    assert snapshot.projected_at == estimate.generated_at
    assert snapshot.estimate_digest == estimate.digest
    assert snapshot.roadmap_digest == roadmap.digest
    assert snapshot.total_tasks == len(prd.requirements) == 5
    assert snapshot.completed_tasks == 0
    assert snapshot.in_progress_tasks == 0
    assert snapshot.blocked_tasks == 0
    assert snapshot.progress_percentage == 0
    assert snapshot.assigned_agent_ids == ()
    assert tuple(value.requirement_id for value in snapshot.tasks) == roadmap.requirement_ids
    assert tuple(
        requirement_id
        for milestone in snapshot.milestones
        for requirement_id in milestone.requirement_ids
    ) == roadmap.requirement_ids
    assert all(value.status == "NOT_STARTED" for value in snapshot.tasks)
    assert all(value.assigned_agent_id is None for value in snapshot.tasks)


def test_progress_exposes_agents_blockers_decisions_and_stable_digest(tmp_path):
    _, estimate, progress = _ready(tmp_path)
    first = progress.view("customer-1", "req-1")
    second = progress.view("customer-1", "req-1")

    assert second == first
    assert second.digest == first.digest
    assert len(first.assigned_agent_ids) == 0
    assert {value.blocker_id for value in first.blockers} == {
        "execution-authority-required",
        "workforce-not-activated",
        "product-workspace-unavailable",
    }
    assert {value.outcome for value in first.decisions} == {
        "APPROVED_AND_LOCKED",
        "DRAFT_RECORDED",
    }
    assert first.decisions[1].authority_digest == estimate.digest
    assert not (tmp_path / "progress").exists()


def test_progress_requires_exact_estimate_and_customer_scope(tmp_path):
    values = _services(tmp_path)
    progress = CustomerProjectProgressService(values[18])
    with pytest.raises(CustomerProjectProgressConflict, match="estimate"):
        progress.view("customer-1", "req-1")
    with pytest.raises(ProductRequestNotFound):
        progress.view("customer-2", "req-1")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "ACTIVE"),
        ("assigned_agent_ids", ("agent-1",)),
        ("progress_percentage", 1),
        ("completed_tasks", 1),
        ("generation_profile", "unknown"),
        ("estimate_digest", "bad"),
    ],
)
def test_progress_model_rejects_elevated_or_invalid_authority(tmp_path, field, value):
    _, _, progress = _ready(tmp_path)
    snapshot = progress.view("customer-1", "req-1")
    with pytest.raises(ValueError):
        replace(snapshot, **{field: value})


def test_progress_model_rejects_duplicate_or_mismatched_task_mapping(tmp_path):
    _, _, progress = _ready(tmp_path)
    snapshot = progress.view("customer-1", "req-1")
    with pytest.raises(ValueError, match="tasks"):
        replace(snapshot, tasks=(snapshot.tasks[0], snapshot.tasks[0]))
    with pytest.raises(ValueError, match="tasks are invalid"):
        replace(
            snapshot,
            milestones=(replace(snapshot.milestones[0], task_ids=(snapshot.tasks[1].task_id,)),),
        )


def test_progress_dashboard_is_customer_scoped_read_only_and_hardened(tmp_path):
    application, _, progress = _application(tmp_path)
    path = "/customer/requests/req-1/progress"
    snapshot = progress.view("customer-1", "req-1")
    status, headers, content = _call(application, path=path)

    assert status == "200 OK"
    assert b"Project progress dashboard" in content
    assert b"0% complete" in content
    assert b"0/5 complete" in content
    assert b"No operational agents assigned" in content
    assert b"Open blockers" in content
    assert b"Governed decisions" in content
    assert b"Visibility only" in content
    assert b"REQ-FEATURE-001" in content
    assert snapshot.digest.encode() in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]
    assert _call(application, path=path, customer=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, customer="customer-2")[0] == "404 Not Found"
    post_status, post_headers, _ = _call(application, path=path, method="POST")
    assert post_status == "405 Method Not Allowed"
    assert post_headers["Allow"] == "GET"


def test_progress_redirects_to_estimate_until_source_exists(tmp_path):
    application = _application(tmp_path, generate_estimate=False)[0]
    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/progress",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/estimate")


def test_estimate_review_links_to_project_progress_without_changing_authority(tmp_path):
    application = _application(tmp_path)[0]
    status, _, content = _call(
        application,
        path="/customer/requests/req-1/estimate/review",
    )
    assert status == "200 OK"
    assert b"View project progress" in content
    assert b"no commitment or execution authority" in content
