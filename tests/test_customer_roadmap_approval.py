from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat
from urllib.parse import urlencode

import pytest

from runtime.customer_application import CustomerPortalApplication, ProductRequestNotFound
from runtime.customer_prd import (
    CustomerPrdApplication,
    CustomerPrdApprovalApplication,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApplication,
    CustomerWorkspaceApplication,
)
from runtime.customer_roadmap import (
    LEGACY_GENERATION_PROFILE,
    ROADMAP_CONFIRMATION_VERSION,
    CustomerRoadmapApplication,
    CustomerRoadmapApprovalApplication,
    CustomerRoadmapApprovalConflict,
    CustomerRoadmapApprovalCorrupt,
    CustomerRoadmapApprovalService,
    CustomerRoadmapService,
    FileCustomerRoadmapApprovalStore,
    FileCustomerRoadmapStore,
    governed_locked_roadmap,
    roadmap_approval_id_for,
)
from runtime.customer_roadmap.service import _legacy_milestones
from tests.test_customer_prd_approval import CSRF, NOW, _call
from tests.test_customer_roadmap import _generate, _ready


def _services(root: Path, *, generate: bool = True):
    values = _ready(root)
    roadmap = _generate(values[12], values[10]) if generate else None
    store = FileCustomerRoadmapApprovalStore(root / "roadmap-approvals")
    approvals = CustomerRoadmapApprovalService(store, values[12], lambda: NOW)
    return (*values, roadmap, store, approvals)


def _approve(service: CustomerRoadmapApprovalService, roadmap, **changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_roadmap_digest": roadmap.digest,
        "confirmed": True,
    }
    values.update(changes)
    return service.approve(**values)


def _application(root: Path, *, generate: bool = True):
    values = _services(root, generate=generate)
    approvals = values[15]
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(values[0]),
        CustomerRequirementsApplication(values[1]),
        CustomerRequirementsApprovalApplication(values[2]),
        CustomerPrdApplication(values[3], values[4]),
        CustomerPrdApprovalApplication(values[4]),
        CustomerRoadmapApplication(values[12], approvals),
        CustomerRoadmapApprovalApplication(approvals),
    )
    return application, values


def _form(roadmap, **changes):
    values = {
        "csrf_token": CSRF,
        "expected_roadmap_digest": roadmap.digest,
        "confirmation": "LOCK",
    }
    values.update(changes)
    return urlencode(values, doseq=True)


def test_roadmap_approval_identity_is_stable_bounded_and_rejects_unsafe_values():
    assert roadmap_approval_id_for("req-1") == roadmap_approval_id_for("req-1")
    assert roadmap_approval_id_for("req-1") != roadmap_approval_id_for("req-2")
    assert len(roadmap_approval_id_for("req-1")) < 128
    with pytest.raises(ValueError):
        roadmap_approval_id_for("../unsafe")


def test_approval_binds_full_authority_chain_and_is_write_once(tmp_path):
    values = _services(tmp_path)
    roadmap, store, approvals = values[13:]
    first = _approve(approvals, roadmap)
    second = _approve(approvals, roadmap)

    assert second == first
    assert first.confirmation_version == ROADMAP_CONFIRMATION_VERSION
    assert first.roadmap_digest == roadmap.digest
    assert first.source_request_digest == roadmap.source_request_digest
    assert first.requirements_digest == roadmap.requirements_digest
    assert first.requirements_approval_digest == roadmap.requirements_approval_digest
    assert first.prd_digest == roadmap.prd_digest
    assert first.prd_approval_digest == roadmap.prd_approval_digest
    assert store.load("customer-1", "req-1") == first
    paths = tuple((tmp_path / "roadmap-approvals").rglob("roadmap-approval-v0.1.json"))
    assert len(paths) == 1
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600


