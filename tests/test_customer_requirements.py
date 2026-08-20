from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import urlencode

import pytest

from runtime.customer_application import (
    CustomerPortalApplication,
    CustomerProductRequestService,
    FileCustomerProductRequestStore,
    ProductRequestNotFound,
)
from runtime.customer_requirements import (
    CustomerRequirementsApplication,
    CustomerRequirementsDraft,
    CustomerRequirementsService,
    CustomerWorkspaceApplication,
    DataSensitivity,
    DeliveryPriority,
    FileCustomerRequirementsStore,
    RequirementsDraftConflict,
    RequirementsDraftCorrupt,
    draft_id_for,
)


NOW = datetime(2026, 8, 20, 14, tzinfo=timezone.utc)
CSRF = "day13-csrf-token-123456789"


def _requests(root: Path) -> CustomerProductRequestService:
    return CustomerProductRequestService(FileCustomerProductRequestStore(root), lambda: NOW)


def _request(service: CustomerProductRequestService, customer="customer-1", request_id="req-1"):
    return service.submit(
        request_id=request_id,
        customer_id=customer,
        product_name="Clinic receptionist",
        product_summary="Answer calls and convert questions into appointments.",
        target_users="Independent clinic teams",
        features=("Answer incoming calls", "Book appointments"),
        constraints=("No autonomous medical advice",),
    )


def _service(root: Path):
    requests = _requests(root / "requests")
    _request(requests)
    return (
        CustomerRequirementsService(
            FileCustomerRequirementsStore(root / "requirements"),
            requests,
            lambda: NOW,
        ),
        requests,
    )


def _values(**changes):
    values = {
        "customer_id": "customer-1",
        "request_id": "req-1",
        "expected_revision": 0,
        "primary_user_journey": "A clinic owner signs in, configures hours, and receives booked appointments.",
        "desired_outcomes": ("Every call is answered", "Appointments are confirmed"),
        "must_have_features": ("Answer calls", "Book appointments"),
        "success_metrics": ("At least 90% of calls answered",),
        "non_goals": ("No autonomous medical advice",),
        "platforms": ("WEB", "AUTOMATION"),
        "data_sensitivity": DataSensitivity.PERSONAL_DATA,
        "delivery_priority": DeliveryPriority.STANDARD,
    }
    values.update(changes)
    return values


def _form(**changes):
    values = {
        "csrf_token": CSRF,
        "expected_revision": "0",
        "primary_user_journey": "A clinic owner configures hours and receives booked appointments.",
        "desired_outcomes": "Every call is answered\nAppointments are confirmed",
        "must_have_features": "Answer incoming calls\nBook appointments",
        "success_metrics": "At least 90% of calls answered",
        "non_goals": "No autonomous medical advice",
        "platforms": ["WEB", "AUTOMATION"],
        "data_sensitivity": "PERSONAL_DATA",
        "delivery_priority": "STANDARD",
    }
    values.update(changes)
    return urlencode(values, doseq=True)


def _call(application, method="GET", path="/customer/requests/req-1/requirements", body="", customer="customer-1", csrf=CSRF):
    encoded = body.encode()
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
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


def test_requirements_draft_digest_and_bounded_identity_are_stable(tmp_path):
    service, _ = _service(tmp_path)
    value = service.save(**_values())

    assert value.revision == 1
    assert value.draft_id == draft_id_for("req-1")
    assert len(value.draft_id) < 128
    assert len(value.digest) == 64
    assert value.digest == replace(value).digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("primary_user_journey", " "),
        ("desired_outcomes", ()),
        ("must_have_features", ("Same", "same")),
        ("success_metrics", tuple(str(item) for item in range(11))),
        ("non_goals", tuple(str(item) for item in range(11))),
        ("platforms", ()),
        ("platforms", ("WEB", "UNKNOWN")),
        ("data_sensitivity", "PERSONAL_DATA"),
        ("delivery_priority", "STANDARD"),
    ],
)
def test_requirements_draft_rejects_invalid_authority(tmp_path, field, value):
    service, _ = _service(tmp_path)
    with pytest.raises(ValueError):
        service.save(**_values(**{field: value}))


def test_service_binds_source_request_and_exact_retry_is_idempotent(tmp_path):
    service, requests = _service(tmp_path)
    first = service.save(**_values())
    second = service.save(**_values())

    assert second == first
    assert first.source_request_digest == requests.get("customer-1", "req-1").digest
    assert service.history("customer-1", "req-1") == (first,)


def test_revision_history_is_append_only_restart_safe_and_stale_writes_fail(tmp_path):
    service, requests = _service(tmp_path)
    first = service.save(**_values())
    second = service.save(
        **_values(
            expected_revision=1,
            success_metrics=("At least 95% of calls answered",),
        )
    )
    assert second.revision == 2
    assert first.digest != second.digest

    restarted = CustomerRequirementsService(
        FileCustomerRequirementsStore(tmp_path / "requirements"),
        requests,
        lambda: NOW,
    )
    assert restarted.context("customer-1", "req-1")[1] == second
    assert restarted.history("customer-1", "req-1") == (first, second)
    with pytest.raises(RequirementsDraftConflict):
        restarted.save(**_values(expected_revision=0, non_goals=("Different",)))


