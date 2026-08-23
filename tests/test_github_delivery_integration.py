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

from runtime.github_delivery import (
    ARTIFACT_STATUS,
    DELIVERY_STATE,
    PILOT_STATUS,
    PULL_REQUEST_STATE,
)
from tests.test_github_delivery import _run_delivery


APPROVED_DAY32_BASE_SHA = "fa718dff0c1fa4f79f8f1d6dce92d88b94760a53"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _page(artifact) -> bytes:
    file_rows = "".join(
        f"<tr><td><code>{escape(item.path)}</code></td>"
        f"<td>{escape(item.owner_role)}</td><td><code>{item.content_digest[:16]}…</code></td></tr>"
        for item in artifact.reviewed_files
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ASCOS Day 33 controlled GitHub delivery</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:#0c3155;font-family:Inter,Arial,sans-serif}}
main{{max-width:1160px;margin:auto;padding:42px 28px 54px}}.eyebrow{{color:#2767bd;font-weight:800;letter-spacing:2px}}
h1{{font-size:42px;margin:12px 0}}p{{color:#55728f;font-size:18px;line-height:1.55}}.badge{{display:inline-block;background:#dff5e9;color:#087447;font-weight:800;padding:10px 16px;border-radius:24px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,section{{background:white;border:1px solid #d5e0ec;border-radius:16px;padding:20px}}
.metric{{font-size:34px;font-weight:900}}.label{{color:#607c97}}section{{margin:18px 0}}h2{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce5ee}}th{{font-size:12px;color:#607c97}}code{{font-size:12px}}.boundary{{border-left:5px solid #2767bd}}.warning{{color:#936100;font-weight:800}}.pass{{color:#087447;font-weight:800}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS AUTOMATIC IMPLEMENTATION · DAY 33</div>
<h1>Controlled GitHub delivery</h1>
<p>The exact Day 32 QA/Security-reviewed files were staged, committed once, pushed without force to the isolated feature branch, and opened as one draft pull request. Human review remains mandatory.</p>
<div class="badge">● EXACT COMMIT PUSHED · DRAFT PR OPEN · UNMERGED</div>
<div class="metrics">
<div class="card"><div class="metric">{len(artifact.reviewed_files)}</div><div class="label">reviewed paths</div></div>
<div class="card"><div class="metric">{artifact.commit_count}</div><div class="label">reviewed commit</div></div>
<div class="card"><div class="metric">{artifact.push_count}</div><div class="label">non-force push</div></div>
<div class="card"><div class="metric">{artifact.pull_request_count}</div><div class="label">draft pull request</div></div>
<div class="card"><div class="metric">0</div><div class="label">force pushes</div></div>
<div class="card"><div class="metric">0</div><div class="label">unreviewed paths</div></div>
<div class="card"><div class="metric">0</div><div class="label">secret exposure</div></div>
<div class="card"><div class="metric">0</div><div class="label">merge/deploy/release</div></div>
</div>
<section><h2>Exact delivery binding</h2><ul>
<li>Repository: <strong>{escape(artifact.repository_full_name)}</strong></li>
<li>Base: <code>{escape(artifact.base_branch)}</code> at <code>{artifact.base_commit}</code></li>
<li>Head: <code>{escape(artifact.feature_branch)}</code> at <code>{artifact.commit_sha}</code></li>
<li>Commit parent: <code>{artifact.commit_parent}</code></li>
<li>Remote branch: <code>{artifact.remote_branch_sha}</code></li>
</ul></section>
<section><h2>Reviewed files committed exactly</h2><table><thead><tr><th>PATH</th><th>OWNER</th><th>CONTENT DIGEST</th></tr></thead><tbody>{file_rows}</tbody></table></section>
<section><h2>Draft pull request</h2><ul>
<li>PR #{artifact.pull_request.number}: <strong>{escape(artifact.pull_request.title)}</strong></li>
<li>State: <span class="pass">{artifact.pull_request_state}</span></li>
<li>Base/head and exact commit are immutable in the receipt</li>
<li>Body digest: <code>{artifact.pull_request_body_digest}</code></li>
</ul></section>
<section><h2>Exact immutable source chain</h2><ul>
<li>Day 32 coding review: <code>{artifact.coding_review_artifact_digest}</code></li>
<li>Day 31 workspace: <code>{artifact.workspace_artifact_digest}</code></li>
<li>Day 30 orchestration: <code>{artifact.orchestration_artifact_digest}</code></li>
<li>Day 26 QA: <code>{artifact.qa_artifact_digest}</code></li>
<li>Day 27 Security: <code>{artifact.security_artifact_digest}</code></li>
</ul></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>One reviewed commit, one non-force feature-branch push, and one open draft PR only</li>
<li>No raw credential value, general command, unapproved network call, or unrelated path</li>
<li>No force push, protected-branch write, approval, merge, deployment, or release</li>
<li class="warning">No official pilot selected; preview deployment remains Day 34</li>
</ul></section>
</main></body></html>""".encode("utf-8")


def _application(body: bytes):
    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day33-github-delivery-evidence":
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]
        headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            (
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
            ),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
        ]
        start_response("200 OK", headers)
        return [body]

    return application


def test_day33_evidence_contract_reports_exact_draft_delivery(tmp_path: Path) -> None:
    *_, artifact = _run_delivery(tmp_path)
    body = _page(artifact).decode("utf-8")
    assert "EXACT COMMIT PUSHED · DRAFT PR OPEN · UNMERGED" in body
    assert artifact.commit_sha in body and artifact.base_commit in body
    assert artifact.feature_branch in body
    assert "No official pilot selected" in body
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pull_request_state == PULL_REQUEST_STATE
    assert artifact.delivery_state == DELIVERY_STATE
    assert artifact.pilot_status == PILOT_STATUS


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_real_chromium_day33_founder_evidence(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    *_, artifact = _run_delivery(tmp_path)
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
                f"http://127.0.0.1:{server.server_port}/day33-github-delivery-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            page.get_by_role("heading", name="Controlled GitHub delivery").wait_for()
            page.get_by_text("EXACT COMMIT PUSHED · DRAFT PR OPEN · UNMERGED").wait_for()
            page.get_by_text("OPEN_DRAFT_UNMERGED", exact=True).wait_for()
            assert page.get_by_text(artifact.commit_sha, exact=True).count() >= 1
            assert console_errors == [] and network_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY33_FOUNDER_EVIDENCE_DIR")
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
    screenshot_path = target / "controlled-github-delivery-verification.png"
    screenshot_path.write_bytes(screenshot)
    screenshot_digest = hashlib.sha256(screenshot).hexdigest()
    commit_sha = os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", APPROVED_DAY32_BASE_SHA)
    if re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
        raise ValueError("Evidence commit SHA is invalid")
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": commit_sha,
        "approved_day32_base_commit": APPROVED_DAY32_BASE_SHA,
        "source_chain": {
            "coding_review_artifact_digest": artifact.coding_review_artifact_digest,
            "workspace_artifact_digest": artifact.workspace_artifact_digest,
            "orchestration_artifact_digest": artifact.orchestration_artifact_digest,
            "qa_artifact_digest": artifact.qa_artifact_digest,
            "security_artifact_digest": artifact.security_artifact_digest,
        },
        "delivery_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "status": artifact.status,
            "delivery_state": artifact.delivery_state,
            "pull_request_state": artifact.pull_request_state,
            "reviewed_path_count": len(artifact.reviewed_files),
            "base_commit": artifact.base_commit,
            "commit_parent": artifact.commit_parent,
            "commit_sha": artifact.commit_sha,
            "commit_tree": artifact.commit_tree,
            "remote_branch_sha": artifact.remote_branch_sha,
            "draft_pull_request_number": artifact.pull_request.number,
            "commit_count": artifact.commit_count,
            "push_count": artifact.push_count,
            "pull_request_count": artifact.pull_request_count,
            "force_push_count": artifact.force_push_count,
            "secret_value_exposure_count": artifact.secret_value_exposure_count,
            "unapproved_network_call_count": artifact.unapproved_network_call_count,
            "unrelated_path_count": artifact.unrelated_path_count,
            "merge_count": artifact.merge_count,
            "deployment_count": artifact.deployment_count,
            "release_count": artifact.release_count,
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
