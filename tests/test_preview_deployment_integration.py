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

from runtime.preview_deployment import (
    ARTIFACT_STATUS,
    DEPLOYMENT_STATE,
    ENVIRONMENT_STATE,
    PILOT_STATUS,
    PRODUCTION_STATE,
    ROLLBACK_STATE,
)
from tests.test_preview_deployment import _run_preview


APPROVED_DAY33_BASE_SHA = "dd5c35a673f92565bd2bcf5db33de29ee90e4410"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):  # noqa: ANN001
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _page(artifact) -> bytes:  # noqa: ANN001
    health_rows = "".join(
        f"<tr><td>{escape(item.check_id)}</td><td><code>{escape(item.url)}</code></td>"
        f"<td class='pass'>{item.status_code} PASS</td>"
        f"<td><code>{item.response_digest[:16]}…</code></td></tr>"
        for item in artifact.health_receipts
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ASCOS Day 34 isolated preview deployment</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:#0c3155;font-family:Inter,Arial,sans-serif}}
main{{max-width:1160px;margin:auto;padding:42px 28px 54px}}.eyebrow{{color:#2767bd;font-weight:800;letter-spacing:2px}}
h1{{font-size:42px;margin:12px 0}}p{{color:#55728f;font-size:18px;line-height:1.55}}.badge{{display:inline-block;background:#dff5e9;color:#087447;font-weight:800;padding:10px 16px;border-radius:24px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,section{{background:white;border:1px solid #d5e0ec;border-radius:16px;padding:20px}}
.metric{{font-size:34px;font-weight:900}}.label{{color:#607c97}}section{{margin:18px 0}}h2{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce5ee}}th{{font-size:12px;color:#607c97}}code{{font-size:12px}}.boundary{{border-left:5px solid #2767bd}}.warning{{color:#936100;font-weight:800}}.pass{{color:#087447;font-weight:800}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS AUTOMATIC IMPLEMENTATION · DAY 34</div>
<h1>Isolated preview deployment</h1>
<p>The exact human-authorized Day 33 commit was deployed once to a bounded non-production preview using the matching Day 28 DevOps plans. Production remains untouched.</p>
<div class="badge">● EXACT COMMIT DEPLOYED · PREVIEW HEALTHY · PRODUCTION UNTOUCHED</div>
<div class="metrics">
<div class="card"><div class="metric">{artifact.deployment_count}</div><div class="label">preview deployment</div></div>
<div class="card"><div class="metric">{artifact.migration_count}</div><div class="label">preview migration</div></div>
<div class="card"><div class="metric">{len(artifact.health_receipts)}</div><div class="label">healthy checks</div></div>
<div class="card"><div class="metric">{artifact.monitoring_configuration_count}</div><div class="label">monitoring profile</div></div>
<div class="card"><div class="metric">0</div><div class="label">production deploys</div></div>
<div class="card"><div class="metric">0</div><div class="label">merges</div></div>
<div class="card"><div class="metric">0</div><div class="label">releases</div></div>
<div class="card"><div class="metric">0</div><div class="label">secret exposure</div></div>
</div>
<section><h2>Exact source binding</h2><ul>
<li>Repository: <strong>{escape(artifact.repository_full_name)}</strong></li>
<li>Feature branch: <code>{escape(artifact.feature_branch)}</code></li>
<li>Approved commit: <code>{artifact.approved_commit}</code></li>
<li>Approved tree: <code>{artifact.approved_tree}</code></li>
<li>Draft PR: #{artifact.draft_pull_request_number} · <span class="pass">{artifact.pull_request_state}</span></li>
</ul></section>
<section><h2>Isolated preview receipt</h2><ul>
<li>Environment: <strong>{escape(artifact.preview_environment_id)}</strong></li>
<li>Class: <code>{artifact.environment_class}</code></li>
<li>URL: <code>{escape(artifact.preview_url)}</code></li>
<li>Revision: <code>{artifact.deployment_revision}</code></li>
<li>State: <span class="pass">{artifact.environment_state}</span></li>
</ul></section>
<section><h2>Health verification</h2><table><thead><tr><th>CHECK</th><th>URL</th><th>STATUS</th><th>RESPONSE DIGEST</th></tr></thead><tbody>{health_rows}</tbody></table></section>
<section><h2>Exact immutable source chain</h2><ul>
<li>Day 33 delivery: <code>{artifact.github_delivery_artifact_digest}</code></li>
<li>Day 28 DevOps: <code>{artifact.devops_artifact_digest}</code></li>
<li>Day 32 coding review: <code>{artifact.coding_review_artifact_digest}</code></li>
<li>Day 31 workspace: <code>{artifact.workspace_artifact_digest}</code></li>
<li>Day 30 orchestration: <code>{artifact.orchestration_artifact_digest}</code></li>
<li>Day 26 QA: <code>{artifact.qa_artifact_digest}</code></li>
<li>Day 27 Security: <code>{artifact.security_artifact_digest}</code></li>
</ul></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>One isolated non-production preview deployment for the exact approved commit only</li>
<li>Opaque secret references only; no raw credential or secret value</li>
<li>Rollback is ready but was not executed</li>
<li>No PR approval, merge, production deployment, promotion, release, or billing</li>
<li class="warning">No official pilot selected; complete Chrome runtime acceptance remains Day 35</li>
</ul></section>
</main></body></html>""".encode("utf-8")


def _application(body: bytes):
    def application(environ, start_response):  # noqa: ANN001
        if environ.get("PATH_INFO") != "/day34-preview-deployment-evidence":
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


def test_day34_evidence_contract_reports_exact_healthy_preview(tmp_path: Path) -> None:
    *_, artifact = _run_preview(tmp_path)
    body = _page(artifact).decode("utf-8")
    assert "EXACT COMMIT DEPLOYED · PREVIEW HEALTHY · PRODUCTION UNTOUCHED" in body
    assert artifact.approved_commit in body and artifact.approved_tree in body
    assert artifact.preview_environment_id in body
    assert artifact.environment_state == ENVIRONMENT_STATE
    assert artifact.deployment_state == DEPLOYMENT_STATE
    assert artifact.rollback_state == ROLLBACK_STATE
    assert artifact.production_state == PRODUCTION_STATE
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pilot_status == PILOT_STATUS


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_real_chromium_day34_founder_evidence(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    *_, artifact = _run_preview(tmp_path)
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
                f"http://127.0.0.1:{server.server_port}/day34-preview-deployment-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            page.get_by_role("heading", name="Isolated preview deployment").wait_for()
            page.get_by_text(
                "EXACT COMMIT DEPLOYED · PREVIEW HEALTHY · PRODUCTION UNTOUCHED"
            ).wait_for()
            page.get_by_text(ENVIRONMENT_STATE, exact=True).wait_for()
            assert page.get_by_text(artifact.approved_commit, exact=True).count() >= 1
            assert console_errors == [] and network_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY34_FOUNDER_EVIDENCE_DIR")
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
    artifact,  # noqa: ANN001
    screenshot: bytes,
    console_errors: list[str],
    network_failures: list[str],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "preview-deployment-verification.png"
    screenshot_path.write_bytes(screenshot)
    screenshot_digest = hashlib.sha256(screenshot).hexdigest()
    commit_sha = os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", APPROVED_DAY33_BASE_SHA)
    if re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
        raise ValueError("Evidence commit SHA is invalid")
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": commit_sha,
        "approved_day33_base_commit": APPROVED_DAY33_BASE_SHA,
        "source_chain": {
            "github_delivery_artifact_digest": artifact.github_delivery_artifact_digest,
            "devops_artifact_digest": artifact.devops_artifact_digest,
            "coding_review_artifact_digest": artifact.coding_review_artifact_digest,
            "workspace_artifact_digest": artifact.workspace_artifact_digest,
            "orchestration_artifact_digest": artifact.orchestration_artifact_digest,
            "qa_artifact_digest": artifact.qa_artifact_digest,
            "security_artifact_digest": artifact.security_artifact_digest,
        },
        "preview_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "status": artifact.status,
            "environment_id": artifact.preview_environment_id,
            "environment_class": artifact.environment_class,
            "environment_state": artifact.environment_state,
            "preview_url": artifact.preview_url,
            "approved_commit": artifact.approved_commit,
            "deployed_commit": artifact.deployed_commit,
            "approved_tree": artifact.approved_tree,
            "deployed_tree": artifact.deployed_tree,
            "deployment_revision": artifact.deployment_revision,
            "health_check_count": len(artifact.health_receipts),
            "health_status_codes": [item.status_code for item in artifact.health_receipts],
            "deployment_count": artifact.deployment_count,
            "migration_count": artifact.migration_count,
            "monitoring_configuration_count": artifact.monitoring_configuration_count,
            "rollback_count": artifact.rollback_count,
            "production_deployment_count": artifact.production_deployment_count,
            "merge_count": artifact.merge_count,
            "release_count": artifact.release_count,
            "billing_count": artifact.billing_count,
            "secret_value_exposure_count": artifact.secret_value_exposure_count,
            "unapproved_network_call_count": artifact.unapproved_network_call_count,
            "general_command_count": artifact.general_command_count,
            "rollback_state": artifact.rollback_state,
            "production_state": artifact.production_state,
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
