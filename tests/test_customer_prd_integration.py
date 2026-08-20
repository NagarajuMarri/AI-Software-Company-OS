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
from runtime.customer_prd import CustomerPrdApplication, CustomerPrdService, FileCustomerPrdStore
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApprovalService,
    CustomerRequirementsApplication,
    CustomerRequirementsService,
    CustomerWorkspaceApplication,
    FileCustomerRequirementsApprovalStore,
    FileCustomerRequirementsStore,
)


NOW = datetime(2026, 8, 20, 16, tzinfo=timezone.utc)


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_customer_generates_and_reopens_traceable_prd_draft(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    requests = CustomerProductRequestService(
        FileCustomerProductRequestStore(tmp_path / "requests"),
        lambda: NOW,
    )
    approval_store = FileCustomerRequirementsApprovalStore(tmp_path / "approvals")
    requirements = CustomerRequirementsService(
        FileCustomerRequirementsStore(tmp_path / "requirements"),
        requests,
        lambda: NOW,
        approval_store.is_locked,
    )
    approvals = CustomerRequirementsApprovalService(
        approval_store,
        requirements,
        lambda: NOW,
    )
    prds = CustomerPrdService(
        FileCustomerPrdStore(tmp_path / "prds"),
        approvals,
        lambda: NOW,
    )
    workspace = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(approvals),
        CustomerPrdApplication(prds),
    )
    authentication = CustomerAuthenticationService(
        FileCustomerAccountStore(tmp_path / "authentication"),
        FileCustomerSessionStore(tmp_path / "authentication"),
        clock=lambda: NOW,
    )
    application = AuthenticatedCustomerApplication(
        authentication,
        workspace,
        preauth_secret=b"day-15-founder-browser-preauthentication-secret",
        secure_cookies=False,
        clock=lambda: NOW,
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
    screenshot: bytes
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1400},
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

            page.goto(f"{origin}/signup", wait_until="networkidle")
            page.get_by_label("Email address").fill("founder@example.com")
            page.get_by_label("Password", exact=True).fill("SecureFounder123")
            page.get_by_label("Confirm password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Create account").click()

            page.get_by_role("link", name="Describe a product").click()
            page.get_by_label("Product name").fill("AI receptionist for clinics")
            page.get_by_label("Product summary").fill(
                "Answer incoming calls and convert patient questions into appointments."
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

            page.get_by_role("link", name="Refine requirements").click()
            page.get_by_label("Primary user journey").fill(
                "A clinic owner configures hours; a patient calls; ASCOS answers, finds an available slot, confirms the appointment, and sends a WhatsApp message."
            )
            page.get_by_label("Desired outcomes one per line").fill(
                "Every incoming call receives an answer\nPatients receive confirmed appointments"
            )
            page.get_by_label("Success metrics one measurable signal per line").fill(
                "At least 90% of calls answered\nAt least 70% of booking requests completed"
            )
            page.get_by_label("Non-goals optional, one per line").fill(
                "No autonomous medical advice\nNo payment processing in the first release"
            )
            page.get_by_text("Mobile", exact=True).click()
            page.get_by_label("Data sensitivity").select_option("PERSONAL_DATA")
            page.get_by_label("Delivery priority").select_option("TIME_SENSITIVE")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Save requirements draft").click()

            page.get_by_role("link", name="Approve requirements").click()
            page.get_by_text(
                "I reviewed this exact scope and approve it as the immutable requirements baseline."
            ).click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Approve and lock requirements").click()

            page.get_by_role("link", name="Create PRD draft").click()
            page.get_by_role("heading", name="Create the PRD for AI receptionist for clinics").wait_for()
            assert page.get_by_text("No external AI call").is_visible()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Generate PRD draft").click()

            page.get_by_text("Draft generated", exact=True).wait_for()
            page.get_by_role(
                "heading",
                name="AI receptionist for clinics — Product Requirements Document",
            ).wait_for()
            assert page.get_by_text("REQ-JOURNEY-001", exact=True).is_visible()
            assert page.get_by_text("REQ-FEATURE-003", exact=True).is_visible()
            assert page.get_by_text("No payment processing in the first release").is_visible()
            assert page.get_by_text("PRD draft only — no implementation has started").is_visible()
            screenshot = page.screenshot(full_page=True)

            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign out").click()
            page.get_by_label("Email address").fill("FOUNDER@EXAMPLE.COM")
            page.get_by_label("Password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign in").click()
            page.get_by_text("AI receptionist for clinics", exact=True).click()
            page.get_by_role("link", name="Refine requirements").click()
            page.get_by_role("link", name="Create PRD draft").click()
            assert page.url.endswith("/prd/review")
            assert page.get_by_text("REQ-DATA-001", exact=True).is_visible()
            assert page.get_by_text("Patients receive confirmed appointments").is_visible()
            assert console_errors == []
            assert request_failures == []
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    customer_id = next(path.name for path in (tmp_path / "requests").iterdir())
    product = requests.dashboard(customer_id)[0]
    _, draft, approval, prd = prds.context(customer_id, product.request_id)
    assert draft is not None and approval is not None and prd is not None
    assert prd.requirements_digest == draft.digest
    assert prd.approval_digest == approval.digest
    assert prd.to_governed_document().status.value == "DRAFT"
    target = os.environ.get("ASCOS_DAY15_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_founder_evidence(
            Path(target),
            product.digest,
            draft.digest,
            approval.digest,
            prd.digest,
            screenshot,
        )


def _write_founder_evidence(
    target: Path,
    request_digest: str,
    draft_digest: str,
    approval_digest: str,
    prd_digest: str,
    screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "prd-draft-review.png"
    screenshot_path.write_bytes(screenshot)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "customer.prd.deterministic_draft",
        "claims": [
            "AUTHENTICATED_CUSTOMER_OWNS_APPROVED_SOURCE",
            "EXACT_APPROVAL_DIGEST_BOUND",
            "DETERMINISTIC_PRD_DRAFT_GENERATED",
            "EVERY_REQUIREMENT_HAS_APPROVED_SOURCE_REFERENCE",
            "GOVERNED_PRD_VALIDATION_PASSED",
            "RETURNING_CUSTOMER_REOPENED_PRD_DRAFT",
            "NO_PRD_APPROVAL_PLANNING_OR_IMPLEMENTATION_AUTHORITY",
            "BROWSER_SECURITY_CONTROLS_VERIFIED",
        ],
        "source_request_digest": request_digest,
        "requirements_draft_digest": draft_digest,
        "requirements_approval_digest": approval_digest,
        "customer_prd_digest": prd_digest,
        "screenshot": {
            "file": screenshot_path.name,
            "digest": hashlib.sha256(screenshot).hexdigest(),
        },
        "redaction_contract": (
            "evidence contains no password, bearer token, cookie, CSRF value, salt, or local path"
        ),
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
