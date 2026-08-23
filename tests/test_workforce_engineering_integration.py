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

from runtime.workforce_engineering import ARTIFACT_STATUS, ENGINEERING_ROLES, PILOT_STATUS
from tests.test_workforce_engineering import _run_engineering_family


APPROVED_DAY24_HEAD = "1d02e84548e998f7ad3fb045f9745a0c300c6914"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _items(values: tuple[str, ...]) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in values)


def _report(architecture, executions):
    cards = []
    bindings = []
    for _, twin, authority, artifact in executions:
        implementations = "".join(
            f"<li><strong>{escape(item.target_component_id)}</strong> · "
            f"{escape(item.implementation)}</li>"
            for item in artifact.implementation_items
        )
        contract = artifact.interface_contracts[0]
        cards.append(
            f"<article><div class='row'><h2>{escape(artifact.business_role.value)}</h2>"
            "<span class='complete'>BOUNDED COMPLETE</span></div>"
            f"<p>{escape(artifact.summary)}</p><h3>Implementation output</h3>"
            f"<ul>{implementations}</ul><h3>{escape(contract.name)}</h3>"
            f"<p>{escape(contract.producer)} → {escape(contract.consumer)}</p>"
            f"<small>{escape(contract.failure_behavior)}</small>"
            f"<h3>Capabilities</h3><p class='mono'>{escape(' · '.join(twin.capability_ids))}</p>"
            f"<p class='state'>{escape(artifact.status)}</p>"
            f"<span class='zero'>0 tools · {authority.max_tool_calls} tool calls</span></article>"
        )
        bindings.append(
            f"<tr><td>{escape(artifact.business_role.value)}</td>"
            f"<td><code>{escape(artifact.work_order_digest)}</code></td>"
            f"<td><code>{escape(artifact.architecture_artifact_digest)}</code></td>"
            f"<td><code>{escape(artifact.receipt_digest)}</code></td></tr>"
        )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 25 Engineering family verification</title>
