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

from runtime.workforce_devops import ARTIFACT_STATUS, EXECUTION_STATE, PILOT_STATUS
from tests.test_workforce_devops import _run_devops


APPROVED_DAY27_HEAD = "625a9ba1ce5e3048a198d70e74a8c8b1a3f22e16"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _list(items) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def _plan_card(name: str, subtitle: str, items, state: str) -> str:
    return (
        f"<article><div class='row'><h2>{escape(name)}</h2><span>{escape(state)}</span></div>"
        f"<p>{escape(subtitle)}</p><ul>{_list(items)}</ul></article>"
    )


def _report(authority, artifact):
    cards = "".join((
        _plan_card("CI pipeline", "Five fail-closed stages with exact evidence gates", artifact.ci_pipeline.stages, artifact.ci_pipeline.execution_state),
        _plan_card("Isolated preview", artifact.preview_environment.environment_class, artifact.preview_environment.isolation_controls, artifact.preview_environment.execution_state),
        _plan_card("Migrations", "Data-source-bound reversible migration preparation", artifact.migration_plan.preflight_checks, artifact.migration_plan.execution_state),
        _plan_card("Deployment", artifact.deployment_plan.target_environment, artifact.deployment_plan.deployment_steps, artifact.deployment_plan.execution_state),
        _plan_card("Monitoring", artifact.monitoring_plan.target_environment, artifact.monitoring_plan.signals, artifact.monitoring_plan.execution_state),
        _plan_card("Rollback", artifact.rollback_plan.target_environment, artifact.rollback_plan.rollback_steps, artifact.rollback_plan.execution_state),
    ))
    bindings = "".join(
        f"<tr><td>{escape(source.business_role.value)}</td><td><code>{escape(source.artifact_digest)}</code></td>"
        f"<td>{escape(', '.join(source.target_component_ids))}</td></tr>"
        for source in artifact.sources
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 28 DevOps Engineer verification</title>
<style>
:root{{--ink:#102a43;--muted:#627d98;--line:#d9e2ec;--blue:#1463b8;--green:#087f5b;
--amber:#9c6506;--wash:#edf2f7}}*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);
color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1280px;
margin:0 auto;padding:48px 28px 72px}}.eyebrow{{color:var(--blue);font-weight:850;letter-spacing:.12em;
text-transform:uppercase}}h1{{font-size:48px;line-height:1.06;margin:12px 0}}.lead{{font-size:20px;
line-height:1.5;color:var(--muted);max-width:1040px}}.status{{display:inline-flex;margin:10px 0 28px;
background:#dff7ee;color:var(--green);font-weight:850;border-radius:999px;padding:10px 16px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}}article,section{{background:#fff;
border:1px solid var(--line);border-radius:18px;padding:23px}}article{{min-height:330px}}.row{{display:flex;
justify-content:space-between;gap:12px;align-items:start}}h2{{font-size:23px;margin:0 0 14px}}
p,li{{line-height:1.55}}article span{{background:#fff3d6;color:var(--amber);font-size:11px;
font-weight:850;padding:6px 9px;border-radius:999px}}section{{margin-top:18px}}table{{width:100%;
border-collapse:collapse}}th,td{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}
th{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}code{{font-family:
ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;overflow-wrap:anywhere}}.boundary{{border-left:5px solid var(--blue)}}
@media(max-width:840px){{.grid{{grid-template-columns:1fr}}h1{{font-size:38px}}article{{min-height:auto}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS operational workforce · Day 28</div>
<h1>Governed DevOps Engineer agent</h1>
<p class="lead">The exact persisted Architecture, four Engineering outputs, QA artifact, and Security artifact are bound into six reviewable operational preparation plans.</p>
<div class="status">● DEVOPS PREPARATION COMPLETE · 0 OPERATIONS EXECUTED</div>
<div class="grid">{cards}</div>
<section><h2>Exact upstream bindings</h2>
<p>Architecture: <code>{escape(artifact.architecture_artifact_digest)}</code></p>
<p>QA: <code>{escape(artifact.qa_artifact_digest)}</code></p>
<p>Security: <code>{escape(artifact.security_artifact_digest)}</code></p>
<p>DevOps receipt: <code>{escape(artifact.receipt_digest)}</code></p>
<table><thead><tr><th>Engineering role</th><th>Artifact digest</th><th>Components</th></tr></thead>
<tbody>{bindings}</tbody></table></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>0 tools · {authority.max_tool_calls} tool calls · no live provider</li>
<li>No filesystem, workspace, repository, command, network, infrastructure, credentials, or secret values</li>
<li>No CI run, provisioning, migration, deployment, monitoring connection, rollback, promotion, release, or production target</li>
<li>Every plan remains {escape(EXECUTION_STATE)} and the artifact remains {escape(ARTIFACT_STATUS)}</li>
<li>No commit, merge, billing, budget, architecture, QA, Security, risk-acceptance, or orchestration authority</li>
<li>No official pilot product selected</li></ul></section>
</main></body></html>""".encode("utf-8")

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day28-devops-evidence":
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


def test_devops_evidence_report_has_restrictive_headers_and_exact_bindings(tmp_path: Path) -> None:
    *_, authority, artifact = _run_devops(tmp_path)
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(_report(authority, artifact)({"PATH_INFO": "/day28-devops-evidence"}, start_response))
    headers = captured["headers"]
    assert captured["status"] == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert artifact.architecture_artifact_digest.encode() in body
    assert artifact.qa_artifact_digest.encode() in body
    assert artifact.security_artifact_digest.encode() in body
    assert b"0 OPERATIONS EXECUTED" in body
    assert b"No official pilot product selected" in body


def test_devops_evidence_manifest_binds_every_source_and_six_plan_states(tmp_path: Path, monkeypatch) -> None:
    _, _, _, architecture, sources, qa, security, _, _, authority, artifact = _run_devops(tmp_path)
    monkeypatch.setenv("ASCOS_EVIDENCE_COMMIT_SHA", "d" * 40)
    target = tmp_path / "founder-evidence"
    screenshot = b"generic-devops-screenshot"
    _write_evidence(target, architecture, sources, qa, security, authority, artifact, screenshot)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["result"] == "PASS"
    assert manifest["commit_sha"] == "d" * 40
    assert manifest["approved_day27_base_commit"] == APPROVED_DAY27_HEAD
    assert manifest["qa_source"]["artifact_digest"] == qa.digest
    assert manifest["security_source"]["artifact_digest"] == security.digest
    assert [item["artifact_digest"] for item in manifest["engineering_sources"]] == [item.digest for item in sources]
    output = manifest["devops_output"]
    assert output["artifact_digest"] == artifact.digest
    assert output["plan_count"] == 6
    assert set(output["plan_states"].values()) == {EXECUTION_STATE}
    assert output["tool_call_count"] == 0
    assert manifest["screenshots"]["devops-engineer-verification.png"] == hashlib.sha256(screenshot).hexdigest()


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_chromium_inspects_devops_engineer_output(tmp_path: Path) -> None:
    _, provider, _, architecture, sources, qa, security, _, _, authority, artifact = _run_devops(tmp_path)
    assert provider.execution_count == 1
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(item.digest for item in sources)
    assert artifact.qa_artifact_digest == qa.digest
    assert artifact.security_artifact_digest == security.digest
    plans = (
        artifact.ci_pipeline, artifact.preview_environment, artifact.migration_plan,
        artifact.deployment_plan, artifact.monitoring_plan, artifact.rollback_plan,
    )
    assert all(item.execution_state == EXECUTION_STATE for item in plans)
    assert authority.allowed_tool_ids == () and authority.max_tool_calls == 0

    server = make_server(
        "127.0.0.1", 0, _report(authority, artifact),
        server_class=_ThreadingServer, handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    console_errors: list[str] = []
    request_failures: list[str] = []
    try:
        with pytest.importorskip("playwright.sync_api").sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US", timezone_id="UTC")
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: request_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day28-devops-evidence", wait_until="networkidle"
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            page.get_by_role("heading", name="Governed DevOps Engineer agent").wait_for()
            assert page.get_by_text("● DEVOPS PREPARATION COMPLETE · 0 OPERATIONS EXECUTED", exact=True).is_visible()
            for heading in ("CI pipeline", "Isolated preview", "Migrations", "Deployment", "Monitoring", "Rollback"):
                assert page.get_by_role("heading", name=heading, exact=True).is_visible()
            for source in artifact.sources:
                assert page.get_by_text(source.artifact_digest, exact=True).is_visible()
            assert page.get_by_text(EXECUTION_STATE, exact=True).count() == 6
            assert page.get_by_text(ARTIFACT_STATUS, exact=False).is_visible()
            assert page.get_by_text(artifact.security_artifact_digest, exact=True).is_visible()
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

    target = os.environ.get("ASCOS_DAY28_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(Path(target), architecture, sources, qa, security, authority, artifact, screenshot)


def _write_evidence(target: Path, architecture, sources, qa, security, authority, artifact, screenshot: bytes) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "devops-engineer-verification.png"
    (target / screenshot_name).write_bytes(screenshot)
    commit_sha = (os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA") or os.environ.get("GITHUB_SHA") or "e" * 40).lower()
    assert re.fullmatch(r"[0-9a-f]{40}", commit_sha)
    plans = {
        "ci_pipeline": artifact.ci_pipeline.execution_state,
        "preview_environment": artifact.preview_environment.execution_state,
        "migration": artifact.migration_plan.execution_state,
        "deployment": artifact.deployment_plan.execution_state,
        "monitoring": artifact.monitoring_plan.execution_state,
        "rollback": artifact.rollback_plan.execution_state,
    }
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "workforce_devops.exact_sources_to_six_operational_plans.inspect_output",
        "claims": [
            "EXACT_PERSISTED_ARCHITECTURE_ENGINEERING_QA_AND_SECURITY_SOURCES_CONSUMED",
            "ONE_DEVOPS_ENGINEER_PROFILE_EXECUTED_ON_PROVIDER_NEUTRAL_RUNTIME",
            "CI_PREVIEW_MIGRATION_DEPLOYMENT_MONITORING_AND_ROLLBACK_PLANS_TYPED",
            "ALL_OPERATIONAL_ACTIONS_TRUTHFULLY_NOT_EXECUTED",
            "EXACT_RETRY_AND_RESTART_ARE_SIDE_EFFECT_FREE",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_DEVOPS_EVIDENCE",
            "CONSOLE_AND_NETWORK_FAILURE_COLLECTIONS_EMPTY",
            "NO_TOOLS_LIVE_PROVIDER_FILESYSTEM_REPOSITORY_COMMAND_NETWORK_INFRASTRUCTURE_CREDENTIAL_WORKSPACE_COMMIT_MERGE_DEPLOYMENT_RELEASE_BILLING_OR_BUDGET_AUTHORITY",
            "NO_PRODUCTION_PROMOTION_QA_SECURITY_DOCUMENTATION_OR_MULTI_AGENT_ORCHESTRATION_BEHAVIOR",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day27_base_commit": APPROVED_DAY27_HEAD,
        "fixture_contract": "Generic DevOps workforce verification data only; no official pilot was selected",
        "architecture_source": {
            "artifact_id": architecture.artifact_id, "artifact_digest": architecture.digest,
            "status": architecture.status, "pilot_status": architecture.pilot_status,
        },
        "engineering_sources": [
            {
                "artifact_id": item.artifact_id, "artifact_digest": item.digest,
                "business_role": item.business_role.value, "status": item.status,
                "pilot_status": item.pilot_status,
            }
            for item in sources
        ],
        "qa_source": {
            "artifact_id": qa.artifact_id, "artifact_digest": qa.digest,
            "status": qa.status, "pilot_status": qa.pilot_status,
        },
        "security_source": {
            "artifact_id": security.artifact_id, "artifact_digest": security.digest,
            "status": security.status, "pilot_status": security.pilot_status,
        },
        "devops_output": {
            "artifact_id": artifact.artifact_id, "artifact_digest": artifact.digest,
            "work_order_digest": artifact.work_order_digest, "business_role": artifact.business_role.value,
            "provider_id": artifact.provider_id, "status": artifact.status,
            "pilot_status": artifact.pilot_status, "capability_ids": list(artifact.capability_ids),
            "allowed_action_ids": list(artifact.action_ids), "authority_digest": artifact.authority_digest,
            "assignment_digest": artifact.assignment_digest, "provider_request_digest": artifact.request_digest,
            "provider_output_digest": artifact.output_digest, "execution_receipt_digest": artifact.receipt_digest,
            "plan_count": len(plans), "plan_states": plans, "target_environment": artifact.deployment_plan.target_environment,
            "tool_call_count": authority.max_tool_calls,
        },
        "console_errors": [], "network_failures": [],
        "screenshots": {screenshot_name: hashlib.sha256(screenshot).hexdigest()},
        "redaction_contract": "No credentials, cookies, customer secrets, raw provider payloads, exceptions, or local paths",
    }
    content = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (target / "manifest.json").write_bytes(content)
