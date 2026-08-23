from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat
from urllib.parse import urlencode

import pytest

from runtime.customer_application import CustomerPortalApplication, ProductRequestNotFound
from runtime.customer_estimate import (
    EFFORT_UNIT,
    ESTIMATE_STATUS,
    GENERATION_PROFILE,
    CustomerDeliveryEstimateApplication,
    CustomerDeliveryEstimateConflict,
    CustomerDeliveryEstimateCorrupt,
    CustomerDeliveryEstimateService,
    EffortBand,
    EstimateConfidence,
    FileCustomerDeliveryEstimateStore,
    estimate_id_for,
)
from runtime.customer_prd import CustomerPrdApplication, CustomerPrdApprovalApplication
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApplication,
    CustomerWorkspaceApplication,
)
from runtime.customer_roadmap import (
    CustomerRoadmapApplication,
    CustomerRoadmapApprovalApplication,
)
from tests.test_customer_prd_approval import CSRF, NOW, _call
from tests.test_customer_roadmap_approval import (
    _approve as _approve_roadmap,
    _services as _roadmap_services,
)


def _services(root: Path, *, approve_roadmap: bool = True):
    values = _roadmap_services(root)
    receipt = _approve_roadmap(values[15], values[13]) if approve_roadmap else None
    store = FileCustomerDeliveryEstimateStore(root / "estimates")
    estimates = CustomerDeliveryEstimateService(store, values[15], lambda: NOW)
    return (*values, receipt, store, estimates)


def _application(root: Path, *, approve_roadmap: bool = True):
    values = _services(root, approve_roadmap=approve_roadmap)
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(values[0]),
        CustomerRequirementsApplication(values[1]),
        CustomerRequirementsApprovalApplication(values[2]),
        CustomerPrdApplication(values[3], values[4]),
        CustomerPrdApprovalApplication(values[4]),
        CustomerRoadmapApplication(values[12], values[15]),
        CustomerRoadmapApprovalApplication(values[15]),
        CustomerDeliveryEstimateApplication(values[18]),
    )
    return application, values


def _generate(service: CustomerDeliveryEstimateService, approval, **changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_roadmap_approval_digest": approval.digest,
    }
    values.update(changes)
    return service.generate(**values)


def _form(approval, **changes):
    values = {
        "csrf_token": CSRF,
        "expected_roadmap_approval_digest": approval.digest,
    }
    values.update(changes)
    return urlencode(values, doseq=True)


def test_estimate_identity_is_stable_bounded_and_rejects_unsafe_values():
    assert estimate_id_for("req-1") == estimate_id_for("req-1")
    assert estimate_id_for("req-1") != estimate_id_for("req-2")
    assert len(estimate_id_for("req-1")) < 128
    with pytest.raises(ValueError):
        estimate_id_for("../unsafe")


def test_estimate_is_deterministic_and_maps_every_locked_requirement(tmp_path):
    values = _services(tmp_path)
    prd, roadmap, approval, estimates = values[8], values[13], values[16], values[18]
    estimate = _generate(estimates, approval)

    assert estimate.generation_profile == GENERATION_PROFILE
    assert estimate.status == ESTIMATE_STATUS
    assert estimate.effort_unit == EFFORT_UNIT
    assert estimate.roadmap_digest == roadmap.digest
    assert estimate.roadmap_approval_digest == approval.digest
    assert estimate.requirement_ids == roadmap.requirement_ids
    assert estimate.total_minimum_effort_days == 25
    assert estimate.total_maximum_effort_days == 34
    assert estimate.confidence is EstimateConfidence.MEDIUM
    assert estimate.milestones[0].effort_band is EffortBand.LARGE
    assert set(estimate.requirement_ids) == {
        requirement.requirement_id for requirement in prd.requirements
    }
    assert not hasattr(estimate, "price")
    assert not hasattr(estimate, "calendar_date")
    assert not hasattr(estimate, "agent_id")
    assert not hasattr(estimate, "repository")


def test_estimate_exposes_visible_deterministic_drivers_and_assumptions(tmp_path):
    values = _services(tmp_path)
    estimate = _generate(values[18], values[16])
    milestone = estimate.milestones[0]

    assert milestone.complexity_points == 25
    assert milestone.drivers == (
        "6 locked requirements",
        "Priorities: High, Medium",
        "Scope types: Architecture, Functional, Non Functional, Privacy",
        "Declared data class: Personal Data",
        "Approved platforms: Web",
    )
    assert len(estimate.assumptions) == 5
    assert "not a calendar date" in estimate.assumptions[1]
    assert "Pricing, billing" in estimate.assumptions[3]


def test_estimate_is_write_once_restart_safe_and_exact_retry_idempotent(tmp_path):
    values = _services(tmp_path)
    approval, store, estimates = values[16:]
    first = _generate(estimates, approval)
    second = _generate(estimates, approval)
    restarted = CustomerDeliveryEstimateService(
        FileCustomerDeliveryEstimateStore(tmp_path / "estimates"),
        values[15],
        lambda: NOW + timedelta(days=1),
    )

    assert second == first
    assert restarted.context("customer-1", "req-1")[4] == first
    assert store.load("customer-1", "req-1") == first
    paths = tuple((tmp_path / "estimates").rglob("estimate-v0.1.json"))
    assert len(paths) == 1
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600


