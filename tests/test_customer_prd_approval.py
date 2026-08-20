from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import stat
from urllib.parse import urlencode

import pytest

from runtime.customer_application import (
    CustomerPortalApplication,
    CustomerProductRequestService,
    FileCustomerProductRequestStore,
    ProductRequestNotFound,
)
from runtime.customer_prd import (
    PRD_CONFIRMATION_VERSION,
    CustomerPrdApplication,
    CustomerPrdApprovalApplication,
    CustomerPrdApprovalConflict,
    CustomerPrdApprovalCorrupt,
    CustomerPrdApprovalService,
    CustomerPrdService,
    FileCustomerPrdApprovalStore,
    FileCustomerPrdStore,
    prd_approval_id_for,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApprovalService,
    CustomerRequirementsApplication,
    CustomerRequirementsService,
    CustomerWorkspaceApplication,
    DataSensitivity,
    DeliveryPriority,
    FileCustomerRequirementsApprovalStore,
    FileCustomerRequirementsStore,
)
from runtime.product_requirements import RequirementStatus, validate_prd


NOW = datetime(2026, 8, 20, 17, tzinfo=timezone.utc)
CSRF = "day16-csrf-token-123456789"


def _services(root: Path, *, generate: bool = True):
    requests = CustomerProductRequestService(
        FileCustomerProductRequestStore(root / "requests"),
        lambda: NOW,
    )
    request = requests.submit(
        request_id="req-1",
        customer_id="customer-1",
        product_name="Community workshop planner",
        product_summary="Help local groups schedule and coordinate educational workshops.",
        target_users="Community organisers and workshop participants",
        features=("Publish workshops", "Manage registrations"),
        constraints=("No payment processing in the first release",),
    )
    requirements_approval_store = FileCustomerRequirementsApprovalStore(root / "approvals")
    requirements = CustomerRequirementsService(
        FileCustomerRequirementsStore(root / "requirements"),
        requests,
        lambda: NOW,
        requirements_approval_store.is_locked,
    )
    draft = requirements.save(
        customer_id="customer-1",
        request_id="req-1",
        expected_revision=0,
        primary_user_journey=(
            "An organiser publishes a workshop and participants reserve available places."
        ),
        desired_outcomes=("Workshops are visible", "Registrations are confirmed"),
        must_have_features=("Publish workshops", "Manage registrations"),
        success_metrics=("At least 80% of registrations are confirmed",),
        non_goals=("No payment processing in the first release",),
        platforms=("WEB",),
        data_sensitivity=DataSensitivity.PERSONAL_DATA,
        delivery_priority=DeliveryPriority.STANDARD,
    )
    requirements_approvals = CustomerRequirementsApprovalService(
        requirements_approval_store,
        requirements,
        lambda: NOW,
    )
    requirements_approval = requirements_approvals.approve(
        customer_id="customer-1",
        request_id="req-1",
        expected_revision=draft.revision,
        expected_digest=draft.digest,
        confirmed=True,
    )
    prds = CustomerPrdService(
        FileCustomerPrdStore(root / "prds"),
        requirements_approvals,
        lambda: NOW,
    )
    prd = None
    if generate:
        prd = prds.generate(
            customer_id="customer-1",
            request_id="req-1",
            expected_approval_digest=requirements_approval.digest,
        )
    store = FileCustomerPrdApprovalStore(root / "prd-approvals")
    approvals = CustomerPrdApprovalService(store, prds, lambda: NOW)
    return (
        requests,
        requirements,
        requirements_approvals,
        prds,
        approvals,
        request,
        draft,
        requirements_approval,
        prd,
        store,
    )


def _approve(service: CustomerPrdApprovalService, prd, **changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_prd_digest": prd.digest,
        "confirmed": True,
    }
    values.update(changes)
    return service.approve(**values)


