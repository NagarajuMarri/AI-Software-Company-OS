from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
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
from runtime.customer_requirements import (
    CONFIRMATION_VERSION,
    CustomerRequirementsApproval,
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApprovalService,
    CustomerRequirementsApplication,
    CustomerRequirementsService,
    CustomerWorkspaceApplication,
    DataSensitivity,
    DeliveryPriority,
    FileCustomerRequirementsApprovalStore,
    FileCustomerRequirementsStore,
    RequirementsApprovalConflict,
    RequirementsApprovalCorrupt,
    RequirementsDraftLocked,
    approval_id_for,
)


NOW = datetime(2026, 8, 20, 15, tzinfo=timezone.utc)
CSRF = "day14-csrf-token-123456789"


def _services(root: Path, *, with_draft: bool = True):
    requests = CustomerProductRequestService(
        FileCustomerProductRequestStore(root / "requests"),
        lambda: NOW,
    )
    request = requests.submit(
        request_id="req-1",
        customer_id="customer-1",
        product_name="Clinic receptionist",
        product_summary="Answer calls and convert questions into appointments.",
        target_users="Independent clinic teams",
        features=("Answer incoming calls", "Book appointments"),
        constraints=("No autonomous medical advice",),
    )
    approval_store = FileCustomerRequirementsApprovalStore(root / "approvals")
    requirements = CustomerRequirementsService(
        FileCustomerRequirementsStore(root / "requirements"),
        requests,
        lambda: NOW,
        approval_store.is_locked,
    )
    draft = None
    if with_draft:
        draft = requirements.save(
            customer_id="customer-1",
            request_id="req-1",
            expected_revision=0,
            primary_user_journey=(
                "A clinic owner configures hours and receives confirmed appointments."
            ),
            desired_outcomes=("Every call is answered", "Appointments are confirmed"),
            must_have_features=("Answer calls", "Book appointments"),
            success_metrics=("At least 90% of calls answered",),
            non_goals=("No autonomous medical advice",),
            platforms=("WEB", "AUTOMATION"),
            data_sensitivity=DataSensitivity.PERSONAL_DATA,
            delivery_priority=DeliveryPriority.STANDARD,
        )
    approvals = CustomerRequirementsApprovalService(
        approval_store,
        requirements,
        lambda: NOW,
    )
    return requests, requirements, approvals, request, draft, approval_store


def _approve(service: CustomerRequirementsApprovalService, draft, **changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_revision": draft.revision,
        "expected_digest": draft.digest,
        "confirmed": True,
    }
    values.update(changes)
    return service.approve(**values)


def _application(root: Path, *, with_draft: bool = True):
    requests, requirements, approvals, request, draft, store = _services(
        root,
        with_draft=with_draft,
    )
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(approvals),
    )
    return application, requirements, approvals, request, draft, store


def _form(draft, **changes):
    values = {
        "csrf_token": CSRF,
        "expected_revision": str(draft.revision),
        "expected_digest": draft.digest,
        "confirmation": "LOCK",
    }
    values.update(changes)
    return urlencode(values, doseq=True)


def _call(
    application,
    *,
    method="GET",
    path="/customer/requests/req-1/requirements/approve",
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


def test_approval_model_digest_and_identity_are_stable():
    value = CustomerRequirementsApproval(
        approval_id_for("req-1"),
        "customer-1",
        "req-1",
        "requirements-draft-1",
        2,
        "a" * 64,
        "b" * 64,
        CONFIRMATION_VERSION,
        NOW,
    )

    assert value.approval_id.startswith("approval-")
    assert len(value.digest) == 64
    assert replace(value).digest == value.digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approval_id", "../unsafe"),
        ("draft_revision", 0),
        ("draft_revision", True),
        ("requirements_digest", "bad"),
        ("source_request_digest", "z" * 64),
        ("confirmation_version", "unknown"),
        ("approved_at", datetime(2026, 8, 20)),
    ],
)
def test_approval_model_rejects_invalid_authority(field, value):
    values = {
        "approval_id": approval_id_for("req-1"),
        "customer_id": "customer-1",
        "request_id": "req-1",
        "draft_id": "requirements-draft-1",
        "draft_revision": 1,
        "source_request_digest": "a" * 64,
        "requirements_digest": "b" * 64,
        "confirmation_version": CONFIRMATION_VERSION,
        "approved_at": NOW,
    }
    values[field] = value
    with pytest.raises(ValueError):
        CustomerRequirementsApproval(**values)


