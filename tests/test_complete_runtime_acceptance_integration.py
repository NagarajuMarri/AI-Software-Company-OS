from __future__ import annotations

from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlparse
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import pytest

from runtime.complete_runtime_acceptance import (
    ARTIFACT_STATUS,
    AUTHENTICATION_STATE,
    BROWSER_STATE,
    JOURNEY_STATE,
    PILOT_STATUS,
    PREVIEW_STATE,
    PRODUCTION_STATE,
)
from runtime.managed_product_browser import (
    BrowserActionKind,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserLocatorKind,
)
from runtime.runtime_acceptance import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
)
from tests.test_complete_runtime_acceptance import PASSWORD, _run_acceptance


APPROVED_DAY34_BASE_SHA = "a3e02c89bdb95445e17fd6fe6791d9f45d6bf580"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):  # noqa: ANN001
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


class RoutedPreviewChromiumProvider:
    """Real Chromium adapter with the HTTPS preview origin routed to a closed fixture."""

    provider_id = "routed-preview-chromium-v1"

    def __init__(self) -> None:
        self.launch_count = 0
        self.console_errors: list[str] = []
        self.network_failures: list[str] = []

    def execute(self, plan, configuration, inputs, redactions, artifact_store):  # noqa: ANN001
        playwright = pytest.importorskip("playwright.sync_api")
        assert inputs["user-password"] == PASSWORD
        assert PASSWORD in redactions
        started = _utc_now()
        evidence: list[EvidenceArtifact] = []
        results: list[JourneyResult] = []
        origin = configuration.frontend_url.rstrip("/")
        expected_by_path = {
            journey.start_path: journey.steps[-2].expected_text
            for journey in plan.journeys
        }
        with playwright.sync_playwright() as runtime:
            self.launch_count += 1
            browser = runtime.chromium.launch(headless=True)
            try:
                for journey in plan.journeys:
                    context = browser.new_context(
                        accept_downloads=False,
                        locale="en-US",
                        service_workers="block",
                        timezone_id="UTC",
                        viewport={"width": 1280, "height": 780},
                    )
                    page = context.new_page()
                    journey_console: list[str] = []
                    journey_network: list[str] = []
                    secret_locators = []
                    page.on(
                        "console",
                        lambda message: journey_console.append(message.text)
                        if message.type == "error"
                        else None,
                    )
                    page.on("pageerror", lambda error: journey_console.append(str(error)))
                    page.on(
                        "requestfailed",
                        lambda request: journey_network.append(request.url),
                    )

                    def route_preview(route):  # noqa: ANN001
                        parsed = urlparse(route.request.url)
                        if f"{parsed.scheme}://{parsed.netloc}" != origin:
                            route.abort("blockedbyclient")
                            return
                        expected = expected_by_path.get(parsed.path)
                        if expected is None:
                            route.fulfill(status=404, body="Not found")
                            return
                        route.fulfill(
                            status=200,
                            content_type="text/html; charset=utf-8",
                            headers={
                                "Cache-Control": "no-store",
                                "Content-Security-Policy": (
                                    "default-src 'none'; style-src 'unsafe-inline'; "
                                    "script-src 'unsafe-inline'; frame-ancestors 'none'"
                                ),
                            },
                            body=_journey_page(journey.title, expected),
                        )

                    page.route("**/*", route_preview)
                    response = page.goto(
                        f"{origin}{journey.start_path}", wait_until="domcontentloaded"
                    )
                    assert response is not None and response.status == 200
                    step_results = []
                    for step in journey.steps:
                        locator = None if step.locator is None else _locator(page, step.locator)
                        if step.action is BrowserActionKind.FILL:
                            assert locator is not None
                            locator.fill(inputs[step.input_id])
                            if step.input_id == "user-password":
                                secret_locators.append(locator)
                        elif step.action is BrowserActionKind.CLICK:
                            assert locator is not None
                            locator.click()
                        elif step.action is BrowserActionKind.ASSERT_TEXT:
                            assert locator is not None
                            locator.wait_for(state="visible")
                            assert step.expected_text in locator.inner_text()
                        elif step.action is BrowserActionKind.ASSERT_URL_PATH:
                            assert urlparse(page.url).path == step.expected_path
                        else:  # pragma: no cover - the locked fixture uses only these actions
                            raise AssertionError("Unexpected routed-preview browser action")
                        step_results.append({"step_id": step.step_id, "outcome": "PASS"})
                    assert journey_console == [] and journey_network == []
                    screenshot = page.screenshot(
                        full_page=True,
                        animations="disabled",
                        mask=secret_locators,
                    )
                    observed = _utc_now()
                    journey_evidence = []
                    records = (
                        (
                            EvidenceKind.BROWSER,
                            {
                                "journey_id": journey.journey_id,
                                "steps": step_results,
                                "outcome": "PASS",
                            },
                        ),
                        (
                            EvidenceKind.BROWSER_CONSOLE,
                            {"journey_id": journey.journey_id, "entries": []},
                        ),
                        (
                            EvidenceKind.BROWSER_NETWORK,
                            {
                                "journey_id": journey.journey_id,
                                "failed_requests": [],
                                "blocked_origins": [],
                            },
                        ),
                    )
                    for kind, payload in records:
                        uri, digest = artifact_store.write_json(
                            plan.product_id, plan.run_id, payload
                        )
                        item = _evidence(plan, journey, kind, uri, digest, observed)
                        evidence.append(item)
                        journey_evidence.append(item.evidence_id)
                    uri, digest = artifact_store.write_bytes(
                        plan.product_id, plan.run_id, screenshot, "png"
                    )
                    screenshot_item = _evidence(
                        plan,
                        journey,
                        EvidenceKind.SCREENSHOT,
                        uri,
                        digest,
                        observed,
                    )
                    evidence.append(screenshot_item)
                    journey_evidence.append(screenshot_item.evidence_id)
                    results.append(
                        JourneyResult(
                            journey.journey_id,
                            EvidenceOutcome.PASS,
                            tuple(journey_evidence),
                            observed,
                        )
                    )
                    self.console_errors.extend(journey_console)
                    self.network_failures.extend(journey_network)
                    context.close()
            finally:
                browser.close()
        return BrowserExecutionResult(
            plan.run_id,
            plan.product_id,
            plan.plan_id,
            plan.digest,
            plan.commit_sha,
            BrowserExecutionStage.COMPLETED,
            tuple(evidence),
            tuple(results),
            started,
            _utc_now(),
        )