def _application(root: Path, *, generate: bool = True):
    values = _services(root, generate=generate)
    requests, requirements, requirements_approvals, prds, approvals = values[:5]
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(requirements_approvals),
        CustomerPrdApplication(prds, approvals),
        CustomerPrdApprovalApplication(approvals),
    )
    return (application, *values)


def _form(prd, **changes):
    values = {
        "csrf_token": CSRF,
        "expected_prd_digest": prd.digest,
        "confirmation": "LOCK",
    }
    values.update(changes)
    return urlencode(values, doseq=True)


def _call(
    application,
    *,
    method="GET",
    path="/customer/requests/req-1/prd/approve",
    body="",
    customer="customer-1",
    csrf=CSRF,
    content_type="application/x-www-form-urlencoded",
):
    encoded = body.encode()
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(encoded)),
        "wsgi.input": BytesIO(encoded),
    }
    if customer is not None:
        environ["REMOTE_USER"] = customer
    if csrf is not None:
        environ["ascos.csrf_token"] = csrf
    observed = {}

    def start_response(status, headers):
        observed["status"] = status
        observed["headers"] = dict(headers)

    content = b"".join(application(environ, start_response))
    return observed["status"], observed["headers"], content


def test_prd_approval_identity_is_stable_bounded_and_rejects_unsafe_values():
    assert prd_approval_id_for("req-1") == prd_approval_id_for("req-1")
    assert prd_approval_id_for("req-1") != prd_approval_id_for("req-2")
    assert len(prd_approval_id_for("req-1")) < 128
    with pytest.raises(ValueError):
        prd_approval_id_for("../unsafe")


def test_approval_binds_exact_prd_and_is_write_once_idempotent(tmp_path):
    values = _services(tmp_path)
    approvals, prd, store = values[4], values[8], values[9]
    first = _approve(approvals, prd)
    second = _approve(approvals, prd)

    assert second == first
    assert first.confirmation_version == PRD_CONFIRMATION_VERSION
    assert first.prd_digest == prd.digest
    assert first.source_request_digest == prd.source_request_digest
    assert first.requirements_digest == prd.requirements_digest
    assert first.requirements_approval_digest == prd.approval_digest
    assert store.load("customer-1", "req-1") == first
    paths = tuple((tmp_path / "prd-approvals").rglob("prd-approval-v0.1.json"))
    assert len(paths) == 1
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600


def test_approval_projects_through_governed_lifecycle_and_locks_every_requirement(tmp_path):
    values = _services(tmp_path)
    approvals, prd = values[4], values[8]
    receipt = _approve(approvals, prd)
    governed = approvals.governed_document("customer-1", "req-1")

    assert governed.status is RequirementStatus.LOCKED
    assert governed.approver == "customer-1"
    assert governed.locked_at == receipt.approved_at
    assert governed.future_roadmap == ()
    assert not validate_prd(governed)
    assert all(item.status is RequirementStatus.LOCKED for item in governed.requirements)
    assert all(item.approver == "customer-1" for item in governed.requirements)
    assert tuple(item.action for item in governed.revision_history[-3:]) == (
        "UNDER_REVIEW",
        "APPROVED",
        "LOCKED",
    )
    assert governed.approval_history[0].approval_id == receipt.approval_id


def test_governed_projection_rejects_receipt_for_a_different_prd(tmp_path):
    values = _services(tmp_path)
    approvals, prd = values[4], values[8]
    receipt = _approve(approvals, prd)
    with pytest.raises(CustomerPrdApprovalConflict, match="does not bind"):
        from runtime.customer_prd import governed_locked_document

        governed_locked_document(replace(prd, title="Different product scope"), receipt)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approval_id", "../unsafe"),
        ("prd_version", "1.0"),
        ("prd_digest", "bad"),
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
    receipt = _approve(values[4], values[8])
    with pytest.raises(ValueError):
        replace(receipt, **{field: value})