def test_approval_projects_every_exact_item_into_terminal_locked_state(tmp_path):
    values = _services(tmp_path)
    roadmap, approvals = values[13], values[15]
    receipt = _approve(approvals, roadmap)
    locked = approvals.governed_roadmap("customer-1", "req-1")

    assert locked.status == "LOCKED"
    assert locked.approved_by == "customer-1"
    assert locked.locked_at == receipt.approved_at
    assert locked.source_roadmap_digest == roadmap.digest
    assert locked.approval_digest == receipt.digest
    assert locked.requirement_ids == roadmap.requirement_ids
    assert tuple(item.roadmap_item_id for item in locked.milestones) == tuple(
        item.roadmap_item_id for item in roadmap.milestones
    )
    assert all(item.status == "LOCKED" for item in locked.milestones)
    assert not hasattr(locked, "estimate")
    assert not hasattr(locked, "repository")
    assert not hasattr(locked, "agent_id")


def test_governed_projection_rejects_receipt_for_a_different_roadmap(tmp_path):
    values = _services(tmp_path)
    roadmap, approvals = values[13], values[15]
    receipt = _approve(approvals, roadmap)
    with pytest.raises(CustomerRoadmapApprovalConflict, match="does not bind"):
        governed_locked_roadmap(replace(roadmap, title="Different planning scope"), receipt)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approval_id", "../unsafe"),
        ("prd_version", "1.0"),
        ("roadmap_digest", "bad"),
        ("confirmation_version", "unknown"),
        ("approved_at", datetime(2026, 8, 20)),
        (
            "approved_at",
            datetime(2026, 8, 20, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        ),
    ],
)
def test_approval_model_rejects_invalid_authority(tmp_path, field, value):
    values = _services(tmp_path)
    receipt = _approve(values[15], values[13])
    with pytest.raises(ValueError):
        replace(receipt, **{field: value})


def test_locked_projection_rejects_elevated_or_inconsistent_state(tmp_path):
    values = _services(tmp_path)
    receipt = _approve(values[15], values[13])
    locked = governed_locked_roadmap(values[13], receipt)
    with pytest.raises(ValueError, match="LOCKED"):
        replace(locked, status="APPROVED")
    with pytest.raises(ValueError, match="LOCKED"):
        replace(locked.milestones[0], status="PLANNED")
    with pytest.raises(ValueError, match="sequence"):
        replace(locked.milestones[0], sequence=0)


def test_approval_requires_roadmap_confirmation_exact_digest_and_customer_scope(tmp_path):
    missing = _services(tmp_path / "missing", generate=False)
    with pytest.raises(CustomerRoadmapApprovalConflict, match="required"):
        missing[15].approve(
            customer_id="customer-1",
            request_id="req-1",
            expected_roadmap_digest="0" * 64,
            confirmed=True,
        )

    ready = _services(tmp_path / "ready")
    with pytest.raises(ValueError, match="confirmation"):
        _approve(ready[15], ready[13], confirmed=False)
    with pytest.raises(CustomerRoadmapApprovalConflict, match="stale"):
        _approve(ready[15], ready[13], expected_roadmap_digest="0" * 64)
    with pytest.raises(ProductRequestNotFound):
        _approve(ready[15], ready[13], customer_id="customer-2")


def test_approval_rejects_legacy_single_milestone_draft(tmp_path):
    values = _ready(tmp_path / "authority")
    current = _generate(values[12], values[10])
    locked = values[4].governed_document("customer-1", "req-1")
    legacy = replace(
        current,
        generation_profile=LEGACY_GENERATION_PROFILE,
        milestones=_legacy_milestones(locked),
    )
    roadmap_store = FileCustomerRoadmapStore(tmp_path / "legacy-roadmaps")
    roadmap_store.save(legacy)
    roadmaps = CustomerRoadmapService(roadmap_store, values[4])
    approvals = CustomerRoadmapApprovalService(
        FileCustomerRoadmapApprovalStore(tmp_path / "legacy-approvals"),
        roadmaps,
    )

    with pytest.raises(CustomerRoadmapApprovalConflict, match="legacy"):
        _approve(approvals, legacy)