<style>
:root{{--ink:#10243f;--muted:#66758b;--line:#d3deea;--blue:#2762bb;--green:#13765b;
--wash:#eef3f8;--amber:#9a6415}}*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);
color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1240px;
margin:0 auto;padding:50px 28px 70px}}.eyebrow{{color:var(--blue);font-weight:850;letter-spacing:.12em;
text-transform:uppercase}}h1{{font-size:48px;line-height:1.06;margin:12px 0}}.lead{{font-size:20px;
line-height:1.5;color:var(--muted);max-width:980px}}.status{{display:inline-flex;margin:10px 0 28px;
background:#dcf5ec;color:var(--green);font-weight:850;border-radius:999px;padding:10px 16px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}article,section{{background:#fff;
border:1px solid var(--line);border-radius:18px;padding:23px}}article{{min-height:520px}}.row{{display:flex;
justify-content:space-between;gap:12px;align-items:start}}h2{{font-size:24px;margin:0 0 14px}}h3{{font-size:15px;
margin:20px 0 8px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}p,li{{line-height:1.55}}
ul{{padding-left:20px}}small{{color:var(--muted);line-height:1.5;display:block}}.complete{{background:#dcf5ec;
color:var(--green);font-size:11px;font-weight:850;padding:6px 8px;border-radius:999px;white-space:nowrap}}
.zero{{display:inline-flex;background:#edf4ff;color:var(--blue);font-weight:800;padding:7px 10px;border-radius:8px}}
.state{{font-size:11px;color:var(--amber);font-weight:850;overflow-wrap:anywhere}}.mono,code{{font-family:
ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;overflow-wrap:anywhere}}section{{margin-top:18px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;vertical-align:top;
border-bottom:1px solid var(--line)}}th{{font-size:11px;color:var(--muted);text-transform:uppercase;
letter-spacing:.06em}}.boundary{{border-left:5px solid var(--blue)}}
@media(max-width:840px){{.grid{{grid-template-columns:1fr}}h1{{font-size:38px}}article{{min-height:auto}}
table{{font-size:12px}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS operational workforce · Day 25</div>
<h1>Governed Engineering agent family</h1>
<p class="lead">Backend, Frontend, AI, and Data assignments executed through one shared Digital Twin runtime with exact role, capability, authority, assignment, tenant, architecture-source, and receipt bindings.</p>
<div class="status">● 4 OF 4 ROLE PROFILES · RUNTIME VERIFIED</div>
<div class="grid">{''.join(cards)}</div>
<section><h2>Exact architecture → Engineering bindings</h2><p>Persisted source: <code>{escape(architecture.digest)}</code></p>
<table><thead><tr><th>Role</th><th>Work order</th><th>Architecture source</th><th>Execution receipt</th></tr></thead>
<tbody>{''.join(bindings)}</tbody></table></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>Zero tools; no filesystem, repository, command, network, credential, coding-workspace, commit, merge, deployment, release, billing, or budget capability</li>
<li>Architecture remains DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW</li>
<li>QA, Security, DevOps, Documentation, and multi-agent orchestration remain Days 26–30</li>
<li>No official pilot product selected</li></ul></section>
</main></body></html>""".encode("utf-8")

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day25-engineering-evidence":
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
def test_real_chromium_inspects_engineering_agent_family(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    _, provider, _, architecture, executions = _run_engineering_family(tmp_path)
    assert provider.execution_count == 4
    assert tuple(item[3].business_role for item in executions) == ENGINEERING_ROLES
    assert all(item[3].architecture_artifact_digest == architecture.digest for item in executions)
    assert all(item[3].status == ARTIFACT_STATUS for item in executions)
    assert all(item[3].pilot_status == PILOT_STATUS for item in executions)
    assert all(item[2].allowed_tool_ids == () and item[2].max_tool_calls == 0 for item in executions)

    server = make_server(
        "127.0.0.1",
        0,
        _report(architecture, executions),
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
                viewport={"width": 1440, "height": 2200},
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
                f"http://127.0.0.1:{server.server_port}/day25-engineering-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            page.get_by_role("heading", name="Governed Engineering agent family").wait_for()
            assert page.get_by_text(
                "● 4 OF 4 ROLE PROFILES · RUNTIME VERIFIED", exact=True
            ).is_visible()
            for role in ENGINEERING_ROLES:
                assert page.get_by_role("heading", name=role.value, exact=True).is_visible()
            assert page.get_by_text(architecture.digest, exact=True).count() == 5
            assert page.get_by_text(ARTIFACT_STATUS, exact=True).count() == 4
            assert page.get_by_text(
                "QA, Security, DevOps, Documentation, and multi-agent orchestration remain Days 26–30",
                exact=True,
            ).is_visible()
            assert page.get_by_text(
                "No official pilot product selected", exact=True
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

    target = os.environ.get("ASCOS_DAY25_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(Path(target), architecture, executions, screenshot)


def _write_evidence(target: Path, architecture, executions, screenshot: bytes) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "engineering-agent-family-verification.png"
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
        "journey": "workforce_engineering.architecture_to_four_role_family.inspect_outputs",
        "claims": [
            "EXACT_PERSISTED_DAY24_ARCHITECTURE_CONSUMED",
            "BACKEND_FRONTEND_AI_AND_DATA_ROLES_EXECUTED",
            "ONE_SHARED_PROVIDER_NEUTRAL_DIGITAL_TWIN_RUNTIME_USED",
            "EXACT_ROLE_CAPABILITY_AUTHORITY_ASSIGNMENT_TENANT_SOURCE_AND_RECEIPT_BINDINGS",
            "UNTRUSTED_OUTPUTS_VALIDATED_WITH_CLOSED_TYPED_SCHEMAS",
            "EXACT_RETRY_AND_RESTART_ARE_SIDE_EFFECT_FREE",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_ENGINEERING_EVIDENCE",
            "CONSOLE_AND_NETWORK_FAILURE_COLLECTIONS_EMPTY",
            "NO_TOOLS_FILESYSTEM_REPOSITORY_COMMAND_NETWORK_CREDENTIAL_WORKSPACE_COMMIT_MERGE_DEPLOYMENT_RELEASE_BILLING_OR_BUDGET_AUTHORITY",
            "NO_QA_SECURITY_DEVOPS_DOCUMENTATION_OR_MULTI_AGENT_ORCHESTRATION_BEHAVIOR",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day24_base_commit": APPROVED_DAY24_HEAD,
        "fixture_contract": (
            "Generic Engineering workforce verification data only; no official pilot product was selected"
        ),
        "architecture_source": {
            "artifact_id": architecture.artifact_id,
            "artifact_digest": architecture.digest,
            "business_role": architecture.business_role.value,
            "status": architecture.status,
            "pilot_status": architecture.pilot_status,
        },
        "engineering_family": [
            {
                "artifact_id": artifact.artifact_id,
                "artifact_digest": artifact.digest,
                "work_order_id": work_order.work_order_id,
                "work_order_digest": work_order.digest,
                "business_role": artifact.business_role.value,
                "provider_id": artifact.provider_id,
                "status": artifact.status,
                "pilot_status": artifact.pilot_status,
                "architecture_artifact_digest": artifact.architecture_artifact_digest,
                "capability_ids": list(twin.capability_ids),
                "allowed_action_ids": list(authority.allowed_action_ids),
                "authority_digest": artifact.authority_digest,
                "assignment_digest": artifact.assignment_digest,
                "provider_request_digest": artifact.request_digest,
                "provider_output_digest": artifact.output_digest,
                "execution_receipt_digest": artifact.receipt_digest,
                "implementation_item_count": len(artifact.implementation_items),
                "interface_contract_count": len(artifact.interface_contracts),
                "tool_call_count": 0,
            }
            for work_order, twin, authority, artifact in executions
        ],
        "role_count": len(executions),
        "console_errors": [],
        "network_failures": [],
        "screenshots": {screenshot_name: hashlib.sha256(screenshot).hexdigest()},
        "redaction_contract": (
            "No credentials, cookies, customer secrets, raw provider payloads, exceptions, or local paths"
        ),
    }
    content = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (target / "manifest.json").write_bytes(content)
