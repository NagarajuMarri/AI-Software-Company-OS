from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.local_uat import create_local_uat_application


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _available_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _start(root: Path):
    port = _available_port()
    origin = f"http://127.0.0.1:{port}"
    application = create_local_uat_application(root, origin)
    server = make_server(
        "127.0.0.1",
        port,
        application,
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, origin


def _stop(server, thread) -> None:
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_founder_runs_unified_local_uat_and_reopens_persisted_product(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    data_dir = tmp_path / "ascos-local-uat"
    server, thread, origin = _start(data_dir)
    uat_screenshot: bytes
    evidence_screenshot: bytes
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
        try:
            page.goto(origin, wait_until="networkidle")
            page.get_by_role(
                "heading",
                name="Test the ASCOS product journey in one browser application.",
            ).wait_for()
            assert page.get_by_text("Local UAT only — not production").is_visible()
            page.get_by_role("link", name="Create local account").click()

            page.get_by_label("Email address").fill("founder@example.com")
            page.get_by_label("Password", exact=True).fill("SecureFounder123")
            page.get_by_label("Confirm password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Create account").click()

            page.goto(f"{origin}/uat", wait_until="networkidle")
            page.get_by_role("heading", name="ASCOS V1 acceptance workspace").wait_for()
            assert page.get_by_text("Interactive now", exact=True).is_visible()
            assert page.get_by_text("Verified baseline", exact=True).is_visible()
            assert page.get_by_text("No automatic deployment", exact=True).is_visible()
            uat_screenshot = page.screenshot(full_page=True)

            page.get_by_role("link", name="Describe a product").click()
            page.get_by_label("Product name").fill("Founder UAT project hub")
            page.get_by_label("Product summary").fill(
                "Help a founder collect product ideas and turn them into governed plans."
            )
            page.get_by_label("Target users").fill("Startup founders and product teams")
            page.get_by_label("Required features one per line").fill(
                "Capture product ideas\nApprove product scope\nTrack delivery readiness"
            )
            page.get_by_label("Constraints optional, one per line").fill(
                "Local UAT must not deploy automatically"
            )
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Submit product request").click()

            page.get_by_role("link", name="Refine requirements").click()
            page.get_by_label("Primary user journey").fill(
                "A founder submits an idea, reviews the generated plan, and sees truthful delivery readiness."
            )
            page.get_by_label("Desired outcomes one per line").fill(
                "Scope is explicit\nApprovals are traceable"
            )
            page.get_by_label("Success metrics one measurable signal per line").fill(
                "Every approved requirement is traceable\nNo deployment occurs during local UAT"
            )
            page.get_by_label("Non-goals optional, one per line").fill(
                "No production release from the local launcher"
            )
            page.get_by_label("Data sensitivity").select_option("NO_PERSONAL_DATA")
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
            page.get_by_role("link", name="Refine acceptance criteria").click()
            page.locator('textarea[name="criteria__REQ-FEATURE-001"]').fill(
                "A founder can save a product idea with a title and summary.\n"
                "The saved idea appears once in the founder workspace."
            )
            page.locator('textarea[name="criteria__REQ-FEATURE-002"]').fill(
                "A founder can review and explicitly approve one exact scope digest.\n"
                "Approval is rejected when the rendered scope digest is stale."
            )
            page.locator('textarea[name="criteria__REQ-FEATURE-003"]').fill(
                "The workspace displays the current governed delivery-readiness state.\n"
                "The readiness view never reports execution or deployment before authority exists."
            )
            page.get_by_text(
                "I reviewed every feature criterion and lock this exact criteria baseline."
            ).click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Lock refined criteria").click()
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
            page.get_by_text(
                "I reviewed this exact roadmap and approve it as the immutable planning scope."
            ).click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Approve and lock roadmap").click()

            page.get_by_role("link", name="Create delivery estimate draft").click()
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Generate estimate draft").click()
            page.get_by_role("link", name="View project progress").click()
            page.get_by_role("heading", name="Founder UAT project hub — Project Progress").wait_for()
            assert page.get_by_text("Overall progress0%", exact=True).is_visible()
            assert page.get_by_text("No operational agents assigned").is_visible()

            page.get_by_role("link", name="Open preview and evidence centre").click()
            page.get_by_role("heading", name="Preview evidence is pending").wait_for()
            assert page.get_by_text("No preview creation or deployment authority").is_visible()
            evidence_screenshot = page.screenshot(full_page=True)

            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign out").click()
            page.get_by_label("Email address").fill("FOUNDER@EXAMPLE.COM")
            page.get_by_label("Password").fill("SecureFounder123")
            with page.expect_navigation(wait_until="networkidle"):
                page.get_by_role("button", name="Sign in").click()
            assert page.get_by_text("Founder UAT project hub", exact=True).is_visible()

            _stop(server, thread)
            server, thread, restarted_origin = _start(data_dir)
            page.goto(f"{restarted_origin}/customer", wait_until="networkidle")
            assert page.get_by_text("Founder UAT project hub", exact=True).is_visible()
            assert console_errors == []
            assert request_failures == []
        finally:
            _stop(server, thread)
            context.close()
            browser.close()

    target = os.environ.get("ASCOS_LOCAL_UAT_EVIDENCE_DIR")
    if target:
        _write_evidence(Path(target), uat_screenshot, evidence_screenshot)


def _write_evidence(target: Path, uat_screenshot: bytes, evidence_screenshot: bytes) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshots = {
        "unified-local-uat-status.png": uat_screenshot,
        "unified-local-uat-evidence-boundary.png": evidence_screenshot,
    }
    for name, content in screenshots.items():
        (target / name).write_bytes(content)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "ascos_v1.local_uat.complete_customer_planning_and_restart",
        "claims": [
            "ONE_LOCAL_BROWSER_APPLICATION",
            "REAL_SIGNUP_AND_SESSION",
            "REAL_PRODUCT_INTAKE_THROUGH_PROJECT_PROGRESS",
            "PERSISTED_STATE_SURVIVES_SERVER_RESTART",
            "PREVIEW_EVIDENCE_TRUTHFULLY_PENDING",
            "ZERO_PROVIDER_REPOSITORY_MERGE_DEPLOYMENT_RELEASE_OR_BILLING_EFFECT",
            "EMPTY_BROWSER_CONSOLE_AND_NETWORK_FAILURE_COLLECTIONS",
        ],
        "screenshots": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in screenshots.items()
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
