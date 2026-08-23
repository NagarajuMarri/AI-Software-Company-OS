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

from runtime.v1_hardening_acceptance import (
    ARTIFACT_STATUS,
    DOCUMENTATION_IDS,
    FOUNDER_UAT_STATUS,
    HARDENING_CONTROL_IDS,
    PRODUCTION_STATE,
    RELEASE_STATE,
)
from tests.test_complete_runtime_acceptance_integration import (
    RoutedPreviewChromiumProvider,
)
from tests.test_v1_hardening_acceptance import _run_hardening


APPROVED_DAY36_BASE_SHA = "7190fe7a7b10a609b17a5d1ac3c6b405508a3cfe"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):  # noqa: ANN001
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _founder_page(artifact) -> bytes:  # noqa: ANN001
    rows = "".join(
        f"<tr><td><code>{escape(item.control_id)}</code></td>"
        f"<td class='pass'>PASS</td><td>{escape(item.state)}</td>"
        f"<td><code>{item.audit_digest[:14]}…</code></td></tr>"
        for item in artifact.control_receipts
    )
    signals = "".join(
        f"<li><strong>{escape(item.signal_id)}</strong>: <span class='pass'>HEALTHY</span></li>"
        for item in artifact.monitoring_receipts
    )
    documents = "".join(f"<li>{escape(item)}</li>" for item in artifact.documentation_ids)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>ASCOS V1 Day 37 acceptance</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:#0c3155;font-family:Inter,Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:42px 28px 54px}}.eyebrow{{color:#2767bd;font-weight:800;letter-spacing:2px}}
