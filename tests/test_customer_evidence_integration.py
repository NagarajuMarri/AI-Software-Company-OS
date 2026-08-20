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
from runtime.customer_evidence import (
    CustomerPreviewEvidenceApplication,
    CustomerPreviewEvidenceService,
    FileCustomerPreviewEvidenceStore,
)
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
from tests.test_customer_evidence import _artifacts


NOW = datetime(2026, 8, 20, 22, tzinfo=timezone.utc)


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _preview(_environ, start_response):
    content = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS browser verification fixture</title><style>
body{font-family:system-ui;background:#eef2ff;color:#18213d;margin:0;padding:8vw}
main{max-width:760px;background:white;padding:48px;border-radius:24px;box-shadow:0 20px 60px #26387622}
span{color:#5367c8;font-weight:800;text-transform:uppercase;letter-spacing:.12em}
h1{font-size:42px;margin:14px 0}p{font-size:20px;line-height:1.6}
</style></head><body><main><span>Browser verification fixture</span>
<h1>Fixture product preview</h1>
<p>This page verifies the governed ASCOS preview-opening journey.</p>
<p><strong>Browser verification only — not an official pilot product.</strong></p>
</main></body></html>""".encode()
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(content))),
            ("Cache-Control", "no-store"),
            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
        ],
    )
    return [content]


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_customer_opens_evidence_accepts_and_reopens_exact_receipt(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    preview_server = make_server(
        "127.0.0.1",
        0,
        _preview,
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    preview_thread = threading.Thread(target=preview_server.serve_forever, daemon=True)
    preview_thread.start()
    preview_origin = f"http://127.0.0.1:{preview_server.server_port}"

    values = _services(tmp_path)
    _generate(values[18], values[16])
    progress = CustomerProjectProgressService(values[18])
    evidence = CustomerPreviewEvidenceService(
        FileCustomerPreviewEvidenceStore(tmp_path / "customer-evidence"),
        progress,
        (preview_origin,),
        lambda: NOW,
    )
    commit_sha = (
        os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or "d" * 40
    )
    package = evidence.publish(
        customer_id="customer-1",
        request_id="req-1",
        preview_label="Community workshop planner — verification preview",
        preview_url=f"{preview_origin}/fixture-product",
        commit_sha=commit_sha,
        evidence=_artifacts(commit_sha=commit_sha),
    )
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
        CustomerPreviewEvidenceApplication(evidence),
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
        salt_factory=lambda: b"day-21-fixedsalt",
    )
    authentication.register("founder@example.com", "SecureFounder123")
    application = AuthenticatedCustomerApplication(
        authentication,
        workspace,
        preauth_secret=b"day-21-founder-browser-preauthentication-secret",
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
    centre_screenshot: bytes
    preview_screenshot: bytes
    receipt_screenshot: bytes
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1700},
                locale="en-US",
                timezone_id="UTC",
            )
            page = context.new_page()
            console_errors: list[str] = []
            request_failures: list[str] = []

            def observe(observed_page):
                observed_page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                observed_page.on(
                    "pageerror",
                    lambda error: console_errors.append(str(error)),
                )
                observed_page.on(
                    "requestfailed",
                    lambda request: request_failures.append(request.url),
                )

            observe(page)
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
            page.get_by_role("link", name="View project progress").click()
            page.get_by_role("link", name="Open preview and evidence centre").click()

            page.get_by_role(
                "heading",
                name="Community workshop planner — verification preview",
            ).wait_for()
            assert page.get_by_text("Exact commit", exact=True).is_visible()
            assert page.get_by_text("Evidence passed", exact=True).is_visible()
            assert page.get_by_text("Evidence passed6/6", exact=True).is_visible()
            assert page.get_by_text(commit_sha, exact=True).is_visible()
            assert page.get_by_text(package.digest, exact=True).is_visible()
            assert page.get_by_role("heading", name="Test and security evidence").is_visible()
            assert page.get_by_text("Automated Test", exact=True).is_visible()
            assert page.get_by_text("Browser Console", exact=True).is_visible()
            assert page.get_by_text("Browser Network", exact=True).is_visible()
            assert page.get_by_text("Screenshot", exact=True).is_visible()
            assert page.get_by_text("Security", exact=True).is_visible()
            assert page.get_by_text("ACCEPT", exact=True).is_visible()
            assert page.get_by_text("REVISE", exact=True).is_visible()
            assert page.get_by_text(
                "Customer decision only — no delivery side effect"
            ).is_visible()
            centre_screenshot = page.screenshot(full_page=True)

            with page.expect_popup() as popup_info:
                page.get_by_role("link", name="Open product preview").click()
            preview_page = popup_info.value
            observe(preview_page)
            preview_page.wait_for_load_state("networkidle")
            assert preview_page.url == f"{preview_origin}/fixture-product"
            assert preview_page.get_by_role(
                "heading",
                name="Fixture product preview",
            ).is_visible()
            assert preview_page.get_by_text(
                "Browser verification only — not an official pilot product."
            ).is_visible()
            preview_screenshot = preview_page.screenshot(full_page=True)
            preview_page.close()

            page.get_by_label("ACCEPT", exact=True).check()
            page.get_by_label("Review comments").fill(
                "Exact preview and all governed evidence reviewed."
            )
            page.get_by_text(
                "I opened the preview and reviewed this exact evidence package."
            ).click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Submit customer decision").click()

            page.get_by_role("heading", name="Immutable customer decision").wait_for()
            assert page.get_by_text("ACCEPT", exact=True).is_visible()
            assert page.get_by_text(
                "Exact preview and all governed evidence reviewed."
            ).is_visible()
            assert page.get_by_text("Customer review required", exact=True).count() == 0
            receipt = evidence.context("customer-1", "req-1")[2]
            assert receipt is not None
            assert page.get_by_text(receipt.review_id, exact=True).is_visible()
            assert page.get_by_text(receipt.digest, exact=True).is_visible()
            receipt_screenshot = page.screenshot(full_page=True)

            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign out").click()
            page.get_by_label("Email address").fill("FOUNDER@EXAMPLE.COM")
            page.get_by_label("Password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign in").click()
            page.goto(
                f"{origin}/customer/requests/req-1/evidence",
                wait_until="networkidle",
            )
            assert page.get_by_text(receipt.review_id, exact=True).is_visible()
            assert page.get_by_text(receipt.digest, exact=True).is_visible()
            assert page.get_by_text(package.digest, exact=True).is_visible()
            assert console_errors == []
            assert request_failures == []
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        preview_server.shutdown()
        preview_thread.join(timeout=5)
        preview_server.server_close()

    snapshot, reopened, review = evidence.context("customer-1", "req-1")
    assert reopened == package
    assert review is not None and review.decision == "ACCEPT"
    assert review.package_digest == package.digest
    assert review.progress_digest == snapshot.digest
    assert snapshot.progress_percentage == 0
    assert snapshot.assigned_agent_ids == ()

    target = os.environ.get("ASCOS_DAY21_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_founder_evidence(
            Path(target),
            snapshot,
            package,
            review,
            centre_screenshot,
            preview_screenshot,
            receipt_screenshot,
        )


def _write_founder_evidence(
    target: Path,
    snapshot,
    package,
    review,
    centre_screenshot: bytes,
    preview_screenshot: bytes,
    receipt_screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshots = {
        "preview-evidence-centre.png": centre_screenshot,
        "fixture-preview-opened.png": preview_screenshot,
        "customer-accept-receipt.png": receipt_screenshot,
    }
    for name, content in screenshots.items():
        (target / name).write_bytes(content)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "customer.preview_evidence.open_accept_reopen",
        "claims": [
            "AUTHENTICATED_CUSTOMER_OWNS_EXACT_EVIDENCE",
            "EXACT_PROGRESS_ROADMAP_ESTIMATE_AND_COMMIT_BOUND",
            "ALLOWLISTED_PRODUCT_PREVIEW_OPENED",
            "REQUIRED_TEST_BROWSER_SCREENSHOT_AND_SECURITY_EVIDENCE_INSPECTED",
            "ACCEPT_REVISE_GATE_VISIBLE",
            "EXACT_ACCEPT_DECISION_RECORDED",
            "RETURNING_CUSTOMER_REOPENED_SAME_RECEIPT",
            "NO_AGENT_TASK_REPOSITORY_WRITE_MERGE_DEPLOYMENT_RELEASE_OR_DAY22_AUTHORITY",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
            "BROWSER_SECURITY_CONTROLS_VERIFIED",
        ],
        "commit_sha": package.commit_sha,
        "customer_progress_digest": snapshot.digest,
        "customer_roadmap_digest": snapshot.roadmap_digest,
        "customer_estimate_digest": snapshot.estimate_digest,
        "evidence_package_id": package.package_id,
        "evidence_package_digest": package.digest,
        "required_evidence_count": len(package.evidence),
        "required_evidence_passed": package.all_required_evidence_passed,
        "customer_review_id": review.review_id,
        "customer_review_digest": review.digest,
        "customer_decision": review.decision,
        "progress_percentage_after_review": snapshot.progress_percentage,
        "assigned_agent_count_after_review": len(snapshot.assigned_agent_ids),
        "screenshots": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in screenshots.items()
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
