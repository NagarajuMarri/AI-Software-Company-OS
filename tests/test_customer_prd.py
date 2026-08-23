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
    GENERATION_PROFILE,
    CustomerPrdApplication,
    CustomerPrdConflict,
    CustomerPrdCorrupt,
    CustomerPrdService,
    FileCustomerPrdStore,
    ids_for,
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
from runtime.product_requirements import (
    ProductRequirementsService,
    RequirementCategory,
    RequirementStatus,
    validate_prd,
)


NOW = datetime(2026, 8, 20, 16, tzinfo=timezone.utc)
CSRF = "day15-csrf-token-123456789"


def _services(root: Path, *, approve: bool = True, with_draft: bool = True):
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
        constraints=("Encrypt patient data in transit and at rest",),
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
            non_goals=("No autonomous medical advice", "No payment processing"),
            platforms=("WEB", "AUTOMATION"),
            data_sensitivity=DataSensitivity.PERSONAL_DATA,
            delivery_priority=DeliveryPriority.TIME_SENSITIVE,
        )
    approvals = CustomerRequirementsApprovalService(
        approval_store,
        requirements,
        lambda: NOW,
    )
    approval = None
    if approve:
        assert draft is not None
        approval = approvals.approve(
            customer_id="customer-1",
            request_id="req-1",
            expected_revision=draft.revision,
            expected_digest=draft.digest,
            confirmed=True,
        )
    prd_store = FileCustomerPrdStore(root / "prds")
    prds = CustomerPrdService(prd_store, approvals, lambda: NOW)
    return requests, requirements, approvals, prds, request, draft, approval, prd_store


def _generate(service: CustomerPrdService, approval, **changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_approval_digest": approval.digest,
    }
    values.update(changes)
    return service.generate(**values)


def _application(root: Path, *, approve: bool = True, with_draft: bool = True):
    values = _services(root, approve=approve, with_draft=with_draft)
    requests, requirements, approvals, prds = values[:4]
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(approvals),
        CustomerPrdApplication(prds),
    )
    return (application, *values)


def _form(approval, **changes):
    values = {
        "csrf_token": CSRF,
        "expected_approval_digest": approval.digest,
        "action": "GENERATE",
    }
    values.update(changes)
    return urlencode(values, doseq=True)


