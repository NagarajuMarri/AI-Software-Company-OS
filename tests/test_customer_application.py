from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

from runtime.customer_application import (
    CustomerPortalApplication,
    CustomerProductRequest,
    CustomerRequestProgress,
    CustomerProductRequestService,
    FileCustomerProductRequestStore,
    ProductRequestConflict,
    ProductRequestCorrupt,
    ProductRequestNotFound,
    ProductRequestStage,
)


NOW = datetime(2026, 8, 20, 10, tzinfo=timezone.utc)
CSRF = "csrf-token-1234567890"


def _request(**changes):
    values = {
        "request_id": "req-123",
        "customer_id": "customer-1",
        "product_name": "Clinic receptionist",
        "product_summary": "Answer calls and turn them into confirmed appointments.",
        "target_users": "Independent clinics in India",
        "features": ("Answer incoming calls", "Book appointments"),
        "constraints": ("Telugu and English",),
        "stage": ProductRequestStage.SUBMITTED,
        "submitted_at": NOW,
    }
    values.update(changes)
    return CustomerProductRequest(**values)


def _service(root: Path) -> CustomerProductRequestService:
    return CustomerProductRequestService(
        FileCustomerProductRequestStore(root),
        lambda: NOW,
    )


def _form(**changes):
    values = {
        "csrf_token": CSRF,
        "request_id": "req-browser-1",
        "product_name": "Clinic receptionist",
        "product_summary": "Answer calls and book appointments for busy clinics.",
        "target_users": "Clinic owners and reception teams",
        "features": "Answer incoming calls\nBook appointments",
        "constraints": "Telugu and English",
    }
    values.update(changes)
    return urlencode(values)


def _call(
    application,
    method="GET",
    path="/customer",
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


def test_product_request_is_immutable_and_digest_stable():
    first = _request()
    second = _request()

    assert first == second
    assert len(first.digest) == 64
    assert first.digest == second.digest
    assert first.business_identity[-1] is ProductRequestStage.SUBMITTED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_id", "../escape"),
        ("customer_id", "customer/escape"),
        ("product_name", " "),
        ("product_name", "x" * 121),
        ("product_summary", "bad\x00value"),
        ("target_users", " users "),
        ("features", ()),
        ("features", ("Same", "same")),
        ("features", tuple(str(index) for index in range(21))),
        ("constraints", tuple(str(index) for index in range(21))),
        ("stage", "SUBMITTED"),
        ("submitted_at", datetime(2026, 8, 20, 10)),
    ],
)
def test_product_request_rejects_invalid_authority(field, value):
    with pytest.raises(ValueError):
        _request(**{field: value})


def test_file_store_is_write_once_restart_safe_and_customer_scoped(tmp_path):
    store = FileCustomerProductRequestStore(tmp_path / "requests")
    value = _request()

    assert store.save(value) == value
    assert store.save(value) == value
    restarted = FileCustomerProductRequestStore(tmp_path / "requests")
    assert restarted.load(value.customer_id, value.request_id) == value
    assert restarted.list_for_customer(value.customer_id) == (value,)
    assert restarted.list_for_customer("customer-2") == ()
    with pytest.raises(ProductRequestNotFound):
        restarted.load("customer-2", value.request_id)


def test_file_store_rejects_conflict_and_corruption(tmp_path):
    root = tmp_path / "requests"
    store = FileCustomerProductRequestStore(root)
    value = _request()
    store.save(value)

    with pytest.raises(ProductRequestConflict):
        store.save(replace(value, product_name="Different product"))

    path = root / value.customer_id / f"{value.request_id}.json"
    envelope = json.loads(path.read_text())
    envelope["record"]["product_name"] = "Tampered"
    path.write_text(json.dumps(envelope))
    with pytest.raises(ProductRequestCorrupt):
        store.load(value.customer_id, value.request_id)


def test_file_store_rejects_symlinked_customer_authority(tmp_path):
    root = tmp_path / "requests"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "customer-1").symlink_to(outside, target_is_directory=True)
    store = FileCustomerProductRequestStore(root)

    with pytest.raises(ValueError):
        store.list_for_customer("customer-1")


def test_file_store_rejects_symlinked_request_file(tmp_path):
    root = tmp_path / "requests"
    customer = root / "customer-1"
    customer.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (customer / "req-123.json").symlink_to(outside)
    store = FileCustomerProductRequestStore(root)

    with pytest.raises(ProductRequestCorrupt):
        store.load("customer-1", "req-123")


