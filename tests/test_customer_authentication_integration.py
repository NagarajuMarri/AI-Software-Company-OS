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
from runtime.customer_authentication import (
    AuthenticatedCustomerApplication,
    CustomerAuthenticationService,
    FileCustomerAccountStore,
    FileCustomerSessionStore,
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
def test_real_customer_signup_logout_login_and_returning_workspace(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    accounts = FileCustomerAccountStore(tmp_path / "authentication")
    sessions = FileCustomerSessionStore(tmp_path / "authentication")
    authentication = CustomerAuthenticationService(
        accounts,
        sessions,
        clock=lambda: datetime(2026, 8, 20, 12, tzinfo=timezone.utc),
    )
    requests = CustomerProductRequestService(
        FileCustomerProductRequestStore(tmp_path / "requests"),
        lambda: datetime(2026, 8, 20, 12, 5, tzinfo=timezone.utc),
    )
    application = AuthenticatedCustomerApplication(
        authentication,
        CustomerPortalApplication(requests),
        preauth_secret=b"day-12-founder-browser-preauthentication-secret",
        secure_cookies=False,
        clock=lambda: datetime(2026, 8, 20, 12, tzinfo=timezone.utc),
    )
    server = make_server(
        "127.0.0.1",
        0,
        application,
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    screenshots: dict[str, bytes] = {}
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                timezone_id="UTC",
            )
            page = context.new_page()
            console_errors: list[str] = []
            request_failures: list[str] = []
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: request_failures.append(request.url))
            origin = f"http://127.0.0.1:{server.server_port}"

            response = page.goto(f"{origin}/customer", wait_until="networkidle")
            assert response is not None
            assert page.url == f"{origin}/login"
            assert response.headers["cache-control"] == "no-store"
            screenshots["login.png"] = page.screenshot(full_page=True)

            page.get_by_role("link", name="Create an account").click()
            page.get_by_label("Email address").fill("founder@example.com")
            page.get_by_label("Password", exact=True).fill("SecureFounder123")
            page.get_by_label("Confirm password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Create account").click()
            page.get_by_role("heading", name="Build your next product with ASCOS").wait_for()

            page.get_by_role("link", name="Describe a product").click()
            page.get_by_label("Product name").fill("AI receptionist for clinics")
            page.get_by_label("Product summary").fill(
                "Answer calls and turn customer questions into confirmed appointments."
            )
            page.get_by_label("Target users").fill("Independent clinic teams in India")
            page.get_by_label("Required features one per line").fill(
                "Answer incoming calls\nBook appointments\nSend WhatsApp confirmations"
            )
            page.get_by_label("Constraints optional, one per line").fill(
                "No autonomous medical advice"
            )
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Submit product request").click()
            page.get_by_text("Request submitted", exact=True).wait_for()

            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign out").click()
            page.get_by_role("heading", name="Welcome back").wait_for()
            page.get_by_label("Email address").fill("FOUNDER@EXAMPLE.COM")
            page.get_by_label("Password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign in").click()
            page.get_by_role("heading", name="Build your next product with ASCOS").wait_for()
            page.get_by_text("AI receptionist for clinics", exact=True).wait_for()
            page.reload(wait_until="networkidle")
            assert page.get_by_text("AI receptionist for clinics", exact=True).is_visible()
            screenshots["returning-workspace.png"] = page.screenshot(full_page=True)

            cookies = context.cookies()
            session_cookie = next(item for item in cookies if item["name"] == "ascos_session")
            assert session_cookie["httpOnly"] is True
            assert session_cookie["sameSite"] == "Strict"
            assert console_errors == []
            assert request_failures == []
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    customer_directories = tuple(path.name for path in (tmp_path / "requests").iterdir())
    assert len(customer_directories) == 1
    values = requests.dashboard(customer_directories[0])
    assert len(values) == 1
    assert values[0].product_name == "AI receptionist for clinics"
    persisted = b"".join(path.read_bytes() for path in (tmp_path / "authentication").rglob("*.*"))
    assert b"SecureFounder123" not in persisted

    target = os.environ.get("ASCOS_DAY12_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_founder_evidence(Path(target), values[0].digest, screenshots)


def _write_founder_evidence(
    target: Path,
    request_digest: str,
    screenshots: dict[str, bytes],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_claims = {}
    for name, content in screenshots.items():
        (target / name).write_bytes(content)
        screenshot_claims[name] = hashlib.sha256(content).hexdigest()
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "customer.authentication.returning_workspace",
        "claims": [
            "CUSTOMER_SIGNUP_COMPLETED",
            "SERVER_SIDE_SESSION_PERSISTED",
            "CUSTOMER_LOGOUT_REVOKED_SESSION",
            "RETURNING_CUSTOMER_LOGIN_COMPLETED",
            "EXISTING_PRODUCT_REQUEST_VISIBLE",
            "BROWSER_SECURITY_CONTROLS_VERIFIED",
        ],
        "request_digest": request_digest,
        "screenshots": screenshot_claims,
        "redaction_contract": (
            "screenshots and manifest contain no passwords, bearer tokens, CSRF values, or salts"
        ),
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