def _call(
    application,
    *,
    method="GET",
    path="/customer/requests/req-1/prd",
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


def test_ids_are_stable_bounded_and_reject_unsafe_values():
    assert ids_for("req-1") == ids_for("req-1")
    assert all(len(value) < 128 for value in ids_for("req-1"))
    assert ids_for("req-1") != ids_for("req-2")
    with pytest.raises(ValueError):
        ids_for("../unsafe")


def test_generation_binds_exact_approval_and_is_idempotent(tmp_path):
    _, _, _, prds, request, draft, approval, store = _services(tmp_path)
    first = _generate(prds, approval)
    second = _generate(prds, approval)

    assert second == first
    assert first.source_request_digest == request.digest
    assert first.requirements_digest == draft.digest
    assert first.approval_digest == approval.digest
    assert first.generation_profile == GENERATION_PROFILE
    assert store.load("customer-1", "req-1") == first
    paths = tuple((tmp_path / "prds").rglob("prd-v0.1.json"))
    assert len(paths) == 1
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600


def test_generated_prd_maps_all_approved_scope_with_stable_source_references(tmp_path):
    _, _, _, prds, _, draft, approval, _ = _services(tmp_path)
    value = _generate(prds, approval)

    ids = tuple(item.requirement_id for item in value.requirements)
    assert ids == (
        "REQ-JOURNEY-001",
        "REQ-FEATURE-001",
        "REQ-FEATURE-002",
        "REQ-CONSTRAINT-001",
        "REQ-PLATFORM-001",
        "REQ-DATA-001",
    )
    assert tuple(item.title for item in value.requirements[1:3]) == draft.must_have_features
    assert value.requirements[0].description == draft.primary_user_journey
    assert value.requirements[0].acceptance_criteria == draft.desired_outcomes
    first_feature, second_feature = value.requirements[1:3]
    assert first_feature.acceptance_criteria != draft.success_metrics
    assert first_feature.acceptance_criteria != second_feature.acceptance_criteria
    assert all(first_feature.title in criterion for criterion in first_feature.acceptance_criteria)
    assert all(second_feature.title in criterion for criterion in second_feature.acceptance_criteria)
    constraint = value.requirements[3]
    assert constraint.category is RequirementCategory.NON_FUNCTIONAL
    assert "Encrypt patient data in transit and at rest" in constraint.description
    assert all(
        "Encrypt patient data in transit and at rest" in criterion
        for criterion in constraint.acceptance_criteria[:1]
    )
    assert value.explicit_exclusions == (
        "No autonomous medical advice",
        "No payment processing",
    )
    assert {item.source_reference for item in value.requirements} == {
        "primary_user_journey + desired_outcomes",
        "must_have_features[1]",
        "must_have_features[2]",
        "request.constraints[1]",
        "platforms",
        "data_sensitivity",
    }


def test_generated_projection_uses_existing_prd_governance_but_stays_draft(tmp_path):
    _, _, _, prds, _, _, approval, _ = _services(tmp_path)
    value = _generate(prds, approval)
    governed = value.to_governed_document()

    assert governed.status is RequirementStatus.DRAFT
    assert governed.approver is None
    assert not validate_prd(governed)
    assert ProductRequirementsService.roadmap(governed) == ()
    assert all(item.status is RequirementStatus.DRAFT for item in governed.requirements)
    assert governed.future_roadmap == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_id", "../unsafe"),
        ("version", "1.0"),
        ("generation_profile", "unknown"),
        ("approval_digest", "bad"),
        ("requirements", ()),
        ("requirements", (object(),)),
        ("success_metrics", ()),
        ("platforms", ()),
        ("platforms", ("AUTOMATION", "WEB")),
        ("platforms", ("DESKTOP",)),
        ("data_sensitivity", "PERSONAL_DATA"),
        ("delivery_priority", "TIME_SENSITIVE"),
        ("generated_at", datetime(2026, 8, 20)),
        ("generated_at", datetime(2026, 8, 20, tzinfo=timezone(timedelta(hours=5, minutes=30)))),
    ],
)
def test_prd_model_rejects_invalid_authority(tmp_path, field, value):
    _, _, _, prds, _, _, approval, _ = _services(tmp_path)
    valid = _generate(prds, approval)
    with pytest.raises(ValueError):
        replace(valid, **{field: value})


def test_generation_requires_approval_and_exact_receipt_digest(tmp_path):
    _, _, _, prds, _, _, _, _ = _services(tmp_path / "unapproved", approve=False)
    with pytest.raises(CustomerPrdConflict, match="Approved"):
        prds.generate(
            customer_id="customer-1",
            request_id="req-1",
            expected_approval_digest="0" * 64,
        )

    _, _, _, ready, _, _, approval, _ = _services(tmp_path / "ready")
    with pytest.raises(CustomerPrdConflict, match="stale"):
        _generate(ready, approval, expected_approval_digest="0" * 64)


def test_cross_customer_generation_is_blocked(tmp_path):
    _, _, _, prds, _, _, approval, _ = _services(tmp_path)
    with pytest.raises(ProductRequestNotFound):
        _generate(prds, approval, customer_id="customer-2")