def test_estimate_requires_exact_locked_roadmap_authority_and_customer_scope(tmp_path):
    missing = _services(tmp_path / "missing", approve_roadmap=False)
    with pytest.raises(CustomerDeliveryEstimateConflict, match="locked"):
        missing[18].generate(
            customer_id="customer-1",
            request_id="req-1",
            expected_roadmap_approval_digest="0" * 64,
        )

    ready = _services(tmp_path / "ready")
    with pytest.raises(CustomerDeliveryEstimateConflict, match="stale"):
        _generate(ready[18], ready[16], expected_roadmap_approval_digest="0" * 64)
    with pytest.raises(ProductRequestNotFound):
        _generate(ready[18], ready[16], customer_id="customer-2")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("estimate_id", "../unsafe"),
        ("prd_version", "1.0"),
        ("roadmap_digest", "bad"),
        ("generation_profile", "unknown"),
        ("effort_unit", "calendar-day"),
        ("status", "APPROVED"),
        ("generated_at", datetime(2026, 8, 20)),
        (
            "generated_at",
            datetime(2026, 8, 20, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        ),
    ],
)
def test_estimate_model_rejects_invalid_or_elevated_authority(tmp_path, field, value):
    values = _services(tmp_path)
    estimate = _generate(values[18], values[16])
    with pytest.raises(ValueError):
        replace(estimate, **{field: value})


def test_estimate_model_rejects_invalid_ranges_mappings_and_item_status(tmp_path):
    values = _services(tmp_path)
    estimate = _generate(values[18], values[16])
    milestone = estimate.milestones[0]
    with pytest.raises(ValueError, match="range"):
        replace(milestone, minimum_effort_days=100)
    with pytest.raises(ValueError, match="DRAFT"):
        replace(milestone, status="LOCKED")
    with pytest.raises(ValueError, match="minimum total"):
        replace(estimate, total_minimum_effort_days=999)
    with pytest.raises(ValueError, match="exactly once"):
        replace(
            estimate,
            milestones=(milestone, replace(milestone, roadmap_item_id="other", sequence=2)),
            total_minimum_effort_days=estimate.total_minimum_effort_days * 2,
            total_maximum_effort_days=estimate.total_maximum_effort_days * 2,
        )


def test_estimate_store_detects_tamper_unknown_entry_and_symlink(tmp_path):
    values = _services(tmp_path)
    _generate(values[18], values[16])
    store = values[17]
    path = next((tmp_path / "estimates").rglob("estimate-v0.1.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["roadmap_digest"] = "0" * 64
    path.write_text(json.dumps(envelope))
    with pytest.raises(CustomerDeliveryEstimateCorrupt):
        store.load("customer-1", "req-1")

    path.write_text("{}")
    (path.parent / "unknown.txt").write_text("unsafe")
    with pytest.raises(CustomerDeliveryEstimateCorrupt, match="closed"):
        store.find("customer-1", "req-1")
    (path.parent / "unknown.txt").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CustomerDeliveryEstimateCorrupt, match="unsafe"):
        store.find("customer-1", "req-1")


def test_estimate_checkpoint_is_customer_scoped_bounded_and_hardened(tmp_path):
    application, values = _application(tmp_path)
    prd, approval = values[8], values[16]
    status, headers, content = _call(
        application,
        path="/customer/requests/req-1/estimate",
    )

    assert status == "200 OK"
    assert b"Create an effort estimate for Community workshop planner" in content
    assert str(len(prd.requirements)).encode() in content
    assert approval.digest.encode() in content
    assert b'name="customer_id"' not in content
    assert b"not calendar duration" in content
    assert b"official pilot-product selection" in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]


def test_customer_generates_and_reopens_exact_estimate_draft(tmp_path):
    application, values = _application(tmp_path)
    approval, estimates = values[16], values[18]
    status, headers, _ = _call(
        application,
        method="POST",
        path="/customer/requests/req-1/estimate",
        body=_form(approval),
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/estimate/review")

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Draft generated" in content
    assert "25–34 engineering days".encode() in content
    assert b"REQ-JOURNEY-001" in content
    assert b"Estimate assumptions" in content
    assert b"no commitment or execution authority" in content
    estimate = estimates.context("customer-1", "req-1")[4]
    assert estimate is not None and estimate.digest.encode() in content

    status, redirected, _ = _call(
        application,
        path="/customer/requests/req-1/estimate",
    )
    assert status == "303 See Other"
    assert redirected["Location"].endswith("/estimate/review")


def test_estimate_web_rejects_csrf_unknown_fields_and_stale_authority(tmp_path):
    application, values = _application(tmp_path)
    approval = values[16]
    path = "/customer/requests/req-1/estimate"
    assert _call(
        application,
        method="POST",
        path=path,
        body=_form(approval, csrf_token="wrong"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        path=path,
        body=_form(approval) + "&unexpected=value",
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        path=path,
        body=_form(approval, expected_roadmap_approval_digest="0" * 64),
    )[0] == "409 Conflict"


def test_estimate_routes_require_identity_hide_cross_customer_and_redirect_unlocked(tmp_path):
    application = _application(tmp_path)[0]
    path = "/customer/requests/req-1/estimate"
    assert _call(application, path=path, customer=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, customer="customer-2")[0] == "404 Not Found"

    unlocked = _application(tmp_path / "unlocked", approve_roadmap=False)[0]
    status, headers, _ = _call(unlocked, path=path)
    assert status == "303 See Other"
    assert headers["Location"].endswith("/roadmap/approved")


def test_locked_roadmap_receipt_offers_estimate_without_changing_authority(tmp_path):
    application, _ = _application(tmp_path)
    status, _, content = _call(
        application,
        path="/customer/requests/req-1/roadmap/approved",
    )
    assert status == "200 OK"
    assert b"Create delivery estimate draft" in content
    assert b"implementation has not started" in content
