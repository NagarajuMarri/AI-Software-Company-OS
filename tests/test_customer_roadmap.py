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
    CustomerPrdApprovalService,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApplication,
    CustomerWorkspaceApplication,
)
from runtime.customer_roadmap import (
    GENERATION_PROFILE,
    LEGACY_GENERATION_PROFILE,
    CustomerRoadmapApplication,
    CustomerRoadmapConflict,
    CustomerRoadmapCorrupt,
    CustomerRoadmapService,
    FileCustomerRoadmapStore,
    roadmap_id_for,
)
from runtime.customer_roadmap.service import _legacy_milestones, _milestones
from runtime.customer_roadmap.web import _roadmap_review
from runtime.product_requirements import RequirementStatus
from tests.test_customer_prd_approval import CSRF, NOW, _approve, _call, _services


def _ready(root: Path, *, approve_prd: bool = True):
    values = _services(root)
    approval = _approve(values[4], values[8]) if approve_prd else None
    store = FileCustomerRoadmapStore(root / "roadmaps")
    roadmaps = CustomerRoadmapService(store, values[4], lambda: NOW)
    return (*values, approval, store, roadmaps)


def _application(root: Path, *, approve_prd: bool = True):
    values = _ready(root, approve_prd=approve_prd)
    roadmaps = values[12]
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(values[0]),
        CustomerRequirementsApplication(values[1]),
        CustomerRequirementsApprovalApplication(values[2]),
        CustomerPrdApplication(values[3], values[4]),
        CustomerPrdApprovalApplication(values[4]),
        CustomerRoadmapApplication(roadmaps),
    )
    return application, values


def _generate(service: CustomerRoadmapService, approval, **changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_prd_approval_digest": approval.digest,
    }
    values.update(changes)
    return service.generate(**values)


def _form(approval, **changes):
    values = {
        "csrf_token": CSRF,
        "expected_prd_approval_digest": approval.digest,
    }
    values.update(changes)
    return urlencode(values, doseq=True)


def test_roadmap_identity_is_stable_bounded_and_rejects_unsafe_values():
    assert roadmap_id_for("req-1") == roadmap_id_for("req-1")
    assert roadmap_id_for("req-1") != roadmap_id_for("req-2")
    assert len(roadmap_id_for("req-1")) < 128
    with pytest.raises(ValueError):
        roadmap_id_for("../unsafe")


def test_roadmap_decomposes_locked_requirements_and_maps_every_requirement(tmp_path):
    values = _ready(tmp_path)
    prd, approval, roadmaps = values[8], values[10], values[12]
    roadmap = _generate(roadmaps, approval)
    locked = values[4].governed_document("customer-1", "req-1")

    assert roadmap.generation_profile == GENERATION_PROFILE
    assert roadmap.status == "DRAFT"
    assert roadmap.prd_digest == prd.digest
    assert roadmap.prd_approval_id == approval.approval_id
    assert roadmap.prd_approval_digest == approval.digest
    assert tuple(item.milestone for item in roadmap.milestones) == (
        "Platform, data, and delivery foundation",
        "Capability increment 1 — Publish workshops",
        "End-to-end journey and release acceptance",
    )
    assert tuple(len(item.requirement_ids) for item in roadmap.milestones) == (3, 2, 1)
    assert set(roadmap.requirement_ids) == {
        requirement.requirement_id for requirement in locked.requirements
    }
    assert all(requirement.status is RequirementStatus.LOCKED for requirement in locked.requirements)
    assert not hasattr(roadmap, "estimate")
    assert not hasattr(roadmap, "scheduled_at")
    assert not hasattr(roadmap, "agent_id")


def test_complex_single_milestone_prd_becomes_bounded_dependency_ordered_increments(tmp_path):
    values = _ready(tmp_path)
    locked = values[4].governed_document("customer-1", "req-1")
    journey = next(item for item in locked.requirements if item.requirement_id.startswith("REQ-JOURNEY-"))
    feature = next(item for item in locked.requirements if item.requirement_id.startswith("REQ-FEATURE-"))
    constraint = next(
        item for item in locked.requirements if item.requirement_id.startswith("REQ-CONSTRAINT-")
    )
    platform = next(item for item in locked.requirements if item.requirement_id.startswith("REQ-PLATFORM-"))
    data = next(item for item in locked.requirements if item.requirement_id.startswith("REQ-DATA-"))
    features = tuple(
        replace(feature, requirement_id=f"REQ-FEATURE-{index:03d}", title=f"Feature {index}")
        for index in range(1, 21)
    )
    constraints = tuple(
        replace(
            constraint,
            requirement_id=f"REQ-CONSTRAINT-{index:03d}",
            title=f"Constraint {index}",
        )
        for index in range(1, 21)
    )
    complex_prd = replace(
        locked,
        requirements=(journey, *features, *constraints, platform, data),
    )

    milestones = _milestones(complex_prd)

    assert len(milestones) == 8
    assert tuple(len(item.requirement_ids) for item in milestones) == (8, 8, 6, 5, 5, 5, 5, 1)
    assert milestones[0].milestone == "Platform, data, and delivery foundation"
    assert milestones[-1].milestone == "End-to-end journey and release acceptance"
    assert tuple(item.sequence for item in milestones) == tuple(range(1, 9))
    assert len({item for milestone in milestones for item in milestone.requirement_ids}) == 43


