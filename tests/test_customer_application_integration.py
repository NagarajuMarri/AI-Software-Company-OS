from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.customer_application import (
    CustomerPortalApplication,
    CustomerProductRequestService,
    FileCustomerProductRequestStore,
)


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_customer_product_request_browser_journey(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    store = FileCustomerProductRequestStore(tmp_path / "requests")
    service = CustomerProductRequestService(
        store,
        lambda: datetime(2026, 8, 20, 10, tzinfo=timezone.utc),
    )
    portal = CustomerPortalApplication(service)

    def authenticated(environ, start_response):
        environ["REMOTE_USER"] = "founder-customer"
        environ["ascos.csrf_token"] = "founder-browser-csrf-token"
        return portal(environ, start_response)

    server = make_server(
        "127.0.0.1",
        0,
        authenticated,
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    screenshot: bytes
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                timezone_id="UTC",
            )
            page = context.new_page()
            console_errors = []
            request_failures = []
            page.on(
                "console",
                lambda message: console_errors.append(message.type)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda _error: console_errors.append("pageerror"))
            page.on("requestfailed", lambda request: request_failures.append(request.url))
            origin = f"http://127.0.0.1:{server.server_port}"
            response = page.goto(f"{origin}/customer", wait_until="networkidle")
            assert response is not None
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            assert response.headers["x-content-type-options"] == "nosniff"
            page.get_by_role("heading", name="Build your next product with ASCOS").wait_for()
            page.get_by_role("link", name="Describe a product").click()
            page.get_by_label("Product name").fill("AI receptionist for clinics")
            page.get_by_label("Product summary").fill(
                "Answer every incoming call and convert patient questions into appointments."
            )
            page.get_by_label("Target users").fill(
                "Independent clinic owners and reception teams in India"
            )
            page.get_by_label("Required features one per line").fill(
                "Answer incoming calls\nBook and reschedule appointments\n"
                "Send WhatsApp confirmations"
            )
            page.get_by_label("Constraints optional, one per line").fill(
                "Telugu and English\nNo autonomous medical advice"
            )
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Submit product request").click()
            page.get_by_text("Request submitted", exact=True).wait_for()
            page.get_by_role("heading", name="AI receptionist for clinics").wait_for()
            assert page.get_by_text("Book and reschedule appointments").is_visible()
            assert page.get_by_text("No autonomous medical advice").is_visible()
            assert console_errors == []
            assert request_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    requests = service.dashboard("founder-customer")
    assert len(requests) == 1
    assert requests[0].product_name == "AI receptionist for clinics"
    assert requests[0].features == (
        "Answer incoming calls",
        "Book and reschedule appointments",
        "Send WhatsApp confirmations",
    )
    target = os.environ.get("ASCOS_DAY11_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_founder_evidence(Path(target), requests[0].digest, screenshot)


def _write_founder_evidence(target: Path, request_digest: str, screenshot: bytes) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "customer-product-request.png"
    screenshot_path.write_bytes(screenshot)
    screenshot_digest = hashlib.sha256(screenshot).hexdigest()
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "customer.product_request.submit",
        "claims": [
            "CUSTOMER_DASHBOARD_VISIBLE",
            "PRODUCT_REQUEST_FORM_COMPLETED",
            "PRODUCT_REQUEST_PERSISTED",
            "CUSTOMER_SCOPED_DETAIL_VISIBLE",
            "SECURITY_HEADERS_VERIFIED",
        ],
        "request_digest": request_digest,
        "screenshot": {
            "file": screenshot_path.name,
            "digest": screenshot_digest,
        },
        "redaction_contract": "no credentials, session identifiers, CSRF values, or customer secrets",
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