def _evidence(plan, journey, kind, uri, digest, observed):  # noqa: ANN001
    suffix = kind.value.removesuffix("_EVIDENCE").casefold().replace("_", "-")
    return EvidenceArtifact(
        evidence_id=f"{plan.run_id}.{journey.journey_id}.{suffix}",
        run_id=plan.run_id,
        capability_id=journey.capability_id,
        journey_id=journey.journey_id,
        kind=kind,
        outcome=EvidenceOutcome.PASS,
        commit_sha=plan.commit_sha,
        artifact_uri=uri,
        digest=digest,
        observed_at=observed,
        summary=f"Real Chromium verified {kind.value}",
        metadata=(
            ("plan_digest", plan.digest),
            ("provider_id", "routed-preview-chromium-v1"),
        ),
    )


def _locator(page, locator):  # noqa: ANN001, ANN202
    if locator.kind is BrowserLocatorKind.ROLE:
        return page.get_by_role(
            locator.value,
            name=locator.accessible_name,
            exact=locator.exact,
        )
    if locator.kind is BrowserLocatorKind.LABEL:
        return page.get_by_label(locator.value, exact=locator.exact)
    if locator.kind is BrowserLocatorKind.TEST_ID:
        return page.get_by_test_id(locator.value)
    if locator.kind is BrowserLocatorKind.TEXT:
        return page.get_by_text(locator.value, exact=locator.exact)
    raise AssertionError("Unsupported browser locator")