def test_store_restart_corruption_unknown_entry_and_symlink_detection(tmp_path):
    values = _services(tmp_path)
    roadmaps, roadmap, store, approvals = values[12:]
    receipt = _approve(approvals, roadmap)
    restarted = CustomerRoadmapApprovalService(
        FileCustomerRoadmapApprovalStore(tmp_path / "roadmap-approvals"),
        roadmaps,
        lambda: NOW + timedelta(days=1),
    )
    assert restarted.context("customer-1", "req-1")[4] == receipt

    path = next((tmp_path / "roadmap-approvals").rglob("roadmap-approval-v0.1.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["roadmap_digest"] = "0" * 64
    path.write_text(json.dumps(envelope))
    with pytest.raises(CustomerRoadmapApprovalCorrupt):
        store.load("customer-1", "req-1")

    path.write_text("{}")
    (path.parent / "unknown.txt").write_text("unsafe")
    with pytest.raises(CustomerRoadmapApprovalCorrupt, match="closed"):
        store.find("customer-1", "req-1")
    (path.parent / "unknown.txt").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CustomerRoadmapApprovalCorrupt, match="unsafe"):
        store.find("customer-1", "req-1")


def test_approval_checkpoint_is_complete_customer_scoped_and_hardened(tmp_path):
    application, values = _application(tmp_path)
    roadmap = values[13]
    status, headers, content = _call(
        application,
        path="/customer/requests/req-1/roadmap/approve",
    )

    assert status == "200 OK"
    assert b"Approve and lock Community workshop planner" in content
    assert b"REQ-JOURNEY-001" in content
    assert b"Platform, data, and delivery foundation" in content
    assert roadmap.digest.encode() in content
    assert b'name="customer_id"' not in content
    assert b"does not estimate or schedule work" in content
    assert b"official pilot product" in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]


def test_customer_approves_reopens_and_cannot_return_to_draft(tmp_path):
    application, values = _application(tmp_path)
    roadmap, approvals = values[13], values[15]
    status, headers, _ = _call(
        application,
        method="POST",
        path="/customer/requests/req-1/roadmap/approve",
        body=_form(roadmap),
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/roadmap/approved")

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Approved and locked" in content
    assert b"Governed status" in content and b"LOCKED" in content
    assert b"implementation has not started" in content
    receipt = approvals.context("customer-1", "req-1")[4]
    assert receipt is not None and receipt.digest.encode() in content
    assert all(item.status == "LOCKED" for item in approvals.governed_roadmap(
        "customer-1", "req-1"
    ).milestones)

    for path in (
        "/customer/requests/req-1/roadmap",
        "/customer/requests/req-1/roadmap/review",
        "/customer/requests/req-1/roadmap/approve",
    ):
        status, redirected, _ = _call(application, path=path)
        assert status == "303 See Other"
        assert redirected["Location"].endswith("/roadmap/approved")


def test_approval_web_rejects_csrf_confirmation_unknown_fields_and_stale_digest(tmp_path):
    application, values = _application(tmp_path)
    roadmap = values[13]
    path = "/customer/requests/req-1/roadmap/approve"
    assert _call(
        application,
        method="POST",
        path=path,
        body=_form(roadmap, csrf_token="wrong"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        path=path,
        body=_form(roadmap, confirmation="REVIEW"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        path=path,
        body=_form(roadmap) + "&unexpected=value",
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        path=path,
        body=_form(roadmap, expected_roadmap_digest="0" * 64),
    )[0] == "409 Conflict"


def test_approval_routes_require_identity_hide_cross_customer_and_redirect_missing(tmp_path):
    application = _application(tmp_path)[0]
    path = "/customer/requests/req-1/roadmap/approve"
    assert _call(application, path=path, customer=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, path=path, customer="customer-2")[0] == "404 Not Found"

    missing = _application(tmp_path / "missing", generate=False)[0]
    status, headers, _ = _call(missing, path=path)
    assert status == "303 See Other"
    assert headers["Location"].endswith("/roadmap")
    status, headers, _ = _call(
        missing,
        path="/customer/requests/req-1/roadmap/approved",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/roadmap/review")