def test_unapproved_legacy_roadmap_is_readable_and_atomically_regenerated(tmp_path):
    values = _ready(tmp_path / "authority")
    approval, roadmaps = values[10], values[12]
    current = _generate(roadmaps, approval)
    locked = values[4].governed_document("customer-1", "req-1")
    legacy = replace(
        current,
        generation_profile=LEGACY_GENERATION_PROFILE,
        milestones=_legacy_milestones(locked),
    )
    legacy_store = FileCustomerRoadmapStore(tmp_path / "legacy-roadmaps")
    legacy_store.save(legacy)
    service = CustomerRoadmapService(
        legacy_store,
        values[4],
        lambda: NOW + timedelta(minutes=1),
        roadmap_approval_locked=lambda _customer, _request: False,
    )

    assert service.context("customer-1", "req-1")[3] == legacy
    regenerated = _generate(service, approval)

    assert regenerated.generation_profile == GENERATION_PROFILE
    assert regenerated.digest != legacy.digest
    assert len(regenerated.milestones) == 3
    assert legacy_store.load("customer-1", "req-1") == regenerated
    path = next((tmp_path / "legacy-roadmaps").rglob("roadmap-v0.1.json"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_legacy_review_offers_regeneration_but_no_approval_action(tmp_path):
    values = _ready(tmp_path)
    current = _generate(values[12], values[10])
    locked = values[4].governed_document("customer-1", "req-1")
    legacy = replace(
        current,
        generation_profile=LEGACY_GENERATION_PROFILE,
        milestones=_legacy_milestones(locked),
    )

    content = _roadmap_review(values[8], legacy, values[10].digest, CSRF)

    assert "Regeneration required" in content
    assert "Regenerate decomposed roadmap" in content
    assert "Review and approve roadmap" not in content


def test_legacy_roadmap_regeneration_fails_closed_when_approval_cannot_be_excluded(tmp_path):
    values = _ready(tmp_path / "authority")
    approval, roadmaps = values[10], values[12]
    current = _generate(roadmaps, approval)
    locked = values[4].governed_document("customer-1", "req-1")
    legacy = replace(
        current,
        generation_profile=LEGACY_GENERATION_PROFILE,
        milestones=_legacy_milestones(locked),
    )
    store = FileCustomerRoadmapStore(tmp_path / "legacy-roadmaps")
    store.save(legacy)

    for callback in (None, lambda _customer, _request: True):
        service = CustomerRoadmapService(
            store,
            values[4],
            roadmap_approval_locked=callback,
        )
        with pytest.raises(CustomerRoadmapConflict, match="approved or unverifiable"):
            _generate(service, approval)


def test_roadmap_is_write_once_restart_safe_and_exact_retry_idempotent(tmp_path):
    values = _ready(tmp_path)
    approval, store, roadmaps = values[10], values[11], values[12]
    first = _generate(roadmaps, approval)
    second = _generate(roadmaps, approval)
    restarted = CustomerRoadmapService(
        FileCustomerRoadmapStore(tmp_path / "roadmaps"),
        values[4],
        lambda: NOW + timedelta(days=1),
    )

    assert second == first
    assert restarted.context("customer-1", "req-1")[3] == first
    assert store.load("customer-1", "req-1") == first
    paths = tuple((tmp_path / "roadmaps").rglob("roadmap-v0.1.json"))
    assert len(paths) == 1
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600


def test_roadmap_requires_exact_locked_prd_authority_and_customer_scope(tmp_path):
    values = _ready(tmp_path / "unapproved", approve_prd=False)
    with pytest.raises(CustomerRoadmapConflict, match="locked"):
        values[12].generate(
            customer_id="customer-1",
            request_id="req-1",
            expected_prd_approval_digest="0" * 64,
        )

    ready = _ready(tmp_path / "ready")
    with pytest.raises(CustomerRoadmapConflict, match="stale"):
        _generate(ready[12], ready[10], expected_prd_approval_digest="0" * 64)
    with pytest.raises(ProductRequestNotFound):
        _generate(ready[12], ready[10], customer_id="customer-2")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("roadmap_id", "../unsafe"),
        ("prd_version", "1.0"),
        ("prd_digest", "bad"),
        ("generation_profile", "unknown"),
        ("status", "APPROVED"),
        ("generated_at", datetime(2026, 8, 20)),
        (
            "generated_at",
            datetime(2026, 8, 20, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        ),
    ],
)
def test_roadmap_model_rejects_invalid_or_elevated_authority(tmp_path, field, value):
    values = _ready(tmp_path)
    roadmap = _generate(values[12], values[10])
    with pytest.raises(ValueError):
        replace(roadmap, **{field: value})


def test_roadmap_model_rejects_duplicate_or_incomplete_mappings(tmp_path):
    values = _ready(tmp_path)
    roadmap = _generate(values[12], values[10])
    milestone = roadmap.milestones[0]
    with pytest.raises(ValueError, match="exactly once"):
        replace(roadmap, milestones=(milestone, replace(milestone, roadmap_item_id="other", sequence=2)))
    with pytest.raises(ValueError, match="sequence"):
        replace(milestone, sequence=0)
    with pytest.raises(ValueError, match="DRAFT"):
        replace(milestone, status="PLANNED")


def test_roadmap_store_detects_tamper_unknown_entry_and_symlink(tmp_path):
    values = _ready(tmp_path)
    _generate(values[12], values[10])
    store = values[11]
    path = next((tmp_path / "roadmaps").rglob("roadmap-v0.1.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["prd_digest"] = "0" * 64
    path.write_text(json.dumps(envelope))
    with pytest.raises(CustomerRoadmapCorrupt):
        store.load("customer-1", "req-1")

    path.write_text("{}")
    (path.parent / "unknown.txt").write_text("unsafe")
    with pytest.raises(CustomerRoadmapCorrupt, match="closed"):
        store.find("customer-1", "req-1")
    (path.parent / "unknown.txt").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CustomerRoadmapCorrupt, match="unsafe"):
        store.find("customer-1", "req-1")


def test_roadmap_checkpoint_is_customer_scoped_bounded_and_hardened(tmp_path):
    application, values = _application(tmp_path)
    prd, approval = values[8], values[10]
    status, headers, content = _call(
        application,
        path="/customer/requests/req-1/roadmap",
    )

    assert status == "200 OK"
    assert b"Create a roadmap draft for Community workshop planner" in content
    assert str(len(prd.requirements)).encode() in content
    assert approval.digest.encode() in content
    assert b'name="customer_id"' not in content
    assert b"no estimate, date, schedule commitment" in content
    assert b"official pilot-product selection" in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]


def test_customer_generates_and_reopens_exact_roadmap_draft(tmp_path):
    application, values = _application(tmp_path)
    approval, roadmaps = values[10], values[12]
    status, headers, _ = _call(
        application,
        method="POST",
        path="/customer/requests/req-1/roadmap",
        body=_form(approval),
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/roadmap/review")

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Draft generated" in content
    assert b"Platform, data, and delivery foundation" in content
    assert b"Capability increment 1" in content
    assert b"End-to-end journey and release acceptance" in content
    assert b"REQ-JOURNEY-001" in content
    assert b"no execution authority" in content
    roadmap = roadmaps.context("customer-1", "req-1")[3]
    assert roadmap is not None and roadmap.digest.encode() in content

    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/roadmap",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/roadmap/review")


def test_roadmap_web_rejects_csrf_unknown_fields_and_stale_authority(tmp_path):
    application, values = _application(tmp_path)
    approval = values[10]
    assert _call(
        application,
        method="POST",
        path="/customer/requests/req-1/roadmap",
        body=_form(approval, csrf_token="wrong"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        path="/customer/requests/req-1/roadmap",
        body=_form(approval) + "&unexpected=value",
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        path="/customer/requests/req-1/roadmap",
        body=_form(approval, expected_prd_approval_digest="0" * 64),
    )[0] == "409 Conflict"


def test_roadmap_routes_require_identity_hide_cross_customer_and_redirect_unapproved(tmp_path):
    application, _ = _application(tmp_path)
    assert _call(
        application,
        path="/customer/requests/req-1/roadmap",
        customer=None,
    )[0] == "401 Unauthorized"
    assert _call(
        application,
        path="/customer/requests/req-1/roadmap",
        csrf=None,
    )[0] == "401 Unauthorized"
    assert _call(
        application,
        path="/customer/requests/req-1/roadmap",
        customer="customer-2",
    )[0] == "404 Not Found"

    unapproved, _ = _application(tmp_path / "unapproved", approve_prd=False)
    status, headers, _ = _call(
        unapproved,
        path="/customer/requests/req-1/roadmap",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/approve")