def test_store_restart_and_corruption_unknown_entry_and_symlink_detection(tmp_path):
    _, _, approvals, prds, _, _, approval, store = _services(tmp_path)
    value = _generate(prds, approval)
    restarted = CustomerPrdService(FileCustomerPrdStore(tmp_path / "prds"), approvals, lambda: NOW)
    assert restarted.context("customer-1", "req-1")[3] == value

    path = next((tmp_path / "prds").rglob("prd-v0.1.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["problem_statement"] = "Tampered"
    path.write_text(json.dumps(envelope))
    with pytest.raises(CustomerPrdCorrupt):
        store.load("customer-1", "req-1")

    path.write_text("{}")
    (path.parent / "unknown.txt").write_text("unsafe")
    with pytest.raises(CustomerPrdCorrupt, match="closed"):
        store.find("customer-1", "req-1")
    (path.parent / "unknown.txt").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(CustomerPrdCorrupt, match="unsafe"):
        store.find("customer-1", "req-1")


def test_generation_checkpoint_is_customer_scoped_and_security_hardened(tmp_path):
    values = _application(tmp_path)
    application, approval = values[0], values[7]
    status, headers, content = _call(application)

    assert status == "200 OK"
    assert b"Create the PRD for Clinic receptionist" in content
    assert b"No external AI call" in content
    assert approval.digest.encode() in content
    assert b'name="customer_id"' not in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert "form-action 'self'" in headers["Content-Security-Policy"]


def test_customer_generates_and_reopens_traceable_prd_review(tmp_path):
    values = _application(tmp_path)
    application, prds, approval = values[0], values[4], values[7]
    status, headers, _ = _call(application, method="POST", body=_form(approval))
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/review")

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Product manager draft" in content
    assert b"REQ-JOURNEY-001" in content
    assert b"REQ-FEATURE-002" in content
    assert b"Acceptance criteria" in content
    assert b"PRD draft only" in content
    assert b"no implementation has started" in content
    value = prds.context("customer-1", "req-1")[3]
    assert value is not None and value.digest.encode() in content

    status, headers, _ = _call(application)
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/review")


def test_prd_web_rejects_csrf_action_unknown_fields_and_stale_approval(tmp_path):
    values = _application(tmp_path)
    application, approval = values[0], values[7]
    assert _call(
        application,
        method="POST",
        body=_form(approval, csrf_token="wrong"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(approval, action="EXECUTE"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(approval) + "&unexpected=value",
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(approval, expected_approval_digest="0" * 64),
    )[0] == "409 Conflict"


def test_prd_routes_require_identity_and_hide_cross_customer_records(tmp_path):
    application = _application(tmp_path)[0]
    assert _call(application, customer=None)[0] == "401 Unauthorized"
    assert _call(application, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, customer="customer-2")[0] == "404 Not Found"


def test_prd_routes_without_approval_redirect_to_approval_boundary(tmp_path):
    application = _application(tmp_path, approve=False)[0]
    status, headers, _ = _call(application)
    assert status == "303 See Other"
    assert headers["Location"].endswith("/requirements/approved")
    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/prd/review",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/requirements/approved")


def test_prd_review_escapes_customer_content(tmp_path):
    requests, requirements, approvals, _, _, _, _, _ = _services(
        tmp_path,
        approve=False,
        with_draft=False,
    )
    requests.submit(
        request_id="req-xss",
        customer_id="customer-1",
        product_name="<script>alert(1)</script>",
        product_summary="<img src=x onerror=alert(1)> solves calls.",
        target_users="Safe teams",
        features=("Safe feature",),
        constraints=(),
    )
    draft = requirements.save(
        customer_id="customer-1",
        request_id="req-xss",
        expected_revision=0,
        primary_user_journey="A safe customer completes the journey.",
        desired_outcomes=("Safe result",),
        must_have_features=("Safe feature",),
        success_metrics=("One safe result",),
        non_goals=(),
        platforms=("WEB",),
        data_sensitivity=DataSensitivity.NO_PERSONAL_DATA,
        delivery_priority=DeliveryPriority.STANDARD,
    )
    approval = approvals.approve(
        customer_id="customer-1",
        request_id="req-xss",
        expected_revision=1,
        expected_digest=draft.digest,
        confirmed=True,
    )
    prds = CustomerPrdService(FileCustomerPrdStore(tmp_path / "prds"), approvals, lambda: NOW)
    prds.generate(
        customer_id="customer-1",
        request_id="req-xss",
        expected_approval_digest=approval.digest,
    )
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(approvals),
        CustomerPrdApplication(prds),
    )
    status, _, content = _call(
        application,
        path="/customer/requests/req-xss/prd/review",
    )
    assert status == "200 OK"
    assert b"<script>" not in content and b"<img" not in content
    assert b"&lt;script&gt;" in content and b"&lt;img" in content
