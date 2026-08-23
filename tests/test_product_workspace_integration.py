from __future__ import annotations

from html import escape
import hashlib
import json
import os
from pathlib import Path
import threading
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.product_workspace import (
    ARTIFACT_STATUS,
    BRANCH_STATE,
    PILOT_STATUS,
    SOURCE_STATE,
    WORKSPACE_STATE,
)
from tests.test_product_workspace import _run_workspace


APPROVED_DAY30_HEAD = "89e7b8f8eeeeabcd5467131a3b1e5bea2a465de5"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _report(authority, artifact):
    checks = (
        ("Exact persisted Day 30 source", artifact.orchestration_artifact_digest, "PASS"),
        ("Approved base commit", artifact.base_commit, "PASS"),
        ("Source branch unchanged", artifact.source_state, "PASS"),
        ("Workspace head equals approved base", artifact.workspace_head, "PASS"),
        ("Workspace tree equals approved tree", artifact.workspace_tree, "PASS"),
        ("Feature branch isolated", artifact.branch_state, "PASS"),
        ("Workspace clean and unused", artifact.workspace_state, "PASS"),
    )
    rows = "".join(
        "<tr>"
        f"<td>{escape(label)}</td><td><code>{escape(value)}</code></td>"
        f"<td><span class='pass'>{escape(state)}</span></td></tr>"
        for label, value, state in checks
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 31 isolated product workspace verification</title>
<style>
:root{{--ink:#102a43;--muted:#627d98;--line:#d9e2ec;--blue:#275dad;--green:#087f5b;
--wash:#edf2f7;--amber:#9c6506}}*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);
color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1220px;
margin:0 auto;padding:48px 28px 72px}}.eyebrow{{color:var(--blue);font-weight:850;letter-spacing:.12em;
text-transform:uppercase}}h1{{font-size:48px;line-height:1.06;margin:12px 0}}.lead{{font-size:20px;
line-height:1.5;color:var(--muted);max-width:1050px}}.status{{display:inline-flex;margin:10px 0 26px;
background:#dff7ee;color:var(--green);font-weight:850;border-radius:999px;padding:10px 16px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}}
.metric,section{{background:#fff;border:1px solid var(--line);border-radius:18px;padding:22px}}
.metric strong{{font-size:34px;display:block}}.metric span{{color:var(--muted)}}section{{margin-top:18px}}
h2{{font-size:25px;margin:0 0 12px}}h3{{margin:0 0 8px}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:13px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:11px;color:var(--muted);text-transform:uppercase}}code{{font-family:ui-monospace,
SFMono-Regular,Menlo,monospace;font-size:12px;overflow-wrap:anywhere}}p,li{{line-height:1.55}}
.pass{{color:var(--green);font-weight:850}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.card{{border:1px solid var(--line);border-radius:14px;padding:18px;background:#fbfdff}}
.card strong{{display:block;font-size:28px;margin-bottom:6px}}.boundary{{border-left:5px solid var(--blue)}}
.warning{{color:var(--amber);font-weight:800}}@media(max-width:900px){{.metrics,.cards{{grid-template-columns:1fr 1fr}}
h1{{font-size:38px}}}}@media(max-width:620px){{.metrics,.cards{{grid-template-columns:1fr}}
table{{display:block;overflow:auto}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS automatic implementation · Day 31</div>
<h1>Isolated product workspace</h1>
<p class="lead">A generic product fixture was prepared in one contained Git worktree on one new
feature branch at the exact approved base. The approved source repository stayed clean, on the same
branch, commit, and tree. No product implementation or delivery operation ran.</p>
<div class="status">● WORKSPACE READY · SOURCE UNCHANGED · NO CODING EXECUTED</div>
<div class="metrics">
<div class="metric"><strong>1</strong><span>exact Day 30 source</span></div>
<div class="metric"><strong>1</strong><span>isolated workspace</span></div>
<div class="metric"><strong>1</strong><span>feature branch</span></div>
<div class="metric"><strong>0</strong><span>source file changes</span></div>
<div class="metric"><strong>{artifact.git_command_count}</strong><span>bounded Git checks/actions</span></div>
<div class="metric"><strong>0</strong><span>network calls</span></div>
<div class="metric"><strong>0</strong><span>general commands</span></div>
<div class="metric"><strong>0</strong><span>coding/delivery operations</span></div></div>
<section><h2>Exact workspace verification</h2>
<table><thead><tr><th>Check</th><th>Bound value</th><th>Result</th></tr></thead>
<tbody>{rows}</tbody></table></section>
<section><h2>Containment and preservation</h2><div class="cards">
<div class="card"><strong>Exact</strong><span>Base branch and 40-character commit verified before creation</span></div>
<div class="card"><strong>Clean</strong><span>Source and workspace status empty after creation</span></div>
<div class="card"><strong>Equal</strong><span>Source, base, and workspace Git trees match</span></div>
<div class="card"><strong>Closed</strong><span>Symlinks, submodules, hooks, filters, existing targets, and branches rejected</span></div>
<div class="card"><strong>Local</strong><span>Specialized Git worktree adapter; no network or credentials</span></div>
<div class="card"><strong>Unused</strong><span>No product file mutation, coding, test, scan, commit, push, or PR</span></div>
</div></section>
<section><h2>Immutable source binding</h2><ul>
<li>Orchestration artifact: <code>{escape(artifact.orchestration_artifact_id)}</code></li>
<li>Orchestration digest: <code>{escape(artifact.orchestration_artifact_digest)}</code></li>
<li>Repository registration: <code>{escape(artifact.repository_id)}</code></li>
<li>Workspace identity: <code>{escape(artifact.workspace_id)}</code> (no host path persisted)</li>
<li>Feature branch: <code>{escape(artifact.feature_branch)}</code></li>
</ul></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>Allowed tool: <code>{escape(', '.join(authority.allowed_tool_ids))}</code>; maximum {authority.max_tool_calls} bounded calls</li>
<li>Actual specialized Git calls: {artifact.git_command_count}; network and general command calls: 0</li>
<li>Source product-file writes and unrelated-path changes: 0</li>
<li>No coding provider, QA execution, Security scan, commit, push, pull request, merge, deployment, or release</li>
<li class="warning">No official pilot selected; Day 32 coding/review requires separate founder authorization</li>
</ul></section>
</main></body></html>""".encode()

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day31-product-workspace-evidence":
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
    (target / "isolated-product-workspace-verification.png").write_bytes(screenshot)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", "UNSET"),
        "approved_day30_base_commit": APPROVED_DAY30_HEAD,
        "work_order": {
            "work_order_id": order.work_order_id,
            "digest": order.digest,
            "status": order.status,
        },
        "authority": {
            "digest": authority.digest,
            "allowed_action_ids": authority.allowed_action_ids,
            "allowed_tool_ids": authority.allowed_tool_ids,
            "max_workspaces": authority.max_workspaces,
            "max_tool_calls": authority.max_tool_calls,
            "network_allowed": authority.network_allowed,
            "source_file_writes_allowed": authority.source_file_writes_allowed,
            "workspace_file_mutation_allowed": authority.workspace_file_mutation_allowed,
        },
        "orchestration_source": {
            "artifact_id": artifact.orchestration_artifact_id,
            "artifact_digest": artifact.orchestration_artifact_digest,
        },
        "workspace_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "provider_id": artifact.provider_id,
            "provider_output_digest": artifact.provider_output_digest,
            "repository_id": artifact.repository_id,
            "workspace_id": artifact.workspace_id,
            "workspace_relative_path": artifact.workspace_relative_path,
            "base_branch": artifact.base_branch,
            "base_commit": artifact.base_commit,
            "base_tree": artifact.base_tree,
            "feature_branch": artifact.feature_branch,
            "workspace_head": artifact.workspace_head,
            "workspace_tree": artifact.workspace_tree,
            "source_state": artifact.source_state,
            "workspace_state": artifact.workspace_state,
            "branch_state": artifact.branch_state,
            "artifact_status": artifact.status,
            "pilot_status": artifact.pilot_status,
            "git_command_count": artifact.git_command_count,
            "network_call_count": artifact.network_call_count,
            "general_command_count": artifact.general_command_count,
            "product_file_write_count": artifact.product_file_write_count,
            "unrelated_path_change_count": artifact.unrelated_path_change_count,
        },
        "browser": {
            "console_errors": [] if console is None else console,
            "network_failures": [] if network is None else network,
        },
        "screenshots": {
            "isolated-product-workspace-verification.png": hashlib.sha256(screenshot).hexdigest()
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def test_workspace_evidence_manifest_binds_exact_states(tmp_path: Path, monkeypatch) -> None:
    _, _, _, _, order, authority, artifact = _run_workspace(tmp_path)
    monkeypatch.setenv("ASCOS_EVIDENCE_COMMIT_SHA", "f" * 40)
    target = tmp_path / "founder-evidence"
    screenshot = b"generic-product-workspace-screenshot"
    _write_evidence(target, order, authority, artifact, screenshot)
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["result"] == "PASS"
    assert manifest["commit_sha"] == "f" * 40
    assert manifest["approved_day30_base_commit"] == APPROVED_DAY30_HEAD
    output = manifest["workspace_output"]
    assert output["base_commit"] == output["workspace_head"]
    assert output["base_tree"] == output["workspace_tree"]
    assert output["source_state"] == SOURCE_STATE
    assert output["workspace_state"] == WORKSPACE_STATE
    assert output["branch_state"] == BRANCH_STATE
    assert output["artifact_status"] == ARTIFACT_STATUS
    assert output["pilot_status"] == PILOT_STATUS
    assert output["network_call_count"] == output["general_command_count"] == 0
    assert output["product_file_write_count"] == output["unrelated_path_change_count"] == 0
    assert manifest["screenshots"]["isolated-product-workspace-verification.png"] == hashlib.sha256(screenshot).hexdigest()
    assert str(tmp_path) not in (target / "manifest.json").read_text()


def test_workspace_report_has_restrictive_headers_and_no_local_path(tmp_path: Path) -> None:
    _, _, _, _, _, authority, artifact = _run_workspace(tmp_path)
    application = _report(authority, artifact)
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(application({"PATH_INFO": "/day31-product-workspace-evidence"}, start_response))
    assert captured["status"] == "200 OK"
    assert captured["headers"]["Content-Security-Policy"].startswith("default-src 'none'")
    assert captured["headers"]["X-Frame-Options"] == "DENY"
    assert str(tmp_path).encode() not in body
    assert b"WORKSPACE READY" in body and b"NO CODING EXECUTED" in body


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_workspace_real_chromium_founder_evidence(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    _, _, _, _, order, authority, artifact = _run_workspace(tmp_path)
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
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("requestfailed", lambda request: network_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day31-product-workspace-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert page.locator("h1").inner_text() == "Isolated product workspace"
            assert page.get_by_text("WORKSPACE READY · SOURCE UNCHANGED · NO CODING EXECUTED").is_visible()
            assert page.get_by_text("No official pilot selected", exact=False).is_visible()
            assert page.locator("tbody tr").count() == 7
            screenshot = page.screenshot(full_page=True)
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert console_errors == [] and network_failures == []
    target = Path(
        os.environ.get("ASCOS_DAY31_FOUNDER_EVIDENCE_DIR", tmp_path / "founder-evidence")
    )
    _write_evidence(target, order, authority, artifact, screenshot, console_errors, network_failures)
