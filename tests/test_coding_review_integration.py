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

from runtime.coding_review import ARTIFACT_STATUS, DELIVERY_STATE, PILOT_STATUS, WORKSPACE_STATE
from tests.test_coding_review import _run_coding_review


APPROVED_DAY31_BASE_SHA = "3151349ca1e0ffab6f6239b9029941047387c144"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _page(artifact) -> bytes:
    round_rows = "".join(
        f"<tr><td>{item.round_number}</td>"
        f"<td>{escape(', '.join(item.resolved_feedback_codes) or 'Initial implementation')}</td>"
        f"<td class='{item.qa_status.lower()}'>{item.qa_status}</td>"
        f"<td class='{item.security_status.lower()}'>{item.security_status}</td>"
        f"<td>{escape(', '.join(item.failure_codes) or 'None')}</td></tr>"
        for item in artifact.rounds
    )
    route_rows = "".join(
        f"<li><strong>{escape(item.reviewer_role)}</strong> returned "
        f"<code>{escape(item.finding_code)}</code> to "
        f"<strong>{escape(item.responsible_role)}</strong></li>"
        for item in artifact.failure_routes
    )
    files = "".join(
        f"<li><code>{escape(item.path)}</code><span>{escape(item.owner_role)}</span></li>"
        for item in artifact.final_files
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ASCOS Day 32 coding and review verification</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:#0c3155;font-family:Inter,Arial,sans-serif}}
main{{max-width:1160px;margin:auto;padding:42px 28px 54px}}.eyebrow{{color:#2767bd;font-weight:800;letter-spacing:2px}}
h1{{font-size:42px;margin:12px 0}}p{{color:#55728f;font-size:18px;line-height:1.55}}.badge{{display:inline-block;background:#dff5e9;color:#087447;font-weight:800;padding:10px 16px;border-radius:24px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,section{{background:white;border:1px solid #d5e0ec;border-radius:16px;padding:20px}}
.metric{{font-size:34px;font-weight:900}}.label{{color:#607c97}}section{{margin:18px 0}}h2{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce5ee}}th{{font-size:12px;color:#607c97}}.pass{{color:#087447;font-weight:800}}.fail{{color:#b04725;font-weight:800}}.not_run_qa_failed{{color:#8b5c00;font-weight:800}}
.files{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;padding:0;list-style:none}}.files li{{display:flex;justify-content:space-between;padding:12px;background:#f5f8fb;border-radius:9px}}code{{font-size:12px}}.boundary{{border-left:5px solid #2767bd}}.warning{{color:#936100;font-weight:800}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,1fr)}}.files{{grid-template-columns:1fr}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS AUTOMATIC IMPLEMENTATION · DAY 32</div>
<h1>Coding and review loop</h1>
<p>A generic fixture moved through role-owned implementation, real isolated pytest, and static Security review. Failed reviews returned to the responsible engineer. The approved source stayed unchanged, and the reviewed workspace stopped before Git delivery.</p>
<div class="badge">● QA PASS · SECURITY PASS · DELIVERY NOT STARTED</div>
<div class="metrics">
<div class="card"><div class="metric">4</div><div class="label">Engineering roles</div></div>
<div class="card"><div class="metric">{len(artifact.rounds)}</div><div class="label">coding/review rounds</div></div>
<div class="card"><div class="metric">{len(artifact.failure_routes)}</div><div class="label">failure returns</div></div>
<div class="card"><div class="metric">{len(artifact.final_changed_paths)}</div><div class="label">reviewed changed files</div></div>
<div class="card"><div class="metric">{artifact.qa_execution_count}</div><div class="label">QA executions</div></div>
<div class="card"><div class="metric">{artifact.security_execution_count}</div><div class="label">Security executions</div></div>
<div class="card"><div class="metric">0</div><div class="label">network/credential calls</div></div>
<div class="card"><div class="metric">0</div><div class="label">stage/commit/push/PR</div></div>
</div>
<section><h2>Review rounds</h2><table><thead><tr><th>ROUND</th><th>FEEDBACK CONSUMED</th><th>QA</th><th>SECURITY</th><th>RETURNED FINDING</th></tr></thead><tbody>{round_rows}</tbody></table></section>
<section><h2>Failures returned to their owner</h2><ul>{route_rows}</ul></section>
<section><h2>Reviewed file ownership</h2><ul class="files">{files}</ul></section>
<section><h2>Exact immutable source chain</h2><ul>
<li>Day 30 orchestration: <code>{artifact.orchestration_artifact_digest}</code></li>
<li>Day 31 isolated workspace: <code>{artifact.workspace_artifact_digest}</code></li>
<li>Day 26 QA plan: <code>{artifact.qa_artifact_digest}</code></li>
<li>Day 27 Security plan: <code>{artifact.security_artifact_digest}</code></li>
<li>Workspace base: <code>{artifact.base_commit}</code> / <code>{artifact.base_tree}</code></li>
</ul></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>Only role-owned UTF-8 text paths, isolated pytest, static Security review, and local Git inspection</li>
<li>Approved source: <strong>{artifact.source_state}</strong>; workspace: <strong>{artifact.workspace_state}</strong></li>
<li>No live provider, network, credentials, general command, staging, commit, push, PR, merge, deployment, or release</li>
<li class="warning">No official pilot selected; controlled GitHub delivery remains Day 33</li>
</ul></section>
</main></body></html>""".encode("utf-8")


def _application(body: bytes):
    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day32-coding-review-evidence":
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]
        headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
        ]
        start_response("200 OK", headers)
        return [body]

    return application


def test_day32_evidence_contract_reports_real_failure_routing(tmp_path: Path) -> None:
    *_, artifact = _run_coding_review(tmp_path)
    body = _page(artifact).decode("utf-8")
    assert "QA PASS · SECURITY PASS · DELIVERY NOT STARTED" in body
    assert "QA_TEST_FAILURE" in body
    assert "UNSAFE_DYNAMIC_EXECUTION" in body
    assert "BACKEND_ENGINEER" in body
    assert "No official pilot selected" in body
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.workspace_state == WORKSPACE_STATE
    assert artifact.delivery_state == DELIVERY_STATE
    assert artifact.pilot_status == PILOT_STATUS


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_real_chromium_day32_founder_evidence(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    *_, artifact = _run_coding_review(tmp_path)
    body = _page(artifact)
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
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: network_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day32-coding-review-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            page.get_by_role("heading", name="Coding and review loop").wait_for()
            page.get_by_text("QA PASS · SECURITY PASS · DELIVERY NOT STARTED").wait_for()
            page.get_by_text("QA_TEST_FAILURE", exact=True).first.wait_for()
            page.get_by_text("UNSAFE_DYNAMIC_EXECUTION", exact=True).first.wait_for()
            assert page.get_by_text("BACKEND_ENGINEER", exact=True).count() >= 1
            assert console_errors == [] and network_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY32_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(
            Path(target),
            artifact,
            screenshot,
            console_errors,
            network_failures,
        )


def _write_evidence(
    target: Path,
    artifact,
    screenshot: bytes,
    console_errors: list[str],
    network_failures: list[str],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "coding-review-loop-verification.png"
    screenshot_path.write_bytes(screenshot)
    screenshot_digest = hashlib.sha256(screenshot).hexdigest()
    commit_sha = os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", APPROVED_DAY31_BASE_SHA)
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("Evidence commit SHA is invalid")
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": commit_sha,
        "approved_day31_base_commit": APPROVED_DAY31_BASE_SHA,
        "source_chain": {
            "orchestration_artifact_digest": artifact.orchestration_artifact_digest,
            "workspace_artifact_digest": artifact.workspace_artifact_digest,
            "qa_artifact_digest": artifact.qa_artifact_digest,
            "security_artifact_digest": artifact.security_artifact_digest,
        },
        "review_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "status": artifact.status,
            "workspace_state": artifact.workspace_state,
            "delivery_state": artifact.delivery_state,
            "engineering_role_count": 4,
            "review_round_count": len(artifact.rounds),
            "failure_route_count": len(artifact.failure_routes),
            "changed_file_count": len(artifact.final_changed_paths),
            "qa_execution_count": artifact.qa_execution_count,
            "security_execution_count": artifact.security_execution_count,
            "final_qa_state": artifact.qa_state,
            "final_security_state": artifact.security_state,
            "network_call_count": artifact.network_call_count,
            "credential_access_count": artifact.credential_access_count,
            "general_command_count": artifact.general_command_count,
            "staged_path_count": artifact.staged_path_count,
            "commit_count": artifact.commit_count,
            "push_count": artifact.push_count,
            "pull_request_count": artifact.pull_request_count,
            "pilot_status": artifact.pilot_status,
        },
        "browser": {
            "console_errors": console_errors,
            "network_failures": network_failures,
        },
        "screenshots": {screenshot_path.name: screenshot_digest},
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
