from __future__ import annotations

from datetime import timedelta
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.digital_twin import DigitalTwinExecutionStatus
from tests.test_digital_twin_runtime import (
    NOW,
    _assignment,
    _authority,
    _definition,
    _runtime,
)


APPROVED_DAY21_HEAD = "22e3a4bc4de50292b7953b1bcef492ae48b8a2a2"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _report(receipt, role: str, allowed_actions: tuple[str, ...]):
    tool = receipt.tool_calls[0]
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 22 Digital Twin verification</title>
<style>
:root{{--ink:#102038;--muted:#5c6c80;--line:#d9e2ec;--ok:#13795b;--wash:#f3f7fb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);
font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1060px;margin:0 auto;padding:64px 32px}}
.eyebrow{{color:#3557b7;font-weight:800;letter-spacing:.12em;text-transform:uppercase}}
h1{{font-size:48px;line-height:1.05;margin:12px 0 16px}}.lead{{font-size:20px;color:var(--muted)}}
.status{{display:inline-flex;gap:10px;align-items:center;background:#e7f8f1;color:var(--ok);
font-weight:800;border-radius:999px;padding:10px 16px}}.grid{{display:grid;grid-template-columns:1fr 1fr;
gap:20px;margin:32px 0}}section{{background:white;border:1px solid var(--line);border-radius:18px;
padding:24px}}h2{{font-size:18px;margin:0 0 16px}}dl{{display:grid;grid-template-columns:170px 1fr;
gap:12px;margin:0}}dt{{color:var(--muted)}}dd{{margin:0;font-weight:650;overflow-wrap:anywhere}}
code{{font-size:12px}}ul{{line-height:1.7;padding-left:20px}}.wide{{grid-column:1/-1}}
.boundary{{border-left:5px solid #3557b7}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}
.wide{{grid-column:auto}}h1{{font-size:38px}}dl{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS runtime evidence · Day 22</div>
<h1>Digital Twin runtime verification</h1>
<p class="lead">One provider-neutral Digital Twin completed one bounded verification assignment.</p>
<div class="status">● {escape(receipt.status.value)}</div>
<div class="grid">
<section><h2>Bounded identity</h2><dl>
<dt>Digital Twin</dt><dd>{escape(receipt.twin_id)}</dd>
<dt>Business Role</dt><dd>{escape(role)}</dd>
<dt>Provider</dt><dd>{escape(receipt.provider_id)}</dd>
<dt>Assignment</dt><dd>{escape(receipt.assignment_id)}</dd>
</dl></section>
<section><h2>Minimum tool access</h2><dl>
<dt>Allowed tool</dt><dd>{escape(tool.tool_id)}</dd>
<dt>Tool calls</dt><dd>{len(receipt.tool_calls)} of 2</dd>
<dt>Outcome</dt><dd>{escape(tool.outcome.value)}</dd>
<dt>Request digest</dt><dd><code>{escape(tool.request_digest)}</code></dd>
</dl></section>
<section class="wide"><h2>Exact authority chain</h2><dl>
<dt>Authority digest</dt><dd><code>{escape(receipt.authority_digest)}</code></dd>
<dt>Assignment digest</dt><dd><code>{escape(receipt.assignment_digest)}</code></dd>
<dt>Provider request</dt><dd><code>{escape(receipt.request_digest)}</code></dd>
<dt>Execution receipt</dt><dd><code>{escape(receipt.digest)}</code></dd>
</dl></section>
<section class="wide boundary"><h2>Authority boundary</h2>
<p>Allowed actions: {escape(', '.join(allowed_actions))}</p>
<ul><li>Read-only fixture record access only</li>
<li>No product repository, command, network, merge, deployment, release, billing, or approval authority</li>
<li>No specialized CEO, Product Manager, architect, engineering, QA, security, DevOps, or documentation behavior</li>
<li>No official pilot product selected</li></ul></section>
</div></main></body></html>""".encode("utf-8")

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day22-runtime-evidence":
            body = b"not found"
            start_response("404 Not Found", [("Content-Length", str(len(body)))])
            return [body]
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(content))),
                ("Cache-Control", "no-store"),
                ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"),
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "DENY"),
                ("Referrer-Policy", "no-referrer"),
            ],
        )
        return [content]

    return application


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_chromium_inspects_exact_digital_twin_execution_receipt(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    authority = _authority()
    assignment = _assignment(authority)
    twin = _definition()
    runtime, provider = _runtime(tmp_path)
    receipt = runtime.execute(
        execution_id="execution-day22-browser",
        twin=twin,
        assignment=assignment,
        authority=authority,
    )
    assert receipt.status is DigitalTwinExecutionStatus.SUCCEEDED
    assert provider.execution_count == 1

    restarted, restarted_provider = _runtime(
        tmp_path,
        clock=lambda: NOW + timedelta(minutes=3),
    )
    reopened = restarted.execute(
        execution_id="execution-day22-browser",
        twin=twin,
        assignment=assignment,
        authority=authority,
    )
    assert reopened == receipt
    assert restarted_provider.execution_count == 0

    server = make_server(
        "127.0.0.1",
        0,
        _report(receipt, assignment.business_role.value, authority.allowed_action_ids),
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    screenshot: bytes
    console_errors: list[str] = []
    request_failures: list[str] = []
    try:
        with playwright.sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1500},
                locale="en-US",
                timezone_id="UTC",
            )
            page = context.new_page()
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: request_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day22-runtime-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            page.get_by_role("heading", name="Digital Twin runtime verification").wait_for()
            assert page.get_by_text("SUCCEEDED", exact=True).is_visible()
            assert page.get_by_text("QA_ENGINEER", exact=True).is_visible()
            assert page.get_by_text("deterministic-day22", exact=True).is_visible()
            assert page.get_by_text("fixture.record.lookup", exact=True).is_visible()
            assert page.get_by_text("1 of 2", exact=True).is_visible()
            assert page.get_by_text(receipt.authority_digest, exact=True).is_visible()
            assert page.get_by_text(receipt.assignment_digest, exact=True).is_visible()
            assert page.get_by_text(receipt.request_digest, exact=True).is_visible()
            assert page.get_by_text(receipt.digest, exact=True).is_visible()
            assert page.get_by_text("No official pilot product selected", exact=True).is_visible()
            assert console_errors == []
            assert request_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY22_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_founder_evidence(
            Path(target),
            receipt,
            assignment.business_role.value,
            authority.allowed_action_ids,
            authority.max_tool_calls,
            screenshot,
        )


def _write_founder_evidence(
    target: Path,
    receipt,
    role: str,
    allowed_actions: tuple[str, ...],
    max_tool_calls: int,
    screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "digital-twin-runtime-verification.png"
    (target / screenshot_name).write_bytes(screenshot)
    commit_sha = (
        os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or "d" * 40
    ).lower()
    assert re.fullmatch(r"[0-9a-f]{40}", commit_sha)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "digital_twin.execute_reopen_inspect_receipt",
        "claims": [
            "PROVIDER_NEUTRAL_DIGITAL_TWIN_EXECUTED",
            "ONE_BUSINESS_ROLE_BOUND",
            "EXACT_DELEGATED_AUTHORITY_BOUND",
            "ONLY_ALLOWLISTED_READ_ONLY_TOOL_INVOKED",
            "TOOL_CALL_AND_PROVIDER_OUTPUT_BUDGETS_ENFORCED",
            "WRITE_BEFORE_EFFECT_INTENT_PERSISTED",
            "EXACT_RETRY_AND_RESTART_REOPENED_SAME_RECEIPT",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_RUNTIME_EVIDENCE",
            "NO_REPOSITORY_COMMAND_NETWORK_MERGE_DEPLOYMENT_RELEASE_BILLING_OR_APPROVAL_AUTHORITY",
            "NO_SPECIALIZED_DAY23_TO_DAY30_ROLE_BEHAVIOR",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day21_base_commit": APPROVED_DAY21_HEAD,
        "business_role": role,
        "provider_id": receipt.provider_id,
        "execution_status": receipt.status.value,
        "execution_id": receipt.execution_id,
        "execution_receipt_id": receipt.receipt_id,
        "digital_twin_digest": receipt.twin_digest,
        "assignment_digest": receipt.assignment_digest,
        "authority_digest": receipt.authority_digest,
        "provider_request_digest": receipt.request_digest,
        "execution_intent_digest": receipt.intent_digest,
        "execution_output_digest": receipt.output_digest,
        "execution_receipt_digest": receipt.digest,
        "allowed_actions": list(allowed_actions),
        "allowed_tool_ids": [item.tool_id for item in receipt.tool_calls],
        "tool_call_count": len(receipt.tool_calls),
        "maximum_tool_calls": max_tool_calls,
        "tool_call_evidence": [
            {
                "sequence": item.sequence,
                "tool_id": item.tool_id,
                "outcome": item.outcome.value,
                "request_digest": item.request_digest,
                "response_digest": item.response_digest,
            }
            for item in receipt.tool_calls
        ],
        "screenshots": {
            screenshot_name: hashlib.sha256(screenshot).hexdigest(),
        },
        "fixture_contract": (
            "Generic bounded runtime verification only; no product or pilot was selected"
        ),
        "redaction_contract": (
            "Evidence contains no password, bearer token, cookie, CSRF value, secret, or local path"
        ),
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