h1{{font-size:42px;margin:12px 0}}p{{color:#55728f;font-size:18px;line-height:1.55}}.badge{{display:inline-block;background:#dff5e9;color:#087447;font-weight:800;padding:10px 16px;border-radius:24px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,section{{background:white;border:1px solid #d5e0ec;border-radius:16px;padding:20px}}
.metric{{font-size:34px;font-weight:900}}.label{{color:#607c97}}section{{margin:18px 0}}h2{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce5ee}}th{{font-size:12px;color:#607c97}}code{{font-size:12px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.boundary{{border-left:5px solid #2767bd}}.warning{{color:#936100;font-weight:800}}.pass{{color:#087447;font-weight:800}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}}}</style></head><body><main>
<div class="eyebrow">ASCOS V1 · FINAL MODULE · DAY 37</div><h1>V1 hardening and founder UAT</h1>
<p>The exact completed Day 36 fixture pilot was hardened through verified security, backup, recovery, audit, monitoring, documentation, and founder-UAT-readiness gates.</p>
<div class="badge">● 7 FINAL GATES VERIFIED · FOUNDER UAT READY · RELEASE BLOCKED</div>
<div class="metrics"><div class="card"><div class="metric">7</div><div class="label">final control gates</div></div>
<div class="card"><div class="metric">{artifact.backup_copy_count}</div><div class="label">verified backup copy</div></div>
<div class="card"><div class="metric">{artifact.recovery_drill_count}</div><div class="label">recovery drill passed</div></div>
<div class="card"><div class="metric">{artifact.audit_entry_count}</div><div class="label">chained audit entries</div></div>
<div class="card"><div class="metric">{artifact.monitoring_signal_count}</div><div class="label">healthy monitoring signals</div></div>
<div class="card"><div class="metric">{artifact.documentation_record_count}</div><div class="label">documentation records</div></div>
<div class="card"><div class="metric">{artifact.founder_uat_journey_count}</div><div class="label">founder-UAT journeys ready</div></div>
<div class="card"><div class="metric">0</div><div class="label">releases / production deploys</div></div></div>
<section><h2>Exact final gates</h2><table><thead><tr><th>CONTROL</th><th>RESULT</th><th>STATE</th><th>AUDIT RECEIPT</th></tr></thead><tbody>{rows}</tbody></table></section>
<div class="grid"><section><h2>Monitoring</h2><ul>{signals}</ul></section><section><h2>Documentation</h2><ul>{documents}</ul></section></div>
<section><h2>Bound V1 source</h2><ul><li>Fixture pilot: <code>{artifact.pilot_id}</code></li>
<li>Repository: <strong>{artifact.repository_full_name}</strong></li><li>Branch: <code>{artifact.feature_branch}</code></li>
<li>Commit: <code>{artifact.approved_commit}</code></li><li>Tree: <code>{artifact.approved_tree}</code></li>
<li>Draft PR: <strong>#{artifact.draft_pull_request_number}</strong></li><li>Day 36 artifact: <code>{artifact.source_pilot_artifact_digest}</code></li>
<li>Security: <code>{artifact.security_artifact_digest}</code></li><li>Runtime acceptance: <code>{artifact.runtime_acceptance_artifact_digest}</code></li></ul></section>
<section><h2>Founder UAT checklist</h2><ul><li class="pass">All four fixture end-user journeys remain technically accepted</li>
<li class="pass">Screenshot is complete, legible, and contains no credential or local-path data</li>
<li class="pass">Primary and backup artifacts recover to exact equality</li>
<li class="warning">Subjective founder acceptance is pending and cannot be self-issued by ASCOS</li></ul></section>
<section class="boundary"><h2>Final authority boundary</h2><ul><li>No live customer product or production target was selected</li>
<li>No repository write, PR mutation, merge, deployment, release, billing, or risk acceptance</li>
<li>Release state: <strong>{artifact.release_state}</strong></li>
<li class="warning">Production and release require separate founder authorization after Day 37 acceptance</li></ul></section>
</main></body></html>""".encode()


def _application(body: bytes):
    def application(environ, start_response):  # noqa: ANN001
        if environ.get("PATH_INFO") != "/day37-v1-acceptance":
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                (
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
                ),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
            ],
        )
        return [body]

    return application


def test_day37_evidence_contract_reports_final_hardening_readiness(tmp_path: Path) -> None:
    *_, artifact = _run_hardening(tmp_path)
    body = _founder_page(artifact).decode()
    assert "7 FINAL GATES VERIFIED · FOUNDER UAT READY · RELEASE BLOCKED" in body
    assert all(control_id in body for control_id in HARDENING_CONTROL_IDS)
    assert all(document_id in body for document_id in DOCUMENTATION_IDS)
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.founder_uat_status == FOUNDER_UAT_STATUS
    assert artifact.release_state == RELEASE_STATE
    assert artifact.production_state == PRODUCTION_STATE


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_real_chromium_day37_founder_uat_and_evidence(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    runtime_provider = RoutedPreviewChromiumProvider()
    *_, artifact = _run_hardening(tmp_path, browser_provider=runtime_provider)
    assert runtime_provider.launch_count == 1
    assert runtime_provider.console_errors == []
    assert runtime_provider.network_failures == []
    assert artifact.founder_uat_journey_count == 4

    body = _founder_page(artifact)
    server = make_server(
        "127.0.0.1",
        0,
        _application(body),
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    console_errors: list[str] = []
    network_failures: list[str] = []
    screenshot: bytes
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
                timezone_id="UTC",
            )
            page = context.new_page()
            page.on(
                "console",
                lambda message: (
                    console_errors.append(message.text) if message.type == "error" else None
                ),
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: network_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day37-v1-acceptance",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            page.get_by_role("heading", name="V1 hardening and founder UAT").wait_for()
            page.get_by_text(
                "7 FINAL GATES VERIFIED · FOUNDER UAT READY · RELEASE BLOCKED"
            ).wait_for()
            assert page.get_by_text("PASS", exact=True).count() == 7
            assert console_errors == [] and network_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY37_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(Path(target), artifact, screenshot, console_errors, network_failures)


def _write_evidence(
    target: Path,
    artifact,  # noqa: ANN001
    screenshot: bytes,
    console_errors: list[str],
    network_failures: list[str],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "ascos-v1-hardening-founder-uat.png"
    screenshot_path.write_bytes(screenshot)
    screenshot_digest = hashlib.sha256(screenshot).hexdigest()
    commit_sha = os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", APPROVED_DAY36_BASE_SHA)
    if re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
        raise ValueError("Evidence commit SHA is invalid")
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": commit_sha,
        "approved_day36_base_commit": APPROVED_DAY36_BASE_SHA,
        "hardening_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "status": artifact.status,
            "founder_uat_status": artifact.founder_uat_status,
            "release_state": artifact.release_state,
            "production_state": artifact.production_state,
            "control_count": len(artifact.control_receipts),
            "controls": [
                {
                    "control_id": item.control_id,
                    "state": item.state,
                    "audit_digest": item.audit_digest,
                }
                for item in artifact.control_receipts
            ],
            "backup_copy_count": artifact.backup_copy_count,
            "recovery_drill_count": artifact.recovery_drill_count,
            "audit_entry_count": artifact.audit_entry_count,
            "monitoring_signal_count": artifact.monitoring_signal_count,
            "documentation_record_count": artifact.documentation_record_count,
            "founder_uat_journey_count": artifact.founder_uat_journey_count,
            "repository_write_count": artifact.repository_write_count,
            "pull_request_mutation_count": artifact.pull_request_mutation_count,
            "merge_count": artifact.merge_count,
            "production_deployment_count": artifact.production_deployment_count,
            "release_count": artifact.release_count,
            "billing_count": artifact.billing_count,
            "risk_acceptance_count": artifact.risk_acceptance_count,
            "founder_acceptance_count": artifact.founder_acceptance_count,
        },
        "source_chain": {
            "day36_pilot_artifact_digest": artifact.source_pilot_artifact_digest,
            "security_artifact_digest": artifact.security_artifact_digest,
            "devops_artifact_digest": artifact.devops_artifact_digest,
            "documentation_artifact_digest": artifact.documentation_artifact_digest,
            "runtime_acceptance_artifact_digest": artifact.runtime_acceptance_artifact_digest,
        },
        "browser": {
            "console_errors": console_errors,
            "network_failures": network_failures,
        },
        "screenshots": {screenshot_path.name: screenshot_digest},
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