def test_explicit_approval_binds_exact_draft_and_retry_is_idempotent(tmp_path):
    _, _, approvals, request, draft, store = _services(tmp_path)
    first = _approve(approvals, draft)
    second = _approve(approvals, draft)

    assert second == first
    assert first.source_request_digest == request.digest
    assert first.requirements_digest == draft.digest
    assert first.draft_revision == 1
    assert store.load("customer-1", "req-1") == first
    paths = tuple((tmp_path / "approvals").rglob("approval.json"))
    assert len(paths) == 1
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600


def test_approval_requires_draft_confirmation_and_exact_revision_digest(tmp_path):
    _, _, approvals, _, draft, _ = _services(tmp_path / "ready")
    with pytest.raises(ValueError, match="confirmation"):
        _approve(approvals, draft, confirmed=False)
    with pytest.raises(RequirementsApprovalConflict, match="stale"):
        _approve(approvals, draft, expected_revision=0)
    with pytest.raises(RequirementsApprovalConflict, match="stale"):
        _approve(approvals, draft, expected_digest="0" * 64)

    _, _, empty, _, _, _ = _services(tmp_path / "empty", with_draft=False)
    with pytest.raises(RequirementsApprovalConflict, match="saved"):
        empty.approve(
            customer_id="customer-1",
            request_id="req-1",
            expected_revision=1,
            expected_digest="0" * 64,
            confirmed=True,
        )


def test_approval_locks_future_requirement_revisions_and_survives_restart(tmp_path):
    requests, requirements, approvals, _, draft, store = _services(tmp_path)
    receipt = _approve(approvals, draft)

    with pytest.raises(RequirementsDraftLocked):
        requirements.save(
            customer_id="customer-1",
            request_id="req-1",
            expected_revision=1,
            primary_user_journey="A changed journey that must remain forbidden after approval.",
            desired_outcomes=("Changed",),
            must_have_features=("Changed",),
            success_metrics=("Changed",),
            non_goals=(),
            platforms=("WEB",),
            data_sensitivity=DataSensitivity.NO_PERSONAL_DATA,
            delivery_priority=DeliveryPriority.STANDARD,
        )

    restarted_requirements = CustomerRequirementsService(
        FileCustomerRequirementsStore(tmp_path / "requirements"),
        requests,
        lambda: NOW,
        store.is_locked,
    )
    restarted = CustomerRequirementsApprovalService(store, restarted_requirements, lambda: NOW)
    assert restarted.context("customer-1", "req-1")[2] == receipt
    assert restarted_requirements.is_locked("customer-1", "req-1")


def test_cross_customer_approval_is_blocked(tmp_path):
    _, _, approvals, _, draft, _ = _services(tmp_path)
    with pytest.raises(ProductRequestNotFound):
        _approve(approvals, draft, customer_id="customer-2")


