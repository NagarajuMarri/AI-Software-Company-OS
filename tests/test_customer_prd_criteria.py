from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
import stat
from urllib.parse import urlencode

import pytest

from runtime.customer_application import CustomerPortalApplication, ProductRequestNotFound
from runtime.customer_prd import (
    CRITERIA_CONFIRMATION_VERSION,
    CustomerPrdApplication,
    CustomerPrdApprovalApplication,
    CustomerPrdApprovalConflict,
    CustomerPrdApprovalService,
    CustomerPrdCriteriaApplication,
    CustomerPrdCriteriaConflict,
    CustomerPrdCriteriaCorrupt,
    CustomerPrdCriteriaEntry,
    CustomerPrdCriteriaRefinement,
    CustomerPrdCriteriaService,
    FileCustomerPrdApprovalStore,
    FileCustomerPrdCriteriaStore,
    criteria_refinement_id_for,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApplication,
    CustomerWorkspaceApplication,
)
from tests.test_customer_prd_approval import CSRF, NOW, _services


def _criteria_values():
    return {
        "REQ-FEATURE-001": (
            "An organiser can publish a workshop with a title, date, capacity, and location.",
            "A published workshop appears in the public workshop list immediately.",
            "Publishing is rejected when the date is past or capacity is not positive.",
        ),
        "REQ-FEATURE-002": (
            "A participant can reserve an available place and receives a confirmation.",
            "The remaining capacity decreases exactly once after a confirmed registration.",
            "Registration is rejected when the workshop has no remaining capacity.",
        ),
    }


def _ready(root: Path):
    values = _services(root)
    prds, raw_prd = values[3], values[8]
    gated_approval_store = FileCustomerPrdApprovalStore(root / "gated-prd-approvals")
    criteria = CustomerPrdCriteriaService(
        FileCustomerPrdCriteriaStore(root / "prd-criteria"),
        prds,
        lambda: NOW,
        prd_approval_locked=gated_approval_store.is_locked,
    )
    approvals = CustomerPrdApprovalService(
        gated_approval_store,
        prds,
        lambda: NOW,
        criteria=criteria,
    )
    return values, raw_prd, criteria, approvals


def _lock(service: CustomerPrdCriteriaService, prd, **changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_prd_digest": prd.digest,
        "criteria": _criteria_values(),
        "confirmed": True,
    }
    values.update(changes)
    return service.lock(**values)


def _application(root: Path):
    values, prd, criteria, approvals = _ready(root)
    application = CustomerWorkspaceApplication(
        CustomerPortalApplication(values[0]),
        CustomerRequirementsApplication(values[1]),
        CustomerRequirementsApprovalApplication(values[2]),
        CustomerPrdApplication(values[3], approvals, criteria=criteria),
        CustomerPrdApprovalApplication(approvals),
        prd_criteria=CustomerPrdCriteriaApplication(criteria, approvals),
    )
    return application, prd, criteria, approvals


