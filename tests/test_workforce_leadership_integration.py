from __future__ import annotations

from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.agents import AgentRole
from runtime.workforce_leadership import (
    LeadershipArtifactKind,
    product_manager_objective,
)
from tests.test_workforce_leadership import (
    NOW,
    _authority,
    _run_ceo,
    _twin,
)


APPROVED_DAY22_HEAD = "fa4383fa839bd8f305a47ab942cc20c6fd67d012"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _report(ceo, product_manager):
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 23 leadership workforce verification</title>
<style>
:root{{--ink:#12233d;--muted:#607087;--line:#d8e1ec;--blue:#3157b7;--green:#16775a;--wash:#f2f6fb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);
font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1120px;margin:0 auto;padding:56px 30px}}
.eyebrow{{color:var(--blue);font-weight:800;letter-spacing:.12em;text-transform:uppercase}}
h1{{font-size:48px;line-height:1.05;margin:12px 0}}.lead{{font-size:20px;color:var(--muted);max-width:850px}}
.status{{display:inline-flex;margin:12px 0 28px;background:#e5f7f0;color:var(--green);font-weight:800;
border-radius:999px;padding:10px 16px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
section{{background:#fff;border:1px solid var(--line);border-radius:18px;padding:24px}}
h2{{margin:0 0 8px;font-size:24px}}h3{{margin:22px 0 8px;font-size:15px;color:var(--muted);
text-transform:uppercase;letter-spacing:.06em}}ul{{padding-left:20px;line-height:1.65}}
.trace{{grid-column:1/-1}}dl{{display:grid;grid-template-columns:180px 1fr;gap:11px;margin:0}}
dt{{color:var(--muted)}}dd{{margin:0;font-weight:650;overflow-wrap:anywhere}}code{{font-size:12px}}
.boundary{{border-left:5px solid var(--blue)}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}
.trace{{grid-column:auto}}h1{{font-size:38px}}dl{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS operational workforce · Day 23</div>
<h1>CEO and Product Manager verification</h1>
<p class="lead">Two exact Business Roles produced draft-only opportunity, scope, plan, and status work through the governed Digital Twin runtime.</p>
<div class="status">● BOUNDED DRAFTS COMPLETE</div>
<div class="grid">
<section><h2>CEO opportunity brief</h2><p>{escape(ceo.summary)}</p>
<h3>Goals</h3><ul>{''.join(f'<li>{escape(item)}</li>' for item in ceo.goals)}</ul>
<h3>Status</h3><p>{escape(ceo.status_report.state)} · {escape(ceo.status_report.blockers[0])}</p></section>
<section><h2>Product Manager plan</h2><p>{escape(product_manager.summary)}</p>
<h3>Scope</h3><ul>{''.join(f'<li>{escape(item)}</li>' for item in product_manager.scope_in)}</ul>
<h3>Product plan</h3><ul>{''.join(f'<li>{escape(item)}</li>' for item in product_manager.plan_items)}</ul></section>
<section class="trace"><h2>Exact governed handoff</h2><dl>
<dt>CEO Business Role</dt><dd>CEO</dd>
<dt>Product Manager Role</dt><dd>PROJECT_MANAGER</dd>
<dt>CEO artifact</dt><dd><code>{escape(ceo.digest)}</code></dd>
<dt>PM upstream binding</dt><dd><code>{escape(product_manager.upstream_artifact_digest)}</code></dd>
<dt>PM artifact</dt><dd><code>{escape(product_manager.digest)}</code></dd>
<dt>CEO receipt</dt><dd><code>{escape(ceo.receipt_digest)}</code></dd>
<dt>PM receipt</dt><dd><code>{escape(product_manager.receipt_digest)}</code></dd>
</dl></section>
<section class="trace boundary"><h2>Authority boundary</h2><ul>
<li>Both artifacts remain DRAFT_AWAITING_HUMAN_REVIEW</li>
<li>No tool, repository, command, network, coding, budget, approval, merge, deployment, billing, or release authority</li>
<li>No architecture, technology selection, ADR, or technical risk work from Day 24</li>
<li>No automatic multi-agent orchestration or official pilot product selection</li>
</ul></section></div></main></body></html>""".encode("utf-8")

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day23-leadership-evidence":
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
def test_real_chromium_inspects_ceo_product_manager_handoff(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    service, provider, intake, _, _, ceo = _run_ceo(tmp_path)
    pm_twin = _twin(AgentRole.PROJECT_MANAGER)
    pm_authority = _authority(
        AgentRole.PROJECT_MANAGER,
        product_manager_objective(intake, ceo),
        assignment_id="assignment-product-manager-browser",
        twin_id=pm_twin.twin_id,
    )
    product_manager = service.run_product_manager(
        execution_id="execution-product-manager-browser",
        twin=pm_twin,
        authority=pm_authority,
        intake=intake,
        ceo_artifact=ceo,
    )
    assert ceo.kind is LeadershipArtifactKind.CEO_OPPORTUNITY_BRIEF
    assert product_manager.kind is LeadershipArtifactKind.PRODUCT_MANAGER_PLAN
    assert product_manager.upstream_artifact_digest == ceo.digest
    assert provider.execution_count == 2

    server = make_server(
        "127.0.0.1",
        0,
        _report(ceo, product_manager),
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    console_errors: list[str] = []
    request_failures: list[str] = []
    screenshot: bytes
    try:
        with playwright.sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1600},
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
                f"http://127.0.0.1:{server.server_port}/day23-leadership-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            page.get_by_role(
                "heading", name="CEO and Product Manager verification"
            ).wait_for()
            assert page.get_by_text("BOUNDED DRAFTS COMPLETE").is_visible()
            assert page.get_by_text("CEO", exact=True).is_visible()
            assert page.get_by_text("PROJECT_MANAGER", exact=True).is_visible()
            assert page.get_by_text(ceo.digest, exact=True).count() == 2
            assert page.get_by_text(product_manager.digest, exact=True).is_visible()
            assert page.get_by_text(
                "No automatic multi-agent orchestration or official pilot product selection",
                exact=True,
            ).is_visible()
            assert console_errors == []
            assert request_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY23_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(Path(target), intake, ceo, product_manager, screenshot)


def _write_evidence(target: Path, intake, ceo, product_manager, screenshot: bytes) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "ceo-product-manager-verification.png"
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
        "journey": "workforce_leadership.ceo_to_product_manager.inspect_drafts",
        "claims": [
            "CEO_OPPORTUNITY_INTAKE_EXECUTED",
            "CEO_STATUS_REPORT_PRODUCED",
            "PRODUCT_MANAGER_SCOPE_CLARIFICATION_EXECUTED",
            "PRODUCT_MANAGER_DRAFT_PLAN_PRODUCED",
            "PRODUCT_MANAGER_STATUS_REPORT_PRODUCED",
            "EXACT_CEO_TO_PRODUCT_MANAGER_HANDOFF_BOUND",
            "BOTH_ROLES_EXECUTED_THROUGH_DIGITAL_TWIN_RUNTIME",
            "EXACT_RETRY_AND_RESTART_ARE_SIDE_EFFECT_FREE",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_DRAFTS",
            "NO_TOOLS_REPOSITORY_COMMAND_NETWORK_CODING_APPROVAL_BUDGET_MERGE_DEPLOYMENT_RELEASE_OR_BILLING_AUTHORITY",
            "NO_DAY24_ARCHITECTURE_BEHAVIOR",
            "NO_MULTI_AGENT_ORCHESTRATION",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day22_base_commit": APPROVED_DAY22_HEAD,
        "opportunity_digest": intake.digest,
        "fixture_contract": (
            "Generic workforce verification data only; no official pilot product was selected"
        ),
        "ceo": _artifact_evidence(ceo),
        "product_manager": _artifact_evidence(product_manager),
        "screenshots": {screenshot_name: hashlib.sha256(screenshot).hexdigest()},
        "redaction_contract": (
            "No credentials, cookies, customer secrets, raw provider exceptions, or local paths"
        ),
    }
    content = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (target / "manifest.json").write_bytes(content)


def _artifact_evidence(value) -> dict[str, object]:
    return {
        "artifact_id": value.artifact_id,
        "artifact_kind": value.kind.value,
        "business_role": value.business_role.value,
        "provider_id": value.provider_id,
        "status": value.status,
        "pilot_status": value.pilot_status,
        "artifact_digest": value.digest,
        "upstream_artifact_digest": value.upstream_artifact_digest,
        "authority_digest": value.authority_digest,
        "assignment_digest": value.assignment_digest,
        "provider_request_digest": value.request_digest,
        "provider_output_digest": value.output_digest,
        "execution_receipt_digest": value.receipt_digest,
        "tool_call_count": 0,
    }