def test_service_exact_retry_reuses_original_submission_time(tmp_path):
    ticks = iter(
        (
            NOW,
            datetime(2026, 8, 20, 10, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 20, 10, 2, tzinfo=timezone.utc),
        )
    )
    service = CustomerProductRequestService(
        FileCustomerProductRequestStore(tmp_path / "requests"),
        lambda: next(ticks),
    )
    arguments = {
        "request_id": "req-retry",
        "customer_id": "customer-1",
        "product_name": "Clinic receptionist",
        "product_summary": "Answer calls and book appointments.",
        "target_users": "Clinics",
        "features": ("Answer calls",),
        "constraints": (),
    }
    first = service.submit(**arguments)
    second = service.submit(**arguments)

    assert second == first
    assert second.submitted_at == NOW
    with pytest.raises(ProductRequestConflict):
        service.submit(**{**arguments, "product_name": "Different"})


def test_customer_dashboard_requires_upstream_identity(tmp_path):
    application = CustomerPortalApplication(_service(tmp_path / "requests"))

    status, headers, content = _call(application, customer=None)

    assert status == "401 Unauthorized"
    assert headers["Cache-Control"] == "no-store"
    assert b"Sign in required" in content


def test_new_request_form_has_csrf_and_browser_security_headers(tmp_path):
    application = CustomerPortalApplication(_service(tmp_path / "requests"))

    status, headers, content = _call(application, path="/customer/requests/new")

    assert status == "200 OK"
    assert f'value="{CSRF}"'.encode() in content
    assert b'form method="post"' in content
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "form-action 'self'" in headers["Content-Security-Policy"]


def test_customer_can_submit_reopen_and_list_product_request(tmp_path):
    service = _service(tmp_path / "requests")
    application = CustomerPortalApplication(service)

    status, headers, content = _call(
        application,
        method="POST",
        path="/customer/requests",
        body=_form(),
    )
    assert status == "303 See Other"
    assert headers["Location"] == "/customer/requests/req-browser-1"
    assert content == b""

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"Request submitted" in content
    assert b"Clinic receptionist" in content
    assert b"Answer incoming calls" in content

    status, _, content = _call(application)
    assert status == "200 OK"
    assert b"1 submitted" in content
    assert b"Clinic receptionist" in content
    assert service.get("customer-1", "req-browser-1").features == (
        "Answer incoming calls",
        "Book appointments",
    )


def test_dashboard_links_to_latest_governed_checkpoint(tmp_path):
    service = _service(tmp_path / "requests")
    service.submit(
        request_id="req-progress",
        customer_id="customer-1",
        product_name="Family vault",
        product_summary="Keep family information ready.",
        target_users="Families",
        features=("Store records",),
        constraints=(),
    )
    application = CustomerPortalApplication(
        service,
        lambda customer_id, request_id: CustomerRequestProgress(
            request_id,
            "PRD approved",
            "Open approved PRD",
            f"/customer/requests/{request_id}/prd/approved",
        ),
    )

    status, _, content = _call(application)

    assert status == "200 OK"
    assert b"PRD approved" in content
    assert b"Open approved PRD" in content
    assert b'href="/customer/requests/req-progress/prd/approved"' in content


def test_customer_progress_rejects_ungoverned_navigation():
    with pytest.raises(ValueError, match="governed"):
        CustomerRequestProgress(
            "req-1",
            "Unsafe",
            "Leave ASCOS",
            "/customer/requests/req-1/../../../outside",
        )


def test_detail_escapes_customer_text_and_blocks_cross_customer_read(tmp_path):
    application = CustomerPortalApplication(_service(tmp_path / "requests"))
    status, headers, _ = _call(
        application,
        method="POST",
        path="/customer/requests",
        body=_form(product_name="<script>alert(1)</script>"),
    )
    assert status == "303 See Other"

    status, _, content = _call(application, path=headers["Location"])
    assert status == "200 OK"
    assert b"<script>" not in content
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in content

    status, _, content = _call(
        application,
        path=headers["Location"],
        customer="customer-2",
    )
    assert status == "404 Not Found"
    assert b"script" not in content.lower()


@pytest.mark.parametrize(
    "changes",
    [
        {"body": _form(csrf_token="wrong-token")},
        {"body": _form(features="")},
        {"body": _form(product_name=" ")},
        {"body": _form(product_summary="x" * 33_000)},
        {"content_type": "application/json", "body": "{}"},
        {"csrf": None, "body": _form()},
    ],
)
def test_submission_fails_closed_for_invalid_request(tmp_path, changes):
    application = CustomerPortalApplication(_service(tmp_path / "requests"))

    status, _, content = _call(
        application,
        method="POST",
        path="/customer/requests",
        **changes,
    )

    assert status == "400 Bad Request"
    assert b"Request not submitted" in content
    assert _service(tmp_path / "requests").dashboard("customer-1") == ()


def test_unknown_routes_do_not_expose_application_details(tmp_path):
    application = CustomerPortalApplication(_service(tmp_path / "requests"))

    status, _, content = _call(application, path="/customer/internal")

    assert status == "404 Not Found"
    assert b"Page not found" in content