def test_approval_requires_generated_prd_confirmation_and_exact_digest(tmp_path):
    values = _services(tmp_path / "missing", generate=False)
    with pytest.raises(CustomerPrdApprovalConflict, match="generated"):
        values[4].approve(
            customer_id="customer-1",
            request_id="req-1",
            expected_prd_digest="0" * 64,
            confirmed=True,
        )

    ready = _services(tmp_path / "ready")
    with pytest.raises(ValueError, match="confirmation"):
        _approve(ready[4], ready[8], confirmed=False)
    with pytest.raises(CustomerPrdApprovalConflict, match="stale"):
        _approve(ready[4], ready[8], expected_prd_digest="0" * 64)


def test_cross_customer_approval_is_blocked(tmp_path):
    values = _services(tmp_path)
    with pytest.raises(ProductRequestNotFound):
        _approve(values[4], values[8], customer_id="customer-2")


def test_store_restart_corruption_unknown_entry_and_symlink_detection(tmp_path):
    values = _services(tmp_path)
    prds, approvals, prd, store = values[3], values[4], values[8], values[9]
    receipt = _approve(approvals, prd)
    restarted = CustomerPrdApprovalService(
        FileCustomerPrdApprovalStore(tmp_path / "prd-approvals"),
        prds,
        lambda: NOW,
    )
    assert restarted.context("customer-1", "req-1")[4] == receipt

    path = next((tmp_path / "prd-approvals").rglob("prd-approval-v0.1.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["prd_digest"] = "0" * 64
    path.write_text(json.dumps(envelope))
    with pytest.raises(CustomerPrdApprovalCorrupt):
        store.load("customer-1", "req-1")

    path.write_text("{}")
    (path.parent / "unknown.txt").write_text("unsafe")
    with pytest.raises(CustomerPrdApprovalCorrupt, match="closed"):
        store.find("customer-1", "req-1")
    (path.parent / "unknown.txt").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CustomerPrdApprovalCorrupt, match="unsafe"):
        store.find("customer-1", "req-1")


def test_approval_checkpoint_is_customer_scoped_complete_and_hardened(tmp_path):
    values = _application(tmp_path)
    application, prd = values[0], values[9]
    status, headers, content = _call(application)

    assert status == "200 OK"
    assert b"Approve and lock Community workshop planner" in content
    assert b"REQ-JOURNEY-001" in content
    assert b"No payment processing in the first release" in content
    assert prd.digest.encode() in content
    assert b'name="customer_id"' not in content
    assert b"does not create a roadmap" in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]


def test_customer_approves_and_reopens_locked_prd_receipt(tmp_path):
    values = _application(tmp_path)
    application, approvals, prd = values[0], values[5], values[9]
    status, headers, _ = _call(application, method="POST", body=_form(prd))
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/approved")

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Approved and locked" in content
    assert b"Governed status" in content and b"LOCKED" in content
    assert b"planning and implementation have not started" in content
    receipt = approvals.context("customer-1", "req-1")[4]
    assert receipt is not None and receipt.digest.encode() in content

    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/prd/review",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/approved")


def test_prd_approval_web_rejects_csrf_confirmation_unknown_fields_and_stale_digest(tmp_path):
    values = _application(tmp_path)
    application, prd = values[0], values[9]
    assert _call(
        application,
        method="POST",
        body=_form(prd, csrf_token="wrong"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(prd, confirmation="REVIEW"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(prd) + "&unexpected=value",
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(prd, expected_prd_digest="0" * 64),
    )[0] == "409 Conflict"


def test_prd_approval_routes_require_identity_and_hide_cross_customer_records(tmp_path):
    application = _application(tmp_path)[0]
    assert _call(application, customer=None)[0] == "401 Unauthorized"
    assert _call(application, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, customer="customer-2")[0] == "404 Not Found"


def test_prd_approval_route_without_generated_prd_redirects_to_generation(tmp_path):
    application = _application(tmp_path, generate=False)[0]
    status, headers, _ = _call(application)
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd")
    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/prd/approved",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/review")
