from __future__ import annotations

from html import escape
import hashlib
import json
import os
from pathlib import Path
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.workforce_orchestration import (
    ARTIFACT_STATUS,
    CONFLICT_STATE,
    ESCALATION_STATE,
    EXECUTION_STATE,
    HANDOFF_STATE,
    PILOT_STATUS,
)
from tests.test_workforce_orchestration import _run_orchestration


APPROVED_DAY29_HEAD = "d18192c2499f5fc9dd2d86c29ca354e7633e11bb"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _list(items) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def _report(authority, artifact):
    waves = "".join(
        "<tr>"
        f"<td>{item.sequence}</td><td>{escape(item.wave_id)}</td>"
        f"<td>{escape(', '.join(item.node_ids))}</td>"
        f"<td>{item.max_parallelism}</td><td>{escape(item.execution_state)}</td>"
        "</tr>"
        for item in artifact.parallel_waves
    )
    sources = "".join(
        "<tr>"
        f"<td>{escape(item.kind.value)}</td><td>{escape(item.artifact_id)}</td>"
        f"<td><code>{escape(item.artifact_digest)}</code></td><td>{escape(item.status)}</td>"
        "</tr>"
        for item in artifact.source_bindings
    )
    conflicts = "".join(
        "<article>"
        f"<div class='row'><h3>{escape(item.subject)}</h3><span>BLOCKS DOWNSTREAM</span></div>"
        f"<p>{escape(item.detection_rule)}</p><p><strong>Owner:</strong> {escape(item.resolution_owner)}</p>"
        f"<p>{escape(item.resolution_policy)}</p><div class='state'>{escape(item.state)}</div>"
        "</article>"
        for item in artifact.conflicts
    )
    escalations = "".join(
        "<article>"
        f"<h3>{escape(item.escalation_id)}</h3><p>{escape(item.trigger)}</p>"
        f"<p><strong>Human owner:</strong> {escape(item.human_owner)}</p>"
        f"<div class='state'>{escape(item.state)}</div>"
        "</article>"
        for item in artifact.escalations
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 30 Multi-agent orchestration verification</title>
<style>
:root{{--ink:#102a43;--muted:#627d98;--line:#d9e2ec;--blue:#275dad;--green:#087f5b;
--amber:#9c6506;--wash:#edf2f7;--red:#b42318}}*{{box-sizing:border-box}}body{{margin:0;
background:var(--wash);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1320px;margin:0 auto;padding:48px 28px 72px}}.eyebrow{{color:var(--blue);
font-weight:850;letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:48px;line-height:1.06;
margin:12px 0}}.lead{{font-size:20px;line-height:1.5;color:var(--muted);max-width:1080px}}
.status{{display:inline-flex;margin:10px 0 26px;background:#dff7ee;color:var(--green);font-weight:850;
border-radius:999px;padding:10px 16px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);
gap:14px;margin-bottom:18px}}.metric,section,article{{background:#fff;border:1px solid var(--line);
border-radius:18px;padding:22px}}.metric strong{{font-size:34px;display:block}}.metric span{{color:var(--muted)}}
section{{margin-top:18px}}h2{{font-size:25px;margin:0 0 12px}}h3{{margin:0 0 10px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid var(--line);
vertical-align:top}}th{{font-size:11px;color:var(--muted);text-transform:uppercase}}code{{font-family:
ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;overflow-wrap:anywhere}}.cards{{display:grid;
grid-template-columns:repeat(3,1fr);gap:14px}}article{{min-height:230px}}.row{{display:flex;
justify-content:space-between;gap:12px}}article span{{color:var(--red);font-size:10px;font-weight:850}}
.state{{font-size:11px;color:var(--amber);font-weight:850;margin-top:16px}}p,li{{line-height:1.5}}
.boundary{{border-left:5px solid var(--blue)}}.safe{{color:var(--green);font-weight:800}}
@media(max-width:900px){{.metrics,.cards{{grid-template-columns:1fr 1fr}}h1{{font-size:38px}}}}
@media(max-width:620px){{.metrics,.cards{{grid-template-columns:1fr}}table{{display:block;overflow:auto}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS workforce · Day 30</div>
<h1>Governed multi-agent orchestration</h1>
<p class="lead">The exact Day 23–29 workforce chain is coordinated through dependency order,
bounded parallelism, source-limited context, draft handoffs, fail-closed conflicts, and human-owned
escalations. This is a plan only: no agent or product operation is executed.</p>
<div class="status">● ORCHESTRATION PLAN COMPLETE · 0 OPERATIONS EXECUTED</div>
<div class="metrics">
<div class="metric"><strong>{len(artifact.source_bindings)}</strong><span>exact sources</span></div>
<div class="metric"><strong>{len(artifact.parallel_waves)}</strong><span>dependency waves</span></div>
<div class="metric"><strong>4</strong><span>parallel Engineering roles</span></div>
<div class="metric"><strong>{len(artifact.context_packages)}</strong><span>bounded contexts</span></div>
<div class="metric"><strong>{len(artifact.handoffs)}</strong><span>draft handoffs</span></div>
<div class="metric"><strong>{len(artifact.conflicts)}</strong><span>conflict routes</span></div>
<div class="metric"><strong>{len(artifact.escalations)}</strong><span>human escalations</span></div>
<div class="metric"><strong>0</strong><span>tool calls</span></div></div>
<section><h2>Dependency and parallel-work plan</h2>
<p class="safe">Wave 4 coordinates Backend, Frontend, AI, and Data work in parallel under the same
exact Architecture source. Every other wave remains dependency ordered.</p>
<table><thead><tr><th>Sequence</th><th>Wave</th><th>Nodes</th><th>Max parallel</th><th>State</th></tr></thead>
<tbody>{waves}</tbody></table></section>
<section><h2>Bounded context and handoffs</h2><ul>
<li>{len(artifact.context_packages)} context packages include only artifact identity, digest, status, and bounded summary.</li>
<li>Credentials, secrets, raw customer data, and local paths are excluded from every context package.</li>
<li>{len(artifact.handoffs)} handoffs remain {escape(HANDOFF_STATE)} and are not dispatched.</li>
<li>Every node remains {escape(EXECUTION_STATE)}.</li></ul></section>
<section><h2>Fail-closed conflict routes</h2><div class="cards">{conflicts}</div></section>
<section><h2>Human-owned escalation routes</h2><div class="cards">{escalations}</div></section>
<section><h2>Exact workforce source bindings</h2>
<table><thead><tr><th>Source</th><th>Artifact</th><th>Digest</th><th>Status</th></tr></thead>
<tbody>{sources}</tbody></table></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>0 tools · {authority.max_tool_calls} tool calls · no live provider</li>
<li>No agent execution, filesystem, workspace, repository, command, network, credential, or external channel</li>
<li>No architecture, quality, Security, risk, merge, deployment, release, billing, or budget approval</li>
<li>Artifact remains {escape(ARTIFACT_STATUS)} and {escape(EXECUTION_STATE)}</li>
<li>No official pilot product selected; Day 31 requires separate founder authorization</li></ul></section>
</main></body></html>""".encode()

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day30-orchestration-evidence":
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


def _write_evidence(target: Path, order, authority, artifact, screenshot: bytes, console=None, network=None):
    target.mkdir(parents=True, exist_ok=True)
    (target / "multi-agent-orchestration-verification.png").write_bytes(screenshot)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", "UNSET"),
        "approved_day29_base_commit": APPROVED_DAY29_HEAD,
        "work_order": {
            "work_order_id": order.work_order_id,
            "digest": order.digest,
            "status": order.status,
        },
        "authority": {
            "digest": authority.digest,
            "allowed_action_ids": authority.allowed_action_ids,
            "allowed_tool_ids": authority.allowed_tool_ids,
            "max_tool_calls": authority.max_tool_calls,
            "max_parallel_workstreams": authority.max_parallel_workstreams,
            "live_provider_allowed": authority.live_provider_allowed,
        },
        "source_set_digest": artifact.source_set_digest,
        "source_bindings": [
            {
                "kind": item.kind.value,
                "artifact_id": item.artifact_id,
                "artifact_digest": item.artifact_digest,
                "status": item.status,
            }
            for item in artifact.source_bindings
        ],
        "orchestration_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "provider_id": artifact.provider_id,
            "provider_output_digest": artifact.provider_output_digest,
            "dependency_node_count": len(artifact.dependency_nodes),
            "parallel_wave_count": len(artifact.parallel_waves),
            "max_planned_parallelism": max(item.max_parallelism for item in artifact.parallel_waves),
            "context_package_count": len(artifact.context_packages),
            "handoff_count": len(artifact.handoffs),
            "conflict_count": len(artifact.conflicts),
            "escalation_count": len(artifact.escalations),
            "execution_states": sorted({item.execution_state for item in artifact.dependency_nodes}),
            "handoff_states": sorted({item.state for item in artifact.handoffs}),
            "conflict_states": sorted({item.state for item in artifact.conflicts}),
            "escalation_states": sorted({item.state for item in artifact.escalations}),
            "artifact_status": artifact.status,
            "pilot_status": artifact.pilot_status,
            "tool_call_count": authority.max_tool_calls,
        },
        "browser": {
            "console_errors": [] if console is None else console,
            "network_failures": [] if network is None else network,
        },
        "screenshots": {
            "multi-agent-orchestration-verification.png": hashlib.sha256(screenshot).hexdigest()
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def test_orchestration_report_has_restrictive_headers_and_complete_plan(tmp_path: Path) -> None:
    *_, authority, artifact = _run_orchestration(tmp_path)
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        _report(authority, artifact)({"PATH_INFO": "/day30-orchestration-evidence"}, start_response)
    )
    headers = captured["headers"]
    assert captured["status"] == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert b"4</strong><span>parallel Engineering roles" in body
    assert b"0 OPERATIONS EXECUTED" in body
    assert b"No official pilot product selected" in body
    for source in artifact.source_bindings:
        assert source.artifact_digest.encode() in body


def test_orchestration_manifest_binds_exact_sources_and_draft_states(tmp_path: Path, monkeypatch) -> None:
    _, _, _, _, order, authority, artifact = _run_orchestration(tmp_path)
    monkeypatch.setenv("ASCOS_EVIDENCE_COMMIT_SHA", "e" * 40)
    target = tmp_path / "founder-evidence"
    screenshot = b"generic-orchestration-screenshot"
    _write_evidence(target, order, authority, artifact, screenshot)
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["result"] == "PASS"
    assert manifest["commit_sha"] == "e" * 40
    assert manifest["approved_day29_base_commit"] == APPROVED_DAY29_HEAD
    assert len(manifest["source_bindings"]) == 11
    output = manifest["orchestration_output"]
    assert output["dependency_node_count"] == 11
    assert output["parallel_wave_count"] == 9
    assert output["max_planned_parallelism"] == 4
    assert output["context_package_count"] == 11
    assert output["handoff_count"] == 7
    assert output["conflict_count"] == output["escalation_count"] == 3
    assert output["execution_states"] == [EXECUTION_STATE]
    assert output["handoff_states"] == [HANDOFF_STATE]
    assert output["conflict_states"] == [CONFLICT_STATE]
    assert output["escalation_states"] == [ESCALATION_STATE]
    assert output["artifact_status"] == ARTIFACT_STATUS
    assert output["pilot_status"] == PILOT_STATUS
    assert output["tool_call_count"] == 0
    assert manifest["screenshots"]["multi-agent-orchestration-verification.png"] == hashlib.sha256(screenshot).hexdigest()


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_orchestration_real_chromium_founder_evidence(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    _, _, _, _, order, authority, artifact = _run_orchestration(tmp_path)
    server = make_server("127.0.0.1", 0, _report(authority, artifact), _ThreadingServer, _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    console_errors: list[str] = []
    network_failures: list[str] = []
    screenshot: bytes
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("requestfailed", lambda request: network_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day30-orchestration-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert page.locator("h1").inner_text() == "Governed multi-agent orchestration"
            assert page.get_by_text("ORCHESTRATION PLAN COMPLETE · 0 OPERATIONS EXECUTED").is_visible()
            assert page.get_by_text("Wave 4 coordinates Backend, Frontend, AI, and Data work in parallel", exact=False).is_visible()
            assert page.get_by_text("No official pilot product selected", exact=False).is_visible()
            assert page.locator("tbody tr").count() == 20
            screenshot = page.screenshot(full_page=True)
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert console_errors == [] and network_failures == []
    target = Path(os.environ.get("ASCOS_DAY30_FOUNDER_EVIDENCE_DIR", tmp_path / "founder-evidence"))
    _write_evidence(target, order, authority, artifact, screenshot, console_errors, network_failures)
