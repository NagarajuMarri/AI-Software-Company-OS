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

from runtime.workforce_qa import (
    ARTIFACT_STATUS,
    DEFECT_STATUS,
    EXECUTION_STATE,
    PILOT_STATUS,
)
from tests.test_workforce_qa import _run_qa


APPROVED_DAY25_HEAD = "6c5c1b759be72bd3537ca4d2fe549cbfb79a8650"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _report(architecture, source_artifacts, authority, artifact):
    source_by_digest = {item.digest: item for item in source_artifacts}
    plans = []
    for plan, automated in zip(
        artifact.test_plan_items, artifact.automated_test_specs, strict=True
    ):
        source = source_by_digest[plan.source_engineering_artifact_digest]
        plans.append(
            f"<article><div class='row'><h2>{escape(source.business_role.value)}</h2>"
            f"<span class='level'>{escape(plan.level.value)}</span></div>"
            f"<p>{escape(plan.objective)}</p><h3>Automated test specification</h3>"
            f"<p><strong>{escape(automated.kind.value)}</strong> · "
            f"{escape(automated.target_component_id)}</p>"
            f"<p>{escape(automated.scenario)}</p>"
            f"<span class='pending'>{escape(automated.execution_state)}</span></article>"
        )
    integrations = "".join(
        f"<div class='integration'><strong>{escape(item.spec_id)}</strong>"
        f"<p>{escape(item.scenario)}</p><small>{escape(item.failure_behavior)}</small>"
        f"<span>{escape(item.execution_state)}</span></div>"
        for item in artifact.integration_test_specs
    )
    defects = "".join(
        f"<div class='defect'><div><strong>{escape(item.title)}</strong>"
        f"<p>{escape(item.observed_risk)}</p></div>"
        f"<span>{escape(item.severity.value)} · {escape(item.status)}</span></div>"
        for item in artifact.defect_reports
    )
    bindings = "".join(
        f"<tr><td>{escape(source.business_role.value)}</td>"
        f"<td><code>{escape(source.artifact_digest)}</code></td>"
        f"<td><code>{escape(source.architecture_artifact_digest)}</code></td></tr>"
        for source in artifact.sources
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 26 QA Engineer verification</title>
<style>
:root{{--ink:#14213d;--muted:#667085;--line:#d7deea;--blue:#2459a9;--green:#11755b;
--amber:#9b640d;--red:#a33a45;--wash:#eef3f8}}*{{box-sizing:border-box}}body{{margin:0;
background:var(--wash);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:50px 28px 70px}}.eyebrow{{color:var(--blue);
font-weight:850;letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:48px;line-height:1.06;
margin:12px 0}}.lead{{font-size:20px;line-height:1.5;color:var(--muted);max-width:980px}}
.status{{display:inline-flex;margin:10px 0 28px;background:#dcf5ec;color:var(--green);
font-weight:850;border-radius:999px;padding:10px 16px}}.grid{{display:grid;
grid-template-columns:1fr 1fr;gap:18px}}article,section{{background:#fff;border:1px solid var(--line);
border-radius:18px;padding:23px}}article{{min-height:330px}}.row{{display:flex;justify-content:space-between;
gap:12px;align-items:start}}h2{{font-size:23px;margin:0 0 14px}}h3{{font-size:14px;margin:20px 0 8px;
text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}p{{line-height:1.55}}
.level{{background:#e5edff;color:var(--blue);font-size:11px;font-weight:850;padding:6px 9px;
border-radius:999px}}.pending{{display:inline-flex;background:#fff3d6;color:var(--amber);
font-weight:850;padding:7px 10px;border-radius:8px}}section{{margin-top:18px}}.two{{display:grid;
grid-template-columns:1fr 1fr;gap:16px}}.integration,.defect{{border:1px solid var(--line);
border-radius:12px;padding:16px;margin-top:12px}}.integration span{{display:block;margin-top:10px;
font-weight:850;color:var(--amber)}}.defect{{display:flex;justify-content:space-between;gap:16px}}
.defect span{{font-size:11px;color:var(--red);font-weight:850;max-width:330px;text-align:right}}
small{{color:var(--muted);line-height:1.5;display:block}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}
th{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;overflow-wrap:anywhere}}
.boundary{{border-left:5px solid var(--blue)}}ul{{line-height:1.65}}
@media(max-width:840px){{.grid,.two{{grid-template-columns:1fr}}h1{{font-size:38px}}
article{{min-height:auto}}.defect{{display:block}}.defect span{{text-align:left}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS operational workforce · Day 26</div>
<h1>Governed QA Engineer agent</h1>
<p class="lead">The exact persisted architecture and four Engineering outputs are bound into one typed quality plan with automated-test specifications, integration-test specifications, and draft defect reports.</p>
<div class="status">● QA PLAN COMPLETE · 0 TESTS EXECUTED</div>
<div class="grid">{''.join(plans)}</div>
<section class="two"><div><h2>Integration specifications</h2>{integrations}</div>
<div><h2>Draft defect reports</h2>{defects}</div></section>
<section><h2>Exact Engineering → QA bindings</h2>
<p>QA receipt: <code>{escape(artifact.receipt_digest)}</code></p>
<table><thead><tr><th>Source role</th><th>Engineering artifact</th><th>Architecture source</th></tr></thead>
<tbody>{bindings}</tbody></table></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>0 tools · {authority.max_tool_calls} tool calls · no live provider</li>
<li>No test files written and no automated, integration, browser, command, or product tests executed</li>
<li>No quality approval; all output remains {escape(ARTIFACT_STATUS)}</li>
<li>Security, DevOps, Documentation, and multi-agent orchestration remain Days 27–30</li>
<li>No repository, commit, merge, deployment, release, billing, budget, or pilot authority</li>
<li>No official pilot product selected</li></ul></section>
</main></body></html>""".encode("utf-8")

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day26-qa-evidence":
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
def test_real_chromium_inspects_qa_engineer_output(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    _, provider, _, architecture, sources, _, _, authority, artifact = _run_qa(tmp_path)
    assert provider.execution_count == 1
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(
        item.digest for item in sources
    )
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.automated_test_specs)
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.integration_test_specs)
    assert all(item.status == DEFECT_STATUS for item in artifact.defect_reports)
    assert authority.allowed_tool_ids == () and authority.max_tool_calls == 0

    server = make_server(
        "127.0.0.1",
        0,
        _report(architecture, sources, authority, artifact),
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
                f"http://127.0.0.1:{server.server_port}/day26-qa-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            page.get_by_role("heading", name="Governed QA Engineer agent").wait_for()
            assert page.get_by_text(
                "● QA PLAN COMPLETE · 0 TESTS EXECUTED", exact=True
            ).is_visible()
            for source in artifact.sources:
                assert page.get_by_role(
                    "heading", name=source.business_role.value, exact=True
                ).is_visible()
                assert page.get_by_text(source.artifact_digest, exact=True).is_visible()
            assert page.get_by_text(EXECUTION_STATE, exact=True).count() == 6
            assert page.get_by_text(DEFECT_STATUS, exact=False).count() >= 2
            assert page.get_by_text(ARTIFACT_STATUS, exact=False).is_visible()
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

    target = os.environ.get("ASCOS_DAY26_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(Path(target), architecture, sources, authority, artifact, screenshot)


def _write_evidence(
    target: Path,
    architecture,
    source_artifacts,
    authority,
    artifact,
    screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "qa-engineer-verification.png"
    (target / screenshot_name).write_bytes(screenshot)
    commit_sha = (
        os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or "e" * 40
    ).lower()
    assert re.fullmatch(r"[0-9a-f]{40}", commit_sha)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "workforce_qa.exact_engineering_sources_to_quality_plan.inspect_output",
        "claims": [
            "EXACT_PERSISTED_DAY24_ARCHITECTURE_CONSUMED",
            "EXACT_PERSISTED_DAY25_ENGINEERING_FAMILY_CONSUMED",
            "ONE_QA_ENGINEER_PROFILE_EXECUTED_ON_PROVIDER_NEUTRAL_RUNTIME",
            "TEST_PLAN_AUTOMATED_TEST_INTEGRATION_TEST_AND_DEFECT_OUTPUTS_TYPED",
            "EXACT_ROLE_CAPABILITY_AUTHORITY_ASSIGNMENT_TENANT_SOURCE_AND_RECEIPT_BINDINGS",
            "UNTRUSTED_OUTPUT_VALIDATED_WITH_CLOSED_TYPED_SCHEMAS",
            "EXACT_RETRY_AND_RESTART_ARE_SIDE_EFFECT_FREE",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_QA_EVIDENCE",
            "CONSOLE_AND_NETWORK_FAILURE_COLLECTIONS_EMPTY",
            "NO_TEST_FILES_WRITTEN_AND_NO_PRODUCT_TESTS_EXECUTED",
            "NO_TOOLS_LIVE_PROVIDER_FILESYSTEM_REPOSITORY_COMMAND_NETWORK_CREDENTIAL_WORKSPACE_COMMIT_MERGE_DEPLOYMENT_RELEASE_BILLING_OR_BUDGET_AUTHORITY",
            "NO_SECURITY_DEVOPS_DOCUMENTATION_OR_MULTI_AGENT_ORCHESTRATION_BEHAVIOR",
            "NO_QUALITY_APPROVAL_AND_NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day25_base_commit": APPROVED_DAY25_HEAD,
        "fixture_contract": (
            "Generic QA workforce verification data only; no official pilot product was selected"
        ),
        "architecture_source": {
            "artifact_id": architecture.artifact_id,
            "artifact_digest": architecture.digest,
            "status": architecture.status,
            "pilot_status": architecture.pilot_status,
        },
        "engineering_sources": [
            {
                "artifact_id": item.artifact_id,
                "artifact_digest": item.digest,
                "business_role": item.business_role.value,
                "architecture_artifact_digest": item.architecture_artifact_digest,
                "status": item.status,
                "pilot_status": item.pilot_status,
            }
            for item in source_artifacts
        ],
        "qa_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "work_order_digest": artifact.work_order_digest,
            "business_role": artifact.business_role.value,
            "provider_id": artifact.provider_id,
            "status": artifact.status,
            "pilot_status": artifact.pilot_status,
            "capability_ids": list(artifact.capability_ids),
            "allowed_action_ids": list(artifact.action_ids),
            "authority_digest": artifact.authority_digest,
            "assignment_digest": artifact.assignment_digest,
            "provider_request_digest": artifact.request_digest,
            "provider_output_digest": artifact.output_digest,
            "execution_receipt_digest": artifact.receipt_digest,
            "test_plan_count": len(artifact.test_plan_items),
            "automated_test_spec_count": len(artifact.automated_test_specs),
            "integration_test_spec_count": len(artifact.integration_test_specs),
            "defect_report_count": len(artifact.defect_reports),
            "test_execution_state": EXECUTION_STATE,
            "defect_status": DEFECT_STATUS,
            "tool_call_count": authority.max_tool_calls,
        },
        "console_errors": [],
        "network_failures": [],
        "screenshots": {screenshot_name: hashlib.sha256(screenshot).hexdigest()},
        "redaction_contract": (
            "No credentials, cookies, customer secrets, raw provider payloads, exceptions, or local paths"
        ),
    }
    content = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (target / "manifest.json").write_bytes(content)
