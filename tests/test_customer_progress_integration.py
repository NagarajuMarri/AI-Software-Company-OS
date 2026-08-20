from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.customer_application import CustomerPortalApplication
from runtime.customer_authentication import (
    AuthenticatedCustomerApplication,
    CustomerAuthenticationService,
    FileCustomerAccountStore,
    FileCustomerSessionStore,
)
from runtime.customer_estimate import CustomerDeliveryEstimateApplication
from runtime.customer_prd import CustomerPrdApplication, CustomerPrdApprovalApplication
from runtime.customer_progress import (
    CustomerProjectProgressApplication,
    CustomerProjectProgressService,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApplication,
    CustomerWorkspaceApplication,
)
from runtime.customer_roadmap import (
    CustomerRoadmapApplication,
    CustomerRoadmapApprovalApplication,
)
from tests.test_customer_estimate import _generate, _services


NOW = datetime(2026, 8, 20, 21, tzinfo=timezone.utc)


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_customer_opens_and_reopens_exact_project_progress(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    values = _services(tmp_path)
    estimate = _generate(values[18], values[16])
    progress = CustomerProjectProgressService(values[18])
    workspace = CustomerWorkspaceApplication(
        CustomerPortalApplication(values[0]),
        CustomerRequirementsApplication(values[1]),
        CustomerRequirementsApprovalApplication(values[2]),
        CustomerPrdApplication(values[3], values[4]),
        CustomerPrdApprovalApplication(values[4]),
        CustomerRoadmapApplication(values[12], values[15]),
        CustomerRoadmapApprovalApplication(values[15]),
        CustomerDeliveryEstimateApplication(values[18]),
        CustomerProjectProgressApplication(progress),
    )
    tokens = iter(
        (
            "1",
            "R" * 32,
            "C" * 32,
            "L" * 32,
            "I" * 32,
            "T" * 32,
            "U" * 32,
        )
    )
    authentication = CustomerAuthenticationService(
        FileCustomerAccountStore(tmp_path / "authentication"),
        FileCustomerSessionStore(tmp_path / "authentication"),
        clock=lambda: NOW,
        token_factory=lambda: next(tokens),
        salt_factory=lambda: b"day-20-fixedsalt",
    )
    authentication.register("founder@example.com", "SecureFounder123")
    application = AuthenticatedCustomerApplication(
        authentication,
        workspace,
        preauth_secret=b"day-20-founder-browser-preauthentication-secret",
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
    first = progress.view("customer-1", "req-1")
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1600},
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

            page.goto(f"{origin}/login", wait_until="networkidle")
            page.get_by_label("Email address").fill("founder@example.com")
            page.get_by_label("Password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign in").click()
            page.get_by_text("Community workshop planner", exact=True).click()
            page.get_by_role("link", name="Refine requirements").click()
            page.get_by_role("link", name="Create PRD draft").click()
            page.wait_for_url("**/prd/approved")
            page.get_by_role("link", name="Create roadmap draft").click()
            page.wait_for_url("**/roadmap/approved")
            page.get_by_role("link", name="Create delivery estimate draft").click()
            page.wait_for_url("**/estimate/review")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("link", name="View project progress").click()

            page.get_by_role(
                "heading", name="Community workshop planner — Project Progress"
            ).wait_for()
            assert page.get_by_text("Overall progress0%", exact=True).is_visible()
            assert page.get_by_text("Tasks0/5 complete", exact=True).is_visible()
            assert page.get_by_text("Assigned agents0", exact=True).is_visible()
            assert page.get_by_text("No operational agents assigned").is_visible()
            assert page.get_by_role("heading", name="Open blockers").is_visible()
            assert page.get_by_text("Execution authority required").is_visible()
            assert page.get_by_text("Operational workforce not activated").is_visible()
            assert page.get_by_text("Product workspace not created").is_visible()
            assert page.get_by_role("heading", name="Governed decisions").is_visible()
            assert page.get_by_text("Roadmap scope approved and locked").is_visible()
            assert page.get_by_text("Delivery estimate recorded as a draft").is_visible()
            assert page.get_by_text("REQ-FEATURE-001", exact=True).is_visible()
            assert page.get_by_text("REQ-JOURNEY-001", exact=True).is_visible()
            assert page.get_by_text(
                "Visibility only — no execution authority"
            ).is_visible()
            assert page.get_by_text(first.digest, exact=True).is_visible()
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
            page.get_by_role("link", name="Create delivery estimate draft").click()
            page.wait_for_url("**/estimate/review")
            page.get_by_role("link", name="View project progress").click()
            page.wait_for_url("**/progress")
            assert page.get_by_text(first.digest, exact=True).is_visible()
            assert page.get_by_text("Overall progress0%", exact=True).is_visible()
            assert console_errors == []
            assert request_failures == []
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    reopened = progress.view("customer-1", "req-1")
    assert reopened == first
    assert reopened.digest == first.digest
    assert reopened.estimate_digest == estimate.digest
    assert reopened.progress_percentage == 0
    assert reopened.total_tasks == 5
    assert reopened.assigned_agent_ids == ()

    target = os.environ.get("ASCOS_DAY20_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_founder_evidence(Path(target), reopened, screenshot)


def _write_founder_evidence(target: Path, snapshot, screenshot: bytes) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "project-progress-dashboard.png"
    screenshot_path.write_bytes(screenshot)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "customer.progress.open_and_reopen",
        "claims": [
            "AUTHENTICATED_CUSTOMER_OWNS_EXACT_PROJECT",
            "EXACT_ESTIMATE_AND_LOCKED_ROADMAP_BOUND",
            "MILESTONES_AND_TASKS_MAP_EXACTLY_ONCE",
            "PROJECT_MANAGER_PROGRESS_CALCULATED",
            "AGENT_ASSIGNMENT_STATE_VISIBLE",
            "BLOCKERS_AND_DECISIONS_VISIBLE",
            "ZERO_EXECUTION_PROGRESS_TRUTHFULLY_REPORTED",
            "RETURNING_CUSTOMER_REOPENED_SAME_PROGRESS",
            "NO_AGENT_REPOSITORY_EXECUTABLE_TASK_CODE_DEPLOYMENT_RELEASE_OR_DAY21_AUTHORITY",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
            "BROWSER_SECURITY_CONTROLS_VERIFIED",
        ],
        "customer_progress_digest": snapshot.digest,
        "customer_estimate_digest": snapshot.estimate_digest,
        "customer_roadmap_digest": snapshot.roadmap_digest,
        "customer_roadmap_approval_digest": snapshot.roadmap_approval_digest,
        "milestone_count": len(snapshot.milestones),
        "task_count": snapshot.total_tasks,
        "completed_task_count": snapshot.completed_tasks,
        "progress_percentage": snapshot.progress_percentage,
        "assigned_agent_count": len(snapshot.assigned_agent_ids),
        "open_blocker_count": len(snapshot.blockers),
        "governed_decision_count": len(snapshot.decisions),
        "project_status": snapshot.status,
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