def test_store_detects_tampering_unknown_entries_and_symlinks(tmp_path):
    _, _, approvals, _, draft, store = _services(tmp_path)
    _approve(approvals, draft)
    path = next((tmp_path / "approvals").rglob("approval.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["requirements_digest"] = "0" * 64
    path.write_text(json.dumps(envelope))
    with pytest.raises(RequirementsApprovalCorrupt):
        store.load("customer-1", "req-1")

    path.write_text("{}")
    (path.parent / "unknown.txt").write_text("unsafe")
    with pytest.raises(RequirementsApprovalCorrupt, match="closed"):
        store.find("customer-1", "req-1")
    (path.parent / "unknown.txt").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(RequirementsApprovalCorrupt, match="unsafe"):
        store.find("customer-1", "req-1")


def test_approval_form_is_exact_customer_scoped_and_security_hardened(tmp_path):
    application, _, _, _, draft, _ = _application(tmp_path)
    status, headers, content = _call(application)

    assert status == "200 OK"
    assert b"Approve Clinic receptionist" in content
    assert b"permanently locks revision 1" in content
    assert draft.digest.encode() in content
    assert b'name="customer_id"' not in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]


def test_customer_approves_and_reopens_receipt_while_edit_redirects(tmp_path):
    application, requirements, approvals, _, draft, _ = _application(tmp_path)
    status, headers, _ = _call(application, method="POST", body=_form(draft))
    assert status == "303 See Other"
    assert headers["Location"].endswith("/requirements/approved")

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Requirements baseline" in content
    assert b"Approved" in content
    assert b"implementation has not started" in content
    receipt = approvals.context("customer-1", "req-1")[2]
    assert receipt is not None and receipt.digest.encode() in content
    assert requirements.is_locked("customer-1", "req-1")

    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/requirements",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/requirements/approved")

    status, _, review = _call(
        application,
        path="/customer/requests/req-1/requirements/review",
    )
    assert status == "200 OK"
    assert b"View approval receipt" in review
    assert b"Edit draft" not in review


def test_approval_web_rejects_csrf_confirmation_unknown_fields_and_stale_form(tmp_path):
    application, _, _, _, draft, _ = _application(tmp_path)
    assert _call(
        application,
        method="POST",
        body=_form(draft, csrf_token="wrong"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=urlencode(
            {
                "csrf_token": CSRF,
                "expected_revision": "1",
                "expected_digest": draft.digest,
            }
        ),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(draft) + "&unexpected=value",
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(draft, expected_digest="0" * 64),
    )[0] == "409 Conflict"


def test_approval_routes_require_identity_and_hide_cross_customer_records(tmp_path):
    application, _, _, _, _, _ = _application(tmp_path)
    assert _call(application, customer=None)[0] == "401 Unauthorized"
    assert _call(application, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, customer="customer-2")[0] == "404 Not Found"


def test_approval_routes_without_draft_or_receipt_redirect_to_safe_steps(tmp_path):
    application, _, _, _, _, _ = _application(tmp_path, with_draft=False)
    status, headers, _ = _call(application)
    assert status == "303 See Other"
    assert headers["Location"].endswith("/requirements")
    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/requirements/approved",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/requirements/review")


def test_receipt_escapes_customer_content(tmp_path):
    requests, requirements, approvals, _, _, store = _services(tmp_path, with_draft=False)
    requests.submit(
        request_id="req-xss",
        customer_id="customer-1",
        product_name="<script>alert(1)</script>",
        product_summary="Safe summary",
        target_users="Safe users",
        features=("Safe feature",),
        constraints=(),
    )
    draft = requirements.save(
        customer_id="customer-1",
        request_id="req-xss",
        expected_revision=0,
        primary_user_journey="<img src=x onerror=alert(1)> completes the journey.",
        desired_outcomes=("Safe result",),
        must_have_features=("Safe feature",),
        success_metrics=("One safe result",),
        non_goals=(),
        platforms=("WEB",),
        data_sensitivity=DataSensitivity.NO_PERSONAL_DATA,
        delivery_priority=DeliveryPriority.STANDARD,
    )
    approvals.approve(
        customer_id="customer-1",
        request_id="req-xss",
        expected_revision=1,
        expected_digest=draft.digest,
        confirmed=True,
    )
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(approvals),
    )
    status, _, content = _call(
        application,
        path="/customer/requests/req-xss/requirements/approved",
    )
    assert status == "200 OK"
    assert b"<script>" not in content and b"<img" not in content
    assert b"&lt;script&gt;" in content and b"&lt;img" in content
    assert store.is_locked("customer-1", "req-xss")
