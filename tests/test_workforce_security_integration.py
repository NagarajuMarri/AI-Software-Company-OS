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

from runtime.workforce_security import (
    ARTIFACT_STATUS,
    EXECUTION_STATE,
    FINDING_STATUS,
    PILOT_STATUS,
)
from tests.test_workforce_security import _run_security


APPROVED_DAY26_HEAD = "467df344e36b6ed32cbc703754c055631e887690"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _report(authority, artifact):
    threats = "".join(
        f"<article><div class='row'><h2>{escape(item.category.value.replace('_', ' '))}</h2>"
        f"<span>{escape(item.validation_state)}</span></div>"
        f"<h3>{escape(item.asset)}</h3><p>{escape(item.scenario)}</p>"
        f"<small>{escape(item.trust_boundary)}</small></article>"
        for item in artifact.threats
    )
    dependencies = "".join(
        f"<tr><td>{escape(source.business_role.value)}</td>"
        f"<td>{escape(check.kind.value)}</td><td>{escape(check.failure_threshold.value)}</td>"
        f"<td><span>{escape(check.execution_state)}</span></td></tr>"
        for source, check in zip(artifact.sources, artifact.dependency_checks, strict=True)
    )
    exposure = "".join(
        f"<tr><td>{escape(source.business_role.value)}</td>"
        f"<td>{escape(', '.join(check.detector_classes))}</td>"
        f"<td><span>{escape(check.execution_state)}</span></td></tr>"
        for source, check in zip(artifact.sources, artifact.secret_checks, strict=True)
    )
    findings = "".join(
        f"<div class='finding'><div><strong>{escape(item.title)}</strong>"
        f"<p>{escape(item.risk)}</p></div><span>{escape(item.severity.value)} · "
        f"{escape(item.status)}</span></div>"
        for item in artifact.findings
    )
    bindings = "".join(
        f"<tr><td>{escape(source.business_role.value)}</td>"
        f"<td><code>{escape(source.artifact_digest)}</code></td></tr>"
        for source in artifact.sources
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 27 Security Engineer verification</title>
<style>
:root{{--ink:#14213d;--muted:#667085;--line:#d7deea;--blue:#2459a9;--green:#11755b;
--amber:#9b640d;--red:#a33a45;--wash:#eef3f8}}*{{box-sizing:border-box}}body{{margin:0;
background:var(--wash);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:50px 28px 70px}}.eyebrow{{color:var(--blue);
font-weight:850;letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:48px;line-height:1.06;
margin:12px 0}}.lead{{font-size:20px;line-height:1.5;color:var(--muted);max-width:980px}}
.status{{display:inline-flex;margin:10px 0 28px;background:#dcf5ec;color:var(--green);
font-weight:850;border-radius:999px;padding:10px 16px}}.grid{{display:grid;
grid-template-columns:repeat(2,1fr);gap:18px}}article,section{{background:#fff;border:1px solid var(--line);
border-radius:18px;padding:23px}}article{{min-height:255px}}.row{{display:flex;justify-content:space-between;
gap:12px;align-items:start}}h2{{font-size:23px;margin:0 0 14px}}h3{{font-size:16px;margin:20px 0 8px}}
p{{line-height:1.55}}article span,td span{{background:#fff3d6;color:var(--amber);font-size:11px;
font-weight:850;padding:6px 9px;border-radius:999px}}small{{color:var(--muted);line-height:1.5;
display:block}}section{{margin-top:18px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;vertical-align:top;
border-bottom:1px solid var(--line)}}th{{font-size:11px;color:var(--muted);text-transform:uppercase;
letter-spacing:.06em}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;
overflow-wrap:anywhere}}.finding{{display:flex;justify-content:space-between;gap:16px;
border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:12px}}.finding span{{font-size:11px;
color:var(--red);font-weight:850;max-width:360px;text-align:right}}.boundary{{border-left:5px solid var(--blue)}}
ul{{line-height:1.65}}@media(max-width:840px){{.grid,.two{{grid-template-columns:1fr}}h1{{font-size:38px}}
article{{min-height:auto}}.finding{{display:block}}.finding span{{text-align:left}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS operational workforce · Day 27</div>
<h1>Governed Security Engineer agent</h1>
<p class="lead">The exact persisted architecture, four Engineering outputs, and QA artifact are bound into a closed STRIDE threat model with dependency checks, secret checks, and draft security findings.</p>
<div class="status">● SECURITY PLAN COMPLETE · 0 SCANS EXECUTED</div>
<div class="grid">{threats}</div>
<section class="two"><div><h2>Dependency check specifications</h2>
<table><thead><tr><th>Role</th><th>Kind</th><th>Threshold</th><th>State</th></tr></thead>
<tbody>{dependencies}</tbody></table></div><div><h2>Secret check specifications</h2>
<table><thead><tr><th>Role</th><th>Detector classes</th><th>State</th></tr></thead>
<tbody>{exposure}</tbody></table></div></section>
<section><h2>Draft security findings</h2>{findings}</section>
<section><h2>Exact upstream bindings</h2>
<p>QA artifact: <code>{escape(artifact.qa_artifact_digest)}</code></p>
<p>Security receipt: <code>{escape(artifact.receipt_digest)}</code></p>
<table><thead><tr><th>Engineering role</th><th>Artifact digest</th></tr></thead>
<tbody>{bindings}</tbody></table></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>0 tools · {authority.max_tool_calls} tool calls · no live provider</li>
<li>No dependency scan, secret scan, filesystem, workspace, repository, command, network, or credential access</li>
<li>No remediation, security approval, quality approval, or risk acceptance</li>
<li>All output remains {escape(ARTIFACT_STATUS)}; findings remain {escape(FINDING_STATUS)}</li>
<li>DevOps, Documentation, and multi-agent orchestration remain Days 28–30</li>
<li>No commit, merge, deployment, release, billing, budget, or pilot authority</li>
<li>No official pilot product selected</li></ul></section>
</main></body></html>""".encode("utf-8")

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day27-security-evidence":
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


def test_security_evidence_report_has_restrictive_headers_and_exact_bindings(
    tmp_path: Path,
) -> None:
    *_, authority, artifact = _run_security(tmp_path)
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        _report(authority, artifact)(
            {"PATH_INFO": "/day27-security-evidence"},
            start_response,
        )
    )
    headers = captured["headers"]
    assert captured["status"] == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert artifact.qa_artifact_digest.encode() in body
    assert artifact.receipt_digest.encode() in body
    assert b"0 SCANS EXECUTED" in body
    assert b"No official pilot product selected" in body


def test_security_evidence_manifest_binds_exact_sources_and_redacted_counts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, _, _, architecture, sources, qa_artifact, _, _, authority, artifact = (
        _run_security(tmp_path)
    )
    monkeypatch.setenv("ASCOS_EVIDENCE_COMMIT_SHA", "d" * 40)
    target = tmp_path / "founder-evidence"
    screenshot = b"generic-security-screenshot"
    _write_evidence(
        target,
        architecture,
        sources,
        qa_artifact,
        authority,
        artifact,
        screenshot,
    )
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["result"] == "PASS"
    assert manifest["commit_sha"] == "d" * 40
    assert manifest["approved_day26_base_commit"] == APPROVED_DAY26_HEAD
    assert manifest["qa_source"]["artifact_digest"] == qa_artifact.digest
    assert [item["artifact_digest"] for item in manifest["engineering_sources"]] == [
        item.digest for item in sources
    ]
    output = manifest["security_output"]
    assert output["artifact_digest"] == artifact.digest
    assert output["threat_count"] == 6
    assert output["dependency_check_count"] == 4
    assert output["secret_check_count"] == 4
    assert output["finding_count"] == 3
    assert output["execution_state"] == EXECUTION_STATE
    assert output["tool_call_count"] == 0
    assert manifest["screenshots"]["security-engineer-verification.png"] == hashlib.sha256(
        screenshot
    ).hexdigest()


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_chromium_inspects_security_engineer_output(tmp_path: Path) -> None:
    _, provider, _, architecture, sources, qa_artifact, _, _, authority, artifact = (
        _run_security(tmp_path)
    )
    assert provider.execution_count == 1
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(
        item.digest for item in sources
    )
    assert artifact.qa_artifact_digest == qa_artifact.digest
    assert all(item.validation_state == EXECUTION_STATE for item in artifact.threats)
    assert all(
        item.execution_state == EXECUTION_STATE
        for item in artifact.dependency_checks + artifact.secret_checks
    )
    assert all(item.status == FINDING_STATUS for item in artifact.findings)
    assert authority.allowed_tool_ids == () and authority.max_tool_calls == 0

    server = make_server(
        "127.0.0.1",
        0,
        _report(authority, artifact),
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    console_errors: list[str] = []
    request_failures: list[str] = []
    try:
        with pytest.importorskip("playwright.sync_api").sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 3200},
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
                f"http://127.0.0.1:{server.server_port}/day27-security-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            page.get_by_role("heading", name="Governed Security Engineer agent").wait_for()
            assert page.get_by_text(
                "● SECURITY PLAN COMPLETE · 0 SCANS EXECUTED", exact=True
            ).is_visible()
            for threat in artifact.threats:
                assert page.get_by_role(
                    "heading", name=threat.category.value.replace("_", " "), exact=True
                ).is_visible()
            for source in artifact.sources:
                assert page.get_by_text(source.artifact_digest, exact=True).is_visible()
            assert page.get_by_text(EXECUTION_STATE, exact=True).count() == 14
            assert page.get_by_text(FINDING_STATUS, exact=False).count() >= 3
            assert page.get_by_text(ARTIFACT_STATUS, exact=False).is_visible()
            assert page.get_by_text(artifact.qa_artifact_digest, exact=True).is_visible()
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

    target = os.environ.get("ASCOS_DAY27_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(
            Path(target), architecture, sources, qa_artifact, authority, artifact, screenshot
        )


def _write_evidence(
    target: Path,
    architecture,
    sources,
    qa_artifact,
    authority,
    artifact,
    screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "security-engineer-verification.png"
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
        "journey": "workforce_security.exact_sources_to_security_plan.inspect_output",
        "claims": [
            "EXACT_PERSISTED_ARCHITECTURE_ENGINEERING_AND_QA_SOURCES_CONSUMED",
            "ONE_SECURITY_ENGINEER_PROFILE_EXECUTED_ON_PROVIDER_NEUTRAL_RUNTIME",
            "ALL_SIX_STRIDE_CATEGORIES_MODELED",
            "DEPENDENCY_AND_SECRET_CHECK_SPECIFICATIONS_TYPED_FOR_ALL_ENGINEERING_ROLES",
            "DRAFT_SECURITY_FINDINGS_BOUND_TO_EXACT_QA_AND_ENGINEERING_SOURCES",
            "NO_SCAN_REMEDIATION_APPROVAL_OR_RISK_ACCEPTANCE_CLAIMED",
            "EXACT_RETRY_AND_RESTART_ARE_SIDE_EFFECT_FREE",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_SECURITY_EVIDENCE",
            "CONSOLE_AND_NETWORK_FAILURE_COLLECTIONS_EMPTY",
            "NO_TOOLS_LIVE_PROVIDER_FILESYSTEM_REPOSITORY_COMMAND_NETWORK_CREDENTIAL_WORKSPACE_COMMIT_MERGE_DEPLOYMENT_RELEASE_BILLING_OR_BUDGET_AUTHORITY",
            "NO_DEVOPS_DOCUMENTATION_OR_MULTI_AGENT_ORCHESTRATION_BEHAVIOR",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day26_base_commit": APPROVED_DAY26_HEAD,
        "fixture_contract": (
            "Generic Security workforce verification data only; no official pilot was selected"
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
                "status": item.status,
                "pilot_status": item.pilot_status,
            }
            for item in sources
        ],
        "qa_source": {
            "artifact_id": qa_artifact.artifact_id,
            "artifact_digest": qa_artifact.digest,
            "status": qa_artifact.status,
            "pilot_status": qa_artifact.pilot_status,
        },
        "security_output": {
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
            "threat_count": len(artifact.threats),
            "dependency_check_count": len(artifact.dependency_checks),
            "secret_check_count": len(artifact.secret_checks),
            "finding_count": len(artifact.findings),
            "execution_state": EXECUTION_STATE,
            "finding_status": FINDING_STATUS,
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