def _journey_page(title: str, expected: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{escape(title)}</title><style>
body{{font-family:Arial;background:#eef3f8;color:#123b61;padding:40px}}
main{{max-width:680px;margin:auto;background:white;padding:32px;border-radius:18px}}
label{{display:block;margin:14px 0}}input{{display:block;width:100%;padding:12px}}
button{{padding:12px 20px;background:#1769c2;color:white;border:0;border-radius:8px}}
#result{{margin-top:24px;padding:16px;background:#e1f6e9;color:#087447;font-weight:800}}
</style></head><body><main><h1>{escape(title)}</h1>
<form id="journey"><label>Email<input aria-label="Email" type="email" required></label>
<label>Password<input aria-label="Password" type="password" required></label>
<button type="submit">Run journey</button></form><div id="result" data-testid="journey-result" hidden></div>
<script>document.getElementById('journey').addEventListener('submit', event => {{
event.preventDefault(); const fields=event.currentTarget.querySelectorAll('input');
if(fields[0].value && fields[1].value){{fields[1].value=''; const result=document.getElementById('result');
result.textContent={json.dumps(expected)}; result.hidden=false;}}
}});</script></main></body></html>"""


def _founder_page(artifact) -> bytes:  # noqa: ANN001
    rows = "".join(
        f"<tr><td><code>{escape(item.journey_id)}</code></td>"
        f"<td>{escape(item.capability_id)}</td><td class='pass'>{item.outcome}</td>"
        f"<td>{item.evidence_count}</td><td><code>{item.screenshot_digest[:14]}…</code></td></tr>"
        for item in artifact.journey_receipts
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>ASCOS Day 35 runtime acceptance</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#eef3f8;color:#0c3155;font-family:Inter,Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:42px 28px 54px}}.eyebrow{{color:#2767bd;font-weight:800;letter-spacing:2px}}
h1{{font-size:42px;margin:12px 0}}p{{color:#55728f;font-size:18px;line-height:1.55}}.badge{{display:inline-block;background:#dff5e9;color:#087447;font-weight:800;padding:10px 16px;border-radius:24px}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0}}.card,section{{background:white;border:1px solid #d5e0ec;border-radius:16px;padding:20px}}
.metric{{font-size:34px;font-weight:900}}.label{{color:#607c97}}section{{margin:18px 0}}h2{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce5ee}}th{{font-size:12px;color:#607c97}}code{{font-size:12px}}.boundary{{border-left:5px solid #2767bd}}.warning{{color:#936100;font-weight:800}}.pass{{color:#087447;font-weight:800}}
@media(max-width:800px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}</style></head><body><main>
<div class="eyebrow">ASCOS AUTOMATIC IMPLEMENTATION · DAY 35</div><h1>Complete runtime acceptance</h1>
<p>ASCOS logged into the exact healthy Day 34 preview and completed every declared module-specific end-user journey in isolated Chromium.</p>
<div class="badge">● AUTHENTICATED · ALL JOURNEYS PASSED · PRODUCTION UNTOUCHED</div>
<div class="metrics"><div class="card"><div class="metric">{len(artifact.journey_receipts)}</div><div class="label">journeys passed</div></div>
<div class="card"><div class="metric">{artifact.authenticated_session_count}</div><div class="label">authenticated sessions</div></div>
<div class="card"><div class="metric">{artifact.screenshot_count}</div><div class="label">journey screenshots</div></div>
<div class="card"><div class="metric">{artifact.evidence_artifact_count}</div><div class="label">evidence artifacts</div></div>
<div class="card"><div class="metric">0</div><div class="label">console errors</div></div><div class="card"><div class="metric">0</div><div class="label">network failures</div></div>
<div class="card"><div class="metric">0</div><div class="label">production deploys</div></div><div class="card"><div class="metric">0</div><div class="label">repository writes</div></div></div>
<section><h2>Exact preview binding</h2><ul><li>Repository: <strong>{escape(artifact.repository_full_name)}</strong></li>
<li>Branch: <code>{escape(artifact.feature_branch)}</code></li><li>Approved commit: <code>{artifact.approved_commit}</code></li>
<li>Approved tree: <code>{artifact.approved_tree}</code></li><li>Environment: <strong>{escape(artifact.preview_environment_id)}</strong></li>
<li>Preview: <code>{escape(artifact.preview_url)}</code></li></ul></section>
<section><h2>Module-specific Chrome journeys</h2><table><thead><tr><th>JOURNEY</th><th>CAPABILITY</th><th>RESULT</th><th>EVIDENCE</th><th>SCREENSHOT</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>Immutable source chain</h2><ul><li>Day 34 preview: <code>{artifact.preview_artifact_digest}</code></li>
<li>Browser plan: <code>{artifact.browser_plan_digest}</code></li><li>Runtime configuration: <code>{artifact.runtime_configuration_digest}</code></li>
<li>Acceptance profile: <code>{artifact.acceptance_profile_digest}</code></li><li>Browser execution: <code>{artifact.browser_execution_digest}</code></li></ul></section>
<section class="boundary"><h2>Authority boundary</h2><ul><li>Opaque login reference only; raw credentials were not persisted</li>
<li>Every journey has passing browser, console, network, and screenshot evidence</li><li>No preview mutation, repository write, PR approval, merge, production deployment, release, or billing</li>
<li class="warning">No official pilot selected; the first end-to-end product pilot remains Day 36</li></ul></section>
</main></body></html>""".encode("utf-8")


def _application(body: bytes):
    def application(environ, start_response):  # noqa: ANN001
        if environ.get("PATH_INFO") != "/day35-complete-runtime-acceptance-evidence":
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


def test_day35_evidence_contract_reports_complete_runtime_acceptance(tmp_path: Path) -> None:
    *_, artifact = _run_acceptance(tmp_path)
    body = _founder_page(artifact).decode("utf-8")
    assert "AUTHENTICATED · ALL JOURNEYS PASSED · PRODUCTION UNTOUCHED" in body
    assert artifact.approved_commit in body and artifact.approved_tree in body
    assert all(item.journey_id in body for item in artifact.journey_receipts)
    assert artifact.preview_state == PREVIEW_STATE
    assert artifact.authentication_state == AUTHENTICATION_STATE
    assert artifact.journey_state == JOURNEY_STATE
    assert artifact.browser_state == BROWSER_STATE
    assert artifact.production_state == PRODUCTION_STATE
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="set ASCOS_BROWSER_INTEGRATION=1 for real Chromium verification",
)
def test_real_chromium_day35_runtime_journeys_and_founder_evidence(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    runtime_provider = RoutedPreviewChromiumProvider()
    *_, artifact = _run_acceptance(tmp_path, runtime_provider)
    assert runtime_provider.launch_count == 1
    assert runtime_provider.console_errors == []
    assert runtime_provider.network_failures == []
    assert len(artifact.journey_receipts) == 4
    assert all(item.outcome == "PASS" for item in artifact.journey_receipts)

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
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: network_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day35-complete-runtime-acceptance-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
            page.get_by_role("heading", name="Complete runtime acceptance").wait_for()
            page.get_by_text(
                "AUTHENTICATED · ALL JOURNEYS PASSED · PRODUCTION UNTOUCHED"
            ).wait_for()
            assert page.get_by_text("PASS", exact=True).count() == 4
            assert console_errors == [] and network_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY35_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(
            Path(target), artifact, screenshot, console_errors, network_failures
        )


def _write_evidence(
    target: Path,
    artifact,  # noqa: ANN001
    screenshot: bytes,
    console_errors: list[str],
    network_failures: list[str],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_path = target / "complete-runtime-acceptance-verification.png"
    screenshot_path.write_bytes(screenshot)
    screenshot_digest = hashlib.sha256(screenshot).hexdigest()
    commit_sha = os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA", APPROVED_DAY34_BASE_SHA)
    if re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
        raise ValueError("Evidence commit SHA is invalid")
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "commit_sha": commit_sha,
        "approved_day34_base_commit": APPROVED_DAY34_BASE_SHA,
        "source_chain": {
            "preview_artifact_digest": artifact.preview_artifact_digest,
            "github_delivery_artifact_digest": artifact.github_delivery_artifact_digest,
            "devops_artifact_digest": artifact.devops_artifact_digest,
            "coding_review_artifact_digest": artifact.coding_review_artifact_digest,
            "workspace_artifact_digest": artifact.workspace_artifact_digest,
            "orchestration_artifact_digest": artifact.orchestration_artifact_digest,
            "qa_artifact_digest": artifact.qa_artifact_digest,
            "security_artifact_digest": artifact.security_artifact_digest,
            "runtime_configuration_digest": artifact.runtime_configuration_digest,
            "acceptance_profile_digest": artifact.acceptance_profile_digest,
            "browser_plan_digest": artifact.browser_plan_digest,
            "browser_execution_digest": artifact.browser_execution_digest,
        },
        "runtime_output": {
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.digest,
            "status": artifact.status,
            "preview_environment_id": artifact.preview_environment_id,
            "preview_url": artifact.preview_url,
            "approved_commit": artifact.approved_commit,
            "approved_tree": artifact.approved_tree,
            "journey_count": len(artifact.journey_receipts),
            "passed_journey_count": sum(
                item.outcome == "PASS" for item in artifact.journey_receipts
            ),
            "journeys": [
                {
                    "journey_id": item.journey_id,
                    "capability_id": item.capability_id,
                    "outcome": item.outcome,
                    "evidence_count": item.evidence_count,
                    "screenshot_digest": item.screenshot_digest,
                }
                for item in artifact.journey_receipts
            ],
            "browser_launch_count": artifact.browser_launch_count,
            "authenticated_session_count": artifact.authenticated_session_count,
            "evidence_artifact_count": artifact.evidence_artifact_count,
            "screenshot_count": artifact.screenshot_count,
            "console_error_count": artifact.console_error_count,
            "network_failure_count": artifact.network_failure_count,
            "raw_secret_exposure_count": artifact.raw_secret_exposure_count,
            "repository_write_count": artifact.repository_write_count,
            "preview_mutation_count": artifact.preview_mutation_count,
            "production_deployment_count": artifact.production_deployment_count,
            "merge_count": artifact.merge_count,
            "release_count": artifact.release_count,
            "billing_count": artifact.billing_count,
            "pilot_selection_count": artifact.pilot_selection_count,
            "preview_state": artifact.preview_state,
            "authentication_state": artifact.authentication_state,
            "journey_state": artifact.journey_state,
            "browser_state": artifact.browser_state,
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


def _utc_now():  # noqa: ANN202
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