def _call(
    application,
    *,
    method="GET",
    path="/customer/requests/req-1/prd/criteria",
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


def _form(prd, **changes):
    values = {
        "csrf_token": CSRF,
        "expected_prd_digest": prd.digest,
        "confirmation": "LOCK",
        **{
            f"criteria__{requirement_id}": "\n".join(criteria)
            for requirement_id, criteria in _criteria_values().items()
        },
    }
    values.update(changes)
    return urlencode(values)


def test_criteria_identity_and_models_are_bounded_and_strict():
    assert criteria_refinement_id_for("req-1") == criteria_refinement_id_for("req-1")
    assert criteria_refinement_id_for("req-1") != criteria_refinement_id_for("req-2")
    with pytest.raises(ValueError):
        criteria_refinement_id_for("../unsafe")
    with pytest.raises(ValueError):
        CustomerPrdCriteriaEntry("REQ-JOURNEY-001", ("one", "two"))
    with pytest.raises(ValueError):
        CustomerPrdCriteriaEntry("REQ-FEATURE-001", ("only one",))


def test_lock_binds_exact_prd_covers_every_feature_and_applies_only_criteria(tmp_path):
    _, raw_prd, service, _ = _ready(tmp_path)
    refinement = _lock(service, raw_prd)
    effective = service.effective_prd("customer-1", "req-1", required=True)

    assert effective is not None
    assert refinement.confirmation_version == CRITERIA_CONFIRMATION_VERSION
    assert refinement.source_prd_digest == raw_prd.digest
    assert tuple(item.requirement_id for item in refinement.entries) == (
        "REQ-FEATURE-001",
        "REQ-FEATURE-002",
    )
    assert effective.digest != raw_prd.digest
    assert effective.requirements[1].acceptance_criteria == _criteria_values()[
        "REQ-FEATURE-001"
    ]
    assert effective.requirements[2].acceptance_criteria == _criteria_values()[
        "REQ-FEATURE-002"
    ]
    assert effective.requirements[0] == raw_prd.requirements[0]
    assert effective.requirements[3:] == raw_prd.requirements[3:]
    assert effective.explicit_exclusions == raw_prd.explicit_exclusions
    path = next((tmp_path / "prd-criteria").rglob("criteria-v0.1.json"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_lock_requires_new_complete_specific_criteria_and_is_write_once(tmp_path):
    _, prd, service, _ = _ready(tmp_path)
    defaults = {
        item.requirement_id: item.acceptance_criteria
        for item in prd.requirements
        if item.requirement_id.startswith("REQ-FEATURE-")
    }
    with pytest.raises(CustomerPrdCriteriaConflict, match="refined"):
        _lock(service, prd, criteria=defaults)
    with pytest.raises(ValueError, match="incomplete"):
        _lock(service, prd, criteria={"REQ-FEATURE-001": _criteria_values()["REQ-FEATURE-001"]})
    with pytest.raises(CustomerPrdCriteriaConflict, match="stale"):
        _lock(service, prd, expected_prd_digest="0" * 64)
    with pytest.raises(ValueError, match="confirmation"):
        _lock(service, prd, confirmed=False)

    first = _lock(service, prd)
    assert _lock(service, prd) == first
    changed = dict(_criteria_values())
    changed["REQ-FEATURE-001"] = (
        "A different valid result is visible.",
        "A different invalid result is rejected.",
    )
    with pytest.raises(CustomerPrdCriteriaConflict, match="different"):
        _lock(service, prd, criteria=changed)


def test_approval_is_gated_and_binds_the_effective_refined_prd(tmp_path):
    _, raw_prd, criteria, approvals = _ready(tmp_path)
    with pytest.raises(CustomerPrdApprovalConflict, match="criteria"):
        approvals.approve(
            customer_id="customer-1",
            request_id="req-1",
            expected_prd_digest=raw_prd.digest,
            confirmed=True,
        )
    _lock(criteria, raw_prd)
    effective = criteria.effective_prd("customer-1", "req-1", required=True)
    assert effective is not None
    receipt = approvals.approve(
        customer_id="customer-1",
        request_id="req-1",
        expected_prd_digest=effective.digest,
        confirmed=True,
    )
    assert receipt.prd_digest == effective.digest
    assert approvals.governed_document("customer-1", "req-1").requirements[
        1
    ].acceptance_criteria == _criteria_values()["REQ-FEATURE-001"]


def test_store_restart_corruption_and_cross_customer_protection(tmp_path):
    values, prd, service, _ = _ready(tmp_path)
    refinement = _lock(service, prd)
    restarted = CustomerPrdCriteriaService(
        FileCustomerPrdCriteriaStore(tmp_path / "prd-criteria"),
        values[3],
        lambda: NOW + timedelta(days=1),
    )
    assert restarted.context("customer-1", "req-1")[1] == refinement
    with pytest.raises(ProductRequestNotFound):
        restarted.context("customer-2", "req-1")

    path = next((tmp_path / "prd-criteria").rglob("criteria-v0.1.json"))
    envelope = json.loads(path.read_text())
    envelope["record"]["source_prd_digest"] = "0" * 64
    path.write_text(json.dumps(envelope))
    with pytest.raises(CustomerPrdCriteriaCorrupt):
        restarted.context("customer-1", "req-1")


def test_browser_flow_refines_locks_and_then_exposes_prd_approval(tmp_path):
    application, prd, criteria, approvals = _application(tmp_path)
    status, headers, content = _call(
        application,
        path="/customer/requests/req-1/prd/review",
    )
    assert status == "200 OK"
    assert b"Refine acceptance criteria" in content
    assert b"Review and approve PRD" not in content
    assert headers["Cache-Control"] == "no-store"

    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/prd/approve",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/criteria")

    status, _, content = _call(application)
    assert status == "200 OK"
    assert b"uses no external AI and no repository" in content
    assert b'criteria__REQ-FEATURE-001' in content

    status, headers, _ = _call(
        application,
        method="POST",
        body=_form(prd),
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/review")
    assert criteria.is_locked("customer-1", "req-1")

    status, _, content = _call(
        application,
        path="/customer/requests/req-1/prd/review",
    )
    assert status == "200 OK"
    assert b"remaining capacity decreases exactly once" in content
    assert b"Review and approve PRD" in content

    status, _, content = _call(application)
    assert status == "200 OK"
    assert b"Feature acceptance criteria are locked" in content
    assert b"Refined and locked" in content

    effective = criteria.effective_prd("customer-1", "req-1", required=True)
    assert effective is not None
    approvals.approve(
        customer_id="customer-1",
        request_id="req-1",
        expected_prd_digest=effective.digest,
        confirmed=True,
    )
    status, headers, _ = _call(application)
    assert status == "303 See Other"
    assert headers["Location"].endswith("/prd/approved")
    with pytest.raises(CustomerPrdCriteriaConflict, match="approved PRD"):
        _lock(criteria, prd)


def test_browser_form_rejects_csrf_unknown_missing_and_unconfirmed_fields(tmp_path):
    application, prd, _, _ = _application(tmp_path)
    assert _call(
        application,
        method="POST",
        body=_form(prd, csrf_token="wrong"),
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(prd) + "&unexpected=value",
    )[0] == "400 Bad Request"
    assert _call(
        application,
        method="POST",
        body=_form(prd, confirmation=""),
    )[0] == "400 Bad Request"
    assert _call(application, customer=None)[0] == "401 Unauthorized"
    assert _call(application, csrf=None)[0] == "401 Unauthorized"
    assert _call(application, customer="customer-2")[0] == "404 Not Found"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("refinement_id", "../unsafe"),
        ("source_prd_digest", "bad"),
        ("entries", ()),
        ("entries", (CustomerPrdCriteriaEntry("REQ-FEATURE-001", ("one", "two")),) * 2),
        ("confirmation_version", "unknown"),
        ("locked_at", NOW.replace(tzinfo=None)),
    ],
)
def test_refinement_model_rejects_invalid_authority(tmp_path, field, value):
    _, prd, service, _ = _ready(tmp_path)
    valid = _lock(service, prd)
    with pytest.raises(ValueError):
        replace(valid, **{field: value})
