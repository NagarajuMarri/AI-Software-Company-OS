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

from runtime.agents import AgentRole
from runtime.workforce_architecture import ADR_STATUS, ARTIFACT_STATUS, PILOT_STATUS
from tests.test_workforce_architecture import _run_architect


APPROVED_DAY23_HEAD = "e10a2bfbff972997c5fffce8d7b95828f0c574a3"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _items(values: tuple[str, ...]) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in values)


def _report(product_manager, architect):
    technologies = "".join(
        f"<tr><td>{escape(item.area)}</td><td>{escape(item.technology)}</td>"
        f"<td><span class='proposed'>{escape(item.status)}</span></td></tr>"
        for item in architect.technology_recommendations
    )
    components = "".join(
        f"<article><h3>{escape(item.name)}</h3><p>{escape(item.responsibility)}</p>"
        f"<small>{escape(item.data_responsibility)}</small></article>"
        for item in architect.components
    )
    decisions = "".join(
        f"<article><div class='row'><h3>{escape(item.title)}</h3>"
        f"<span class='proposed'>{escape(item.status)}</span></div>"
        f"<p>{escape(item.decision)}</p><small>Human approval required</small></article>"
        for item in architect.adr_drafts
    )
    risks = "".join(
        f"<tr><td>{escape(item.title)}</td><td>{escape(item.severity.value)}</td>"
        f"<td>{escape(item.likelihood.value)}</td><td>{escape(item.mitigation)}</td></tr>"
        for item in architect.technical_risks
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 24 Software Architect verification</title>
<style>
:root{{--ink:#11243e;--muted:#61728b;--line:#d5dfeb;--navy:#173a70;--blue:#386bc8;
--green:#167659;--amber:#9a6415;--wash:#f1f5fa}}*{{box-sizing:border-box}}
body{{margin:0;background:var(--wash);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:52px 30px 70px}}.eyebrow{{color:var(--blue);font-weight:850;
letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:48px;line-height:1.05;margin:12px 0}}
.lead{{font-size:20px;color:var(--muted);max-width:920px;line-height:1.5}}.status{{display:inline-flex;
margin:10px 0 28px;background:#e3f6ef;color:var(--green);font-weight:850;border-radius:999px;padding:10px 16px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}section{{background:#fff;border:1px solid var(--line);
border-radius:18px;padding:24px}}.wide{{grid-column:1/-1}}h2{{margin:0 0 14px;font-size:24px}}
h3{{font-size:17px;margin:0 0 8px}}p{{line-height:1.55}}small{{color:var(--muted);line-height:1.4}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}article{{padding:16px;border:1px solid var(--line);
border-radius:13px;background:#f9fbfd}}.row{{display:flex;align-items:start;justify-content:space-between;gap:12px}}
.proposed{{display:inline-flex;background:#fff2d8;color:var(--amber);font-size:12px;font-weight:850;
padding:5px 8px;border-radius:999px}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;
vertical-align:top;padding:12px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-size:12px;
text-transform:uppercase;letter-spacing:.06em}}ul{{padding-left:20px;line-height:1.7}}dl{{display:grid;
grid-template-columns:220px 1fr;gap:11px;margin:0}}dt{{color:var(--muted)}}dd{{margin:0;font-weight:650;
overflow-wrap:anywhere}}code{{font-size:12px}}.boundary{{border-left:5px solid var(--navy)}}
@media(max-width:820px){{.grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}.cards{{grid-template-columns:1fr}}
h1{{font-size:38px}}dl{{grid-template-columns:1fr}}table{{font-size:13px}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS operational workforce · Day 24</div>
<h1>Software Architect proposal verification</h1>
<p class="lead">The exact persisted Product Manager plan produced a draft architecture, proposed technology choices, proposed ADRs, and identified technical risks through one governed Digital Twin.</p>
<div class="status">● DRAFT COMPLETE · HUMAN REVIEW PENDING</div>
<div class="grid">
<section><h2>Architecture boundary</h2><p>{escape(architect.summary)}</p><p>{escape(architect.domain_boundary)}</p>
<h3>Principles</h3><ul>{_items(architect.principles)}</ul></section>
<section><h2>Data, security, and quality</h2><h3>Data lifecycle</h3><ul>{_items(architect.data_lifecycle)}</ul>
<h3>Security controls</h3><ul>{_items(architect.security_controls)}</ul>
<h3>Quality strategy</h3><ul>{_items(architect.quality_strategy)}</ul></section>
<section class="wide"><h2>Proposed components</h2><div class="cards">{components}</div></section>
<section class="wide"><h2>Technology recommendations</h2><table><thead><tr><th>Area</th><th>Recommendation</th><th>Status</th></tr></thead><tbody>{technologies}</tbody></table></section>
<section class="wide"><h2>Proposed architecture decisions</h2><div class="cards">{decisions}</div></section>
<section class="wide"><h2>Technical risks</h2><table><thead><tr><th>Risk</th><th>Severity</th><th>Likelihood</th><th>Mitigation</th></tr></thead><tbody>{risks}</tbody></table></section>
<section class="wide"><h2>Exact Product Manager → Architect handoff</h2><dl>
<dt>Product Manager artifact</dt><dd><code>{escape(product_manager.digest)}</code></dd>
<dt>Architect source binding</dt><dd><code>{escape(architect.product_manager_artifact_digest)}</code></dd>
<dt>Architect role</dt><dd>SOFTWARE_ARCHITECT</dd>
<dt>Architect artifact</dt><dd><code>{escape(architect.digest)}</code></dd>
<dt>Execution receipt</dt><dd><code>{escape(architect.receipt_digest)}</code></dd>
<dt>Artifact status</dt><dd>{escape(architect.status)}</dd></dl></section>
<section class="wide boundary"><h2>Authority boundary</h2><ul>
<li>Technology recommendations and ADRs are PROPOSED; architecture approval remains human-only</li>
<li>Zero tools and no repository, command, network, coding, engineering-task, approval, merge, deployment, release, billing, or budget authority</li>
<li>No Day 25 engineering-agent implementation behavior</li>
<li>No official pilot product selected</li></ul></section>
</div></main></body></html>""".encode("utf-8")

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day24-architecture-evidence":
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


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_chromium_inspects_software_architect_proposal(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    _, provider, intake, product_manager, _, authority, architect = _run_architect(
        tmp_path
    )
    assert architect.business_role is AgentRole.SOFTWARE_ARCHITECT
    assert architect.product_manager_artifact_digest == product_manager.digest
    assert architect.status == ARTIFACT_STATUS
    assert architect.pilot_status == PILOT_STATUS
    assert all(item.status == ADR_STATUS for item in architect.adr_drafts)
    assert provider.execution_count == 1
    assert authority.allowed_tool_ids == () and authority.max_tool_calls == 0

    server = make_server(
        "127.0.0.1",
        0,
        _report(product_manager, architect),
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    console_errors: list[str] = []
    request_failures: list[str] = []
    screenshot: bytes
    try:
        with playwright.sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1900},
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
                f"http://127.0.0.1:{server.server_port}/day24-architecture-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            page.get_by_role(
                "heading", name="Software Architect proposal verification"
            ).wait_for()
            assert page.get_by_text(
                "● DRAFT COMPLETE · HUMAN REVIEW PENDING", exact=True
            ).is_visible()
            assert page.get_by_text("SOFTWARE_ARCHITECT", exact=True).is_visible()
            assert page.get_by_text(product_manager.digest, exact=True).count() == 2
            assert page.get_by_text(architect.digest, exact=True).is_visible()
            assert page.get_by_text("PROPOSED", exact=True).count() == 6
            assert page.get_by_text(
                "No Day 25 engineering-agent implementation behavior", exact=True
            ).is_visible()
            assert page.get_by_text(
                "No official pilot product selected", exact=True
            ).is_visible()
            assert console_errors == []
            assert request_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY24_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(
            Path(target), intake, product_manager, architect, authority, screenshot
        )


def _write_evidence(
    target: Path,
    intake,
    product_manager,
    architect,
    authority,
    screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "software-architect-verification.png"
    (target / screenshot_name).write_bytes(screenshot)
    commit_sha = (
        os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or "d" * 40
    ).lower()
    assert re.fullmatch(r"[0-9a-f]{40}", commit_sha)
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "workforce_architecture.product_manager_to_software_architect.inspect_proposal",
        "claims": [
            "EXACT_PERSISTED_PRODUCT_MANAGER_PLAN_CONSUMED",
            "SOFTWARE_ARCHITECT_ROLE_EXECUTED_THROUGH_DIGITAL_TWIN_RUNTIME",
            "DRAFT_ARCHITECTURE_PROPOSAL_PRODUCED",
            "TECHNOLOGY_RECOMMENDATIONS_REMAIN_PROPOSED",
            "ARCHITECTURE_DECISIONS_REMAIN_PROPOSED_FOR_HUMAN_REVIEW",
            "TECHNICAL_RISKS_AND_MITIGATIONS_IDENTIFIED",
            "EXACT_RETRY_AND_RESTART_ARE_SIDE_EFFECT_FREE",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_ARCHITECTURE_EVIDENCE",
            "NO_TOOLS_REPOSITORY_COMMAND_NETWORK_CODING_TASK_CREATION_ARCHITECTURE_APPROVAL_MERGE_DEPLOYMENT_RELEASE_BILLING_OR_BUDGET_AUTHORITY",
            "NO_DAY25_ENGINEERING_IMPLEMENTATION_BEHAVIOR",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day23_base_commit": APPROVED_DAY23_HEAD,
        "opportunity_digest": intake.digest,
        "fixture_contract": (
            "Generic workforce verification data only; no official pilot product was selected"
        ),
        "source_product_manager": {
            "artifact_id": product_manager.artifact_id,
            "artifact_digest": product_manager.digest,
            "business_role": product_manager.business_role.value,
            "status": product_manager.status,
        },
        "software_architect": {
            "artifact_id": architect.artifact_id,
            "artifact_digest": architect.digest,
            "business_role": architect.business_role.value,
            "provider_id": architect.provider_id,
            "status": architect.status,
            "pilot_status": architect.pilot_status,
            "product_manager_artifact_digest": architect.product_manager_artifact_digest,
            "component_count": len(architect.components),
            "technology_recommendation_count": len(architect.technology_recommendations),
            "proposed_adr_count": len(architect.adr_drafts),
            "technical_risk_count": len(architect.technical_risks),
            "authority_digest": architect.authority_digest,
            "assignment_digest": architect.assignment_digest,
            "provider_request_digest": architect.request_digest,
            "provider_output_digest": architect.output_digest,
            "execution_receipt_digest": architect.receipt_digest,
            "allowed_action_ids": list(authority.allowed_action_ids),
            "tool_call_count": 0,
        },
        "screenshots": {screenshot_name: hashlib.sha256(screenshot).hexdigest()},
        "redaction_contract": (
            "No credentials, cookies, customer secrets, raw provider exceptions, or local paths"
        ),
    }
    content = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (target / "manifest.json").write_bytes(content)