def test_cross_customer_read_and_write_are_blocked(tmp_path):
    service, _ = _service(tmp_path)
    service.save(**_values())

    with pytest.raises(ProductRequestNotFound):
        service.context("customer-2", "req-1")
    with pytest.raises(ProductRequestNotFound):
        service.save(**_values(customer_id="customer-2"))


def test_store_detects_tampering_gaps_unknown_entries_and_symlinks(tmp_path):
    service, _ = _service(tmp_path)
    value = service.save(**_values())
    root = tmp_path / "requirements"
    revision = next(root.rglob("revision-000001.json"))
    envelope = json.loads(revision.read_text())
    envelope["record"]["primary_user_journey"] = "Tampered"
    revision.write_text(json.dumps(envelope))
    with pytest.raises(RequirementsDraftCorrupt):
        FileCustomerRequirementsStore(root).latest("customer-1", "req-1")

    revision.write_bytes(json.dumps({}).encode())
    revision.rename(revision.with_name("revision-000002.json"))
    with pytest.raises(RequirementsDraftCorrupt, match="non-contiguous"):
        FileCustomerRequirementsStore(root).history("customer-1", "req-1")

    directory = revision.parent
    revision.with_name("revision-000002.json").rename(revision)
    (directory / "unknown.txt").write_text("unsafe")
    with pytest.raises(RequirementsDraftCorrupt, match="unknown"):
        FileCustomerRequirementsStore(root).history("customer-1", "req-1")
    (directory / "unknown.txt").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    revision.unlink()
    revision.symlink_to(outside)
    with pytest.raises(RequirementsDraftCorrupt, match="unsafe"):
        FileCustomerRequirementsStore(root).history("customer-1", "req-1")
    assert value.customer_id == "customer-1"


def test_guided_form_prefills_immutable_request_and_security_headers(tmp_path):
    service, requests = _service(tmp_path)
    application = CustomerRequirementsApplication(service)

    status, headers, content = _call(application)

    assert status == "200 OK"
    assert b"Clarify Clinic receptionist" in content
    assert b"Answer incoming calls" in content
    assert b"Original request remains immutable" in content
    assert f'value="{CSRF}"'.encode() in content
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert requests.get("customer-1", "req-1").product_name == "Clinic receptionist"


def test_customer_saves_and_reopens_requirements_review(tmp_path):
    service, requests = _service(tmp_path)
    portal = CustomerPortalApplication(requests)
    application = CustomerWorkspaceApplication(portal, CustomerRequirementsApplication(service))

    status, headers, _ = _call(application, method="POST", body=_form())
    assert status == "303 See Other"
    assert headers["Location"] == "/customer/requests/req-1/requirements/review"

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Requirements draft" in content
    assert b"Draft saved" in content
    assert b"At least 90% of calls answered" in content
    assert b"Draft only" in content
    assert b"no implementation has started" in content

    status, _, detail = _call(application, path="/customer/requests/req-1")
    assert status == "200 OK"
    assert b"Refine requirements" in detail


def test_web_rejects_csrf_stale_cross_customer_and_unexpected_fields(tmp_path):
    service, _ = _service(tmp_path)
    application = CustomerRequirementsApplication(service)

    status, _, _ = _call(application, method="POST", body=_form(csrf_token="wrong"))
    assert status == "400 Bad Request"
    service.save(**_values())
    status, _, content = _call(
        application,
        method="POST",
        body=_form(expected_revision="0", non_goals="Changed"),
    )
    assert status == "409 Conflict"
    assert b"Reload the latest" in content

    status, _, _ = _call(application, customer="customer-2")
    assert status == "404 Not Found"
    status, _, _ = _call(
        application,
        method="POST",
        body=_form() + "&unexpected=value",
    )
    assert status == "400 Bad Request"


def test_review_escapes_customer_requirements(tmp_path):
    service, _ = _service(tmp_path)
    service.save(
        **_values(primary_user_journey="<script>alert(1)</script> completes a safe journey.")
    )
    application = CustomerRequirementsApplication(service)

    status, _, content = _call(
        application,
        path="/customer/requests/req-1/requirements/review",
    )

    assert status == "200 OK"
    assert b"<script>" not in content
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in content


def test_requirements_route_requires_server_identity_and_csrf(tmp_path):
    service, _ = _service(tmp_path)
    application = CustomerRequirementsApplication(service)

    assert _call(application, customer=None)[0] == "401 Unauthorized"
    assert _call(application, csrf=None)[0] == "401 Unauthorized"


def test_review_without_draft_redirects_to_guided_form(tmp_path):
    service, _ = _service(tmp_path)
    application = CustomerRequirementsApplication(service)
    status, headers, _ = _call(
        application,
        path="/customer/requests/req-1/requirements/review",
    )
    assert status == "303 See Other"
    assert headers["Location"].endswith("/requirements")
