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
from runtime.customer_prd import (
    CustomerPrdApplication,
    CustomerPrdApprovalApplication,
    CustomerPrdApprovalService,
    CustomerPrdService,
    FileCustomerPrdApprovalStore,
    FileCustomerPrdStore,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApprovalService,
    CustomerRequirementsApplication,
    CustomerRequirementsService,
    CustomerWorkspaceApplication,
    FileCustomerRequirementsApprovalStore,
    FileCustomerRequirementsStore,
)
from runtime.customer_roadmap import (
    CustomerRoadmapApplication,
    CustomerRoadmapApprovalApplication,
    CustomerRoadmapApprovalService,
    CustomerRoadmapService,
    FileCustomerRoadmapApprovalStore,
    FileCustomerRoadmapStore,
)


NOW = datetime(2026, 8, 20, 19, tzinfo=timezone.utc)


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_customer_approves_locks_and_reopens_exact_roadmap(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    requests = CustomerProductRequestService(
        FileCustomerProductRequestStore(tmp_path / "requests"),
        lambda: NOW,
    )
    requirements_approval_store = FileCustomerRequirementsApprovalStore(
        tmp_path / "requirements-approvals"
    )
    requirements = CustomerRequirementsService(
        FileCustomerRequirementsStore(tmp_path / "requirements"),
        requests,
        lambda: NOW,
        requirements_approval_store.is_locked,
    )
    requirements_approvals = CustomerRequirementsApprovalService(
        requirements_approval_store,
        requirements,
        lambda: NOW,
    )
    prds = CustomerPrdService(
        FileCustomerPrdStore(tmp_path / "prds"),
        requirements_approvals,
        lambda: NOW,
    )
    prd_approvals = CustomerPrdApprovalService(
        FileCustomerPrdApprovalStore(tmp_path / "prd-approvals"),
        prds,
        lambda: NOW,
    )
    roadmaps = CustomerRoadmapService(
        FileCustomerRoadmapStore(tmp_path / "roadmaps"),
        prd_approvals,
        lambda: NOW,
    )
    roadmap_approvals = CustomerRoadmapApprovalService(
        FileCustomerRoadmapApprovalStore(tmp_path / "roadmap-approvals"),
        roadmaps,
        lambda: NOW,
    )
    workspace = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(requirements_approvals),
        CustomerPrdApplication(prds, prd_approvals),
        CustomerPrdApprovalApplication(prd_approvals),
        CustomerRoadmapApplication(roadmaps, roadmap_approvals),
        CustomerRoadmapApprovalApplication(roadmap_approvals),
    )
    authentication = CustomerAuthenticationService(
        FileCustomerAccountStore(tmp_path / "authentication"),
        FileCustomerSessionStore(tmp_path / "authentication"),
        clock=lambda: NOW,
    )
    application = AuthenticatedCustomerApplication(
        authentication,
        workspace,
        preauth_secret=b"day-18-founder-browser-preauthentication-secret",
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
            page.get_by_label("Product name").fill("Community workshop planner")
            page.get_by_label("Product summary").fill(
                "Help local groups schedule and coordinate educational workshops."
            )
            page.get_by_label("Target users").fill(
                "Community organisers and workshop participants"
            )
            page.get_by_label("Required features one per line").fill(
                "Publish workshops\nManage registrations\nSend schedule reminders"
            )
            page.get_by_label("Constraints optional, one per line").fill(
                "No payment processing in the first release"
            )
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Submit product request").click()

            page.get_by_role("link", name="Refine requirements").click()
            page.get_by_label("Primary user journey").fill(
                "An organiser publishes a workshop, participants reserve available places, and everyone receives the final schedule."
            )
            page.get_by_label("Desired outcomes one per line").fill(
                "Workshops are visible\nRegistrations are confirmed"
            )
            page.get_by_label("Success metrics one measurable signal per line").fill(
                "At least 80% of registrations are confirmed\nEvery schedule update is visible"
            )
            page.get_by_label("Non-goals optional, one per line").fill(
                "No payment processing in the first release"
            )
            page.get_by_label("Data sensitivity").select_option("PERSONAL_DATA")
            page.get_by_label("Delivery priority").select_option("STANDARD")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Save requirements draft").click()

            page.get_by_role("link", name="Approve requirements").click()
            page.get_by_text(
                "I reviewed this exact scope and approve it as the immutable requirements baseline."
            ).click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Approve and lock requirements").click()

            page.get_by_role("link", name="Create PRD draft").click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Generate PRD draft").click()
            page.get_by_role("link", name="Review and approve PRD").click()
            page.get_by_text(
                "I reviewed this exact PRD and approve it as the immutable product scope."
            ).click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Approve and lock PRD").click()

            page.get_by_role("link", name="Create roadmap draft").click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Generate roadmap draft").click()
            page.get_by_role("link", name="Review and approve roadmap").click()
            page.get_by_role(
                "heading", name="Approve and lock Community workshop planner"
            ).wait_for()
            assert page.get_by_text("REQ-JOURNEY-001", exact=True).is_visible()
            assert page.get_by_text("This action permanently locks this exact roadmap").is_visible()
            page.get_by_text(
                "I reviewed this exact roadmap and approve it as the immutable planning scope."
            ).click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Approve and lock roadmap").click()

            page.get_by_text("Approved and locked", exact=True).wait_for()
            assert page.get_by_text("LOCKED", exact=True).first.is_visible()
            assert page.get_by_text("Customer MVP", exact=True).is_visible()
            assert page.get_by_text("REQ-DATA-001", exact=True).is_visible()
            assert page.get_by_text(
                "Locked planning scope — implementation has not started"
            ).is_visible()
            screenshot = page.screenshot(full_page=True)

            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign out").click()
            page.get_by_label("Email address").fill("FOUNDER@EXAMPLE.COM")
            page.get_by_label("Password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign in").click()
            page.get_by_text("Community workshop planner", exact=True).click()
            page.get_by_role("link", name="Refine requirements").click()
            page.get_by_role("link", name="Create PRD draft").click()
            page.wait_for_url("**/prd/approved")
            page.get_by_role("link", name="Create roadmap draft").click()
            page.wait_for_url("**/roadmap/approved")
            assert page.get_by_text("Approved and locked", exact=True).is_visible()
            assert page.get_by_text("REQ-FEATURE-003", exact=True).is_visible()
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
    _, prd, prd_approval, roadmap, receipt = roadmap_approvals.context(
        customer_id,
        product.request_id,
    )
    assert prd is not None and prd_approval is not None and roadmap is not None
    assert receipt is not None
    locked = roadmap_approvals.governed_roadmap(customer_id, product.request_id)
    assert locked.status == "LOCKED"
    assert locked.source_roadmap_digest == roadmap.digest
    assert locked.requirement_ids == roadmap.requirement_ids
    assert all(item.status == "LOCKED" for item in locked.milestones)

    target = os.environ.get("ASCOS_DAY18_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_founder_evidence(
            Path(target),
            product.digest,
            prd.requirements_digest,
            prd.approval_digest,
            prd.digest,
            prd_approval.digest,
            roadmap.digest,
            receipt.digest,
            len(locked.milestones),
            len(locked.requirement_ids),
            screenshot,
        )


def _write_founder_evidence(
    target: Path,
    request_digest: str,
    requirements_digest: str,
    requirements_approval_digest: str,
    prd_digest: str,
    prd_approval_digest: str,
    roadmap_digest: str,
    roadmap_approval_digest: str,
    milestone_count: int,
    requirement_count: int,
    screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "roadmap-approved-and-locked.png"
    screenshot_path.write_bytes(screenshot)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "customer.roadmap.approve_lock_and_reopen",
        "claims": [
            "AUTHENTICATED_CUSTOMER_OWNS_EXACT_ROADMAP",
            "EXPLICIT_FIXED_CONFIRMATION_REQUIRED",
            "EXACT_ROADMAP_DIGEST_BOUND",
            "ROADMAP_APPROVAL_RECEIPT_WRITE_ONCE",
            "GOVERNED_ROADMAP_STATUS_LOCKED",
            "EVERY_GOVERNED_ITEM_STATUS_LOCKED",
            "EXACT_REQUIREMENT_MAPPING_PRESERVED",
            "RETURNING_CUSTOMER_REOPENED_SAME_LOCKED_ROADMAP",
            "NO_ESTIMATE_SCHEDULE_AGENT_REPOSITORY_TASK_OR_IMPLEMENTATION_AUTHORITY",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
            "BROWSER_SECURITY_CONTROLS_VERIFIED",
        ],
        "source_request_digest": request_digest,
        "requirements_digest": requirements_digest,
        "requirements_approval_digest": requirements_approval_digest,
        "customer_prd_digest": prd_digest,
        "customer_prd_approval_digest": prd_approval_digest,
        "customer_roadmap_digest": roadmap_digest,
        "customer_roadmap_approval_digest": roadmap_approval_digest,
        "milestone_count": milestone_count,
        "mapped_requirement_count": requirement_count,
        "roadmap_status": "LOCKED",
        "roadmap_item_status": "LOCKED",
        "screenshot": {
            "file": screenshot_path.name,
            "digest": hashlib.sha256(screenshot).hexdigest(),
        },
        "fixture_contract": (
            "Community workshop planner is browser test data only; no ASCOS pilot is selected"
        ),
        "redaction_contract": (
            "evidence contains no password, bearer token, cookie, CSRF value, salt, or local path"
        ),
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
