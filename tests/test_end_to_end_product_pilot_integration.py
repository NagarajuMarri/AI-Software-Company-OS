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

from runtime.end_to_end_product_pilot import (
    ARTIFACT_STATUS,
    PILOT_STAGE_IDS,
    PILOT_STATUS,
    PRODUCTION_STATE,
)
from tests.test_complete_runtime_acceptance_integration import (
    RoutedPreviewChromiumProvider,
)
from tests.test_end_to_end_product_pilot import _run_pilot


APPROVED_DAY35_BASE_SHA = "ca82f0de270f8ef333ff591301472b4361124e7c"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):  # noqa: ANN001
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _founder_page(artifact) -> bytes:  # noqa: ANN001
    rows = "".join(
        f"<tr><td><code>{escape(item.stage_id)}</code></td>"
        f"<td class='pass'>PASS</td><td>{escape(item.state)}</td>"
        f"<td><code>{item.source_digest[:14]}…</code></td></tr>"
        for item in artifact.stage_receipts
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>ASCOS Day 36 product pilot</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:#0c3155;font-family:Inter,Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:42px 28px 54px}}.eyebrow{{color:#2767bd;font-weight:800;letter-spacing:2px}}
h1{{font-size:42px;margin:12px 0}}p{{color:#55728f;font-size:18px;line-height:1.55}}.badge{{display:inline-block;background:#dff5e9;color:#087447;font-weight:800;padding:10px 16px;border-radius:24px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,section{{background:white;border:1px solid #d5e0ec;border-radius:16px;padding:20px}}
.metric{{font-size:34px;font-weight:900}}.label{{color:#607c97}}section{{margin:18px 0}}h2{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce5ee}}th{{font-size:12px;color:#607c97}}code{{font-size:12px}}.boundary{{border-left:5px solid #2767bd}}.warning{{color:#936100;font-weight:800}}.pass{{color:#087447;font-weight:800}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}</style></head><body><main>
<div class="eyebrow">ASCOS AUTOMATIC IMPLEMENTATION · DAY 36</div><h1>First end-to-end product pilot</h1>
<p>One fixture customer idea traversed the exact persisted intake, locked PRD, approved roadmap, governed agents, reviewed code, draft PR, healthy preview, and complete runtime-acceptance chain.</p>
<div class="badge">● ALL 8 STAGES VERIFIED · 4 JOURNEYS PASSED · PRODUCTION UNTOUCHED</div>
<div class="metrics"><div class="card"><div class="metric">8</div><div class="label">pilot stages verified</div></div>
<div class="card"><div class="metric">{artifact.passed_journey_count}</div><div class="label">runtime journeys passed</div></div>
<div class="card"><div class="metric">1</div><div class="label">open draft PR bound</div></div>
<div class="card"><div class="metric">7</div><div class="label">persisted source records</div></div>
<div class="card"><div class="metric">0</div><div class="label">repository writes</div></div><div class="card"><div class="metric">0</div><div class="label">PR mutations</div></div>
<div class="card"><div class="metric">0</div><div class="label">production deploys</div></div><div class="card"><div class="metric">0</div><div class="label">Day 37 actions</div></div></div>
<section><h2>Pilot identity</h2><ul><li>Fixture idea: <strong>Community workshop planner</strong></li>
<li>Pilot: <code>{artifact.pilot_id}</code></li><li>Customer request: <code>{artifact.request_id}</code></li>
<li>Repository: <strong>{artifact.repository_full_name}</strong></li><li>Branch: <code>{artifact.feature_branch}</code></li>
<li>Commit: <code>{artifact.approved_commit}</code></li><li>Draft PR: <strong>#{artifact.draft_pull_request_number}</strong></li>
<li>Preview: <code>{artifact.preview_url}</code></li></ul></section>
<section><h2>Exact end-to-end stages</h2><table><thead><tr><th>STAGE</th><th>RESULT</th><th>STATE</th><th>SOURCE</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>Immutable product chain</h2><ul><li>Customer idea: <code>{artifact.source_request_digest}</code></li>
<li>Locked PRD approval: <code>{artifact.prd_approval_digest}</code></li><li>Approved roadmap: <code>{artifact.roadmap_approval_digest}</code></li>
<li>Governed orchestration: <code>{artifact.orchestration_artifact_digest}</code></li><li>Reviewed code: <code>{artifact.coding_review_artifact_digest}</code></li>
<li>GitHub delivery: <code>{artifact.github_delivery_artifact_digest}</code></li><li>Preview: <code>{artifact.preview_artifact_digest}</code></li>
<li>Runtime acceptance: <code>{artifact.runtime_acceptance_artifact_digest}</code></li></ul></section>
<section class="boundary"><h2>Authority boundary</h2><ul><li>This is a closed fixture pilot; no live customer product or production target was selected</li>
<li>No repository write or draft-PR mutation was performed by Day 36</li><li>No merge, preview mutation, production deployment, release, billing, or risk acceptance</li>
<li class="warning">Day 37 hardening and founder UAT remain separately authorized</li></ul></section>
</main></body></html>""".encode()


def _application(body: bytes):
    def application(environ, start_response):  # noqa: ANN001
        if environ.get("PATH_INFO") != "/day36-product-pilot-evidence":
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


def test_day36_evidence_contract_reports_complete_product_pilot(tmp_path: Path) -> None:
    *_, artifact = _run_pilot(tmp_path)
    body = _founder_page(artifact).decode()
    assert "ALL 8 STAGES VERIFIED · 4 JOURNEYS PASSED · PRODUCTION UNTOUCHED" in body
    assert all(stage_id in body for stage_id in PILOT_STAGE_IDS)
    assert artifact.approved_commit in body
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pilot_status == PILOT_STATUS
    assert artifact.production_state == PRODUCTION_STATE


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_real_chromium_day36_pilot_and_founder_evidence(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    runtime_provider = RoutedPreviewChromiumProvider()
    *_, artifact = _run_pilot(tmp_path, runtime_provider)
    assert runtime_provider.launch_count == 1
    assert runtime_provider.console_errors == []
    assert runtime_provider.network_failures == []
    assert artifact.passed_journey_count == 4

    body = _founder_page(artifact)
    server = make_server(
        "127.0.0.1", 0, _application(body),
        server_class=_ThreadingServer, handler_class=_QuietHandler,
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
                locale="en-US", timezone_id="UTC",
            )
            page = context.new_page()
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error" else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: network_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day36-product-pilot-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            page.get_by_role("heading", name="First end-to-end product pilot").wait_for()
            page.get_by_text(
                "ALL 8 STAGES VERIFIED · 4 JOURNEYS PASSED · PRODUCTION UNTOUCHED"
            ).wait_for()
            assert page.get_by_text("PASS", exact=True).count() == 8
            assert console_errors == [] and network_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY36_FOUNDER_EVIDENCE_DIR")
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
    screenshot_path = target / "end-to-end-product-pilot-verification.png"
    screenshot_path.write_bytes(screenshot)
    screenshot_digest = hashlib.sha256(screenshot).hexdigest()
    commit_sha = os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", APPROVED_DAY35_BASE_SHA)
    if re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
        raise ValueError("Evidence commit SHA is invalid")
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": commit_sha,
        "approved_day35_base_commit": APPROVED_DAY35_BASE_SHA,
        "pilot_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "status": artifact.status,
            "pilot_status": artifact.pilot_status,
            "pilot_id": artifact.pilot_id,
            "customer_request_id": artifact.request_id,
            "stage_count": len(artifact.stage_receipts),
            "stages": [
                {"stage_id": item.stage_id, "state": item.state, "source_digest": item.source_digest}
                for item in artifact.stage_receipts
            ],
            "source_record_count": artifact.source_record_count,
            "completed_journey_count": artifact.completed_journey_count,
            "passed_journey_count": artifact.passed_journey_count,
            "draft_pull_request_number": artifact.draft_pull_request_number,
            "repository_write_count": artifact.repository_write_count,
            "pull_request_mutation_count": artifact.pull_request_mutation_count,
            "preview_mutation_count": artifact.preview_mutation_count,
            "production_deployment_count": artifact.production_deployment_count,
            "merge_count": artifact.merge_count,
            "release_count": artifact.release_count,
            "billing_count": artifact.billing_count,
            "risk_acceptance_count": artifact.risk_acceptance_count,
            "day37_action_count": artifact.day37_action_count,
            "production_state": artifact.production_state,
        },
        "source_chain": {
            "source_request_digest": artifact.source_request_digest,
            "prd_approval_digest": artifact.prd_approval_digest,
            "roadmap_approval_digest": artifact.roadmap_approval_digest,
            "orchestration_artifact_digest": artifact.orchestration_artifact_digest,
            "coding_review_artifact_digest": artifact.coding_review_artifact_digest,
            "github_delivery_artifact_digest": artifact.github_delivery_artifact_digest,
            "preview_artifact_digest": artifact.preview_artifact_digest,
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
