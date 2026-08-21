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

from runtime.workforce_documentation import (
    ARTIFACT_STATUS,
    DOCUMENT_STATUS,
    PILOT_STATUS,
    PUBLICATION_STATE,
    VALIDATION_STATE,
)
from tests.test_workforce_documentation import _run_documentation


APPROVED_DAY28_HEAD = "22ed62b807c79264d3829326e6710dfaf1c9699f"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *_args):
        return


class _ThreadingServer(WSGIServer):
    daemon_threads = True


def _list(items) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def _document_card(document) -> str:
    sections = "".join(
        f"<li><strong>{escape(item.heading)}</strong><br>{escape(item.content)}</li>"
        for item in document.sections
    )
    return (
        f"<article><div class='row'><h2>{escape(document.kind.value.title())}</h2>"
        f"<span>{escape(document.publication_state)}</span></div>"
        f"<h3>{escape(document.title)}</h3><p>{escape(document.purpose)}</p>"
        f"<p class='audience'>Audience · {escape(', '.join(document.audience))}</p>"
        f"<ul>{sections}</ul><div class='validated'>{escape(document.validation_state)}</div></article>"
    )


def _report(authority, artifact):
    cards = "".join(_document_card(item) for item in artifact.documents)
    engineering = "".join(
        f"<tr><td>{escape(source.business_role.value)}</td>"
        f"<td><code>{escape(source.artifact_digest)}</code></td></tr>"
        for source in artifact.sources
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ASCOS Day 29 Documentation Engineer verification</title>
<style>
:root{{--ink:#102a43;--muted:#627d98;--line:#d9e2ec;--blue:#275dad;--green:#087f5b;
--amber:#9c6506;--wash:#edf2f7}}*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);
color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}main{{max-width:1280px;
margin:0 auto;padding:48px 28px 72px}}.eyebrow{{color:var(--blue);font-weight:850;letter-spacing:.12em;
text-transform:uppercase}}h1{{font-size:48px;line-height:1.06;margin:12px 0}}.lead{{font-size:20px;
line-height:1.5;color:var(--muted);max-width:1040px}}.status{{display:inline-flex;margin:10px 0 28px;
background:#dff7ee;color:var(--green);font-weight:850;border-radius:999px;padding:10px 16px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}}article,section{{background:#fff;
border:1px solid var(--line);border-radius:18px;padding:23px}}article{{min-height:390px}}.row{{display:flex;
justify-content:space-between;gap:12px;align-items:start}}h2{{font-size:24px;margin:0}}h3{{font-size:17px;
margin:12px 0}}p,li{{line-height:1.5}}article span{{background:#fff3d6;color:var(--amber);font-size:11px;
font-weight:850;padding:6px 9px;border-radius:999px}}.audience{{color:var(--muted)}}.validated{{color:var(--green);
font-size:11px;font-weight:850;margin-top:16px}}section{{margin-top:18px}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:12px;text-align:left;border-bottom:1px solid var(--line)}}th{{font-size:11px;color:var(--muted);
text-transform:uppercase}}code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;
overflow-wrap:anywhere}}.boundary{{border-left:5px solid var(--blue)}}
@media(max-width:840px){{.grid{{grid-template-columns:1fr}}h1{{font-size:38px}}article{{min-height:auto}}}}
</style></head><body><main>
<div class="eyebrow">ASCOS workforce · Day 29</div>
<h1>Governed Documentation Engineer agent</h1>
<p class="lead">Five exact-source-bound documentation drafts and one customer handoff are ready for human review. Nothing is published.</p>
<div class="status">● DOCUMENTATION VALIDATED · 0 DOCUMENTS PUBLISHED</div>
<div class="grid">{cards}</div>
<section><h2>Customer handoff</h2><p>{escape(artifact.customer_handoff.readiness_summary)}</p>
<h3>Human review checklist</h3><ul>{_list(artifact.customer_handoff.review_checklist)}</ul></section>
<section><h2>Exact upstream bindings</h2>
<p>Architecture: <code>{escape(artifact.architecture_artifact_digest)}</code></p>
<p>QA: <code>{escape(artifact.qa_artifact_digest)}</code></p>
<p>Security: <code>{escape(artifact.security_artifact_digest)}</code></p>
<p>DevOps: <code>{escape(artifact.devops_artifact_digest)}</code></p>
<table><thead><tr><th>Engineering role</th><th>Artifact digest</th></tr></thead>
<tbody>{engineering}</tbody></table></section>
<section class="boundary"><h2>Authority boundary</h2><ul>
<li>0 tools · {authority.max_tool_calls} tool calls · no live provider</li>
<li>No filesystem, workspace, repository, command, network, credentials, customer channel, or publication target</li>
<li>All five records remain {escape(DOCUMENT_STATUS)} and {escape(PUBLICATION_STATE)}</li>
<li>No product execution, commit, merge, deployment, release, billing, budget, approval, or orchestration authority</li>
<li>No official pilot product selected</li></ul></section>
</main></body></html>""".encode()

    def application(environ, start_response):
        if environ.get("PATH_INFO") != "/day29-documentation-evidence":
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


def test_documentation_report_has_restrictive_headers_and_exact_bindings(tmp_path: Path) -> None:
    *_, authority, artifact = _run_documentation(tmp_path)
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        _report(authority, artifact)({"PATH_INFO": "/day29-documentation-evidence"}, start_response)
    )
    headers = captured["headers"]
    assert captured["status"] == "200 OK"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    for digest in (
        artifact.architecture_artifact_digest, artifact.qa_artifact_digest,
        artifact.security_artifact_digest, artifact.devops_artifact_digest,
    ):
        assert digest.encode() in body
    assert b"0 DOCUMENTS PUBLISHED" in body
    assert b"No official pilot product selected" in body


def test_documentation_manifest_binds_all_sources_and_five_drafts(
    tmp_path: Path, monkeypatch,
) -> None:
    _, _, _, architecture, sources, qa, security, devops, _, _, authority, artifact = _run_documentation(tmp_path)
    monkeypatch.setenv("ASCOS_EVIDENCE_COMMIT_SHA", "d" * 40)
    target = tmp_path / "founder-evidence"
    screenshot = b"generic-documentation-screenshot"
    _write_evidence(
        target, architecture, sources, qa, security, devops, authority, artifact, screenshot
    )
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["result"] == "PASS"
    assert manifest["commit_sha"] == "d" * 40
    assert manifest["approved_day28_base_commit"] == APPROVED_DAY28_HEAD
    assert manifest["devops_source"]["artifact_digest"] == devops.digest
    assert [item["artifact_digest"] for item in manifest["engineering_sources"]] == [item.digest for item in sources]
    output = manifest["documentation_output"]
    assert output["artifact_digest"] == artifact.digest
    assert output["document_count"] == 5
    assert set(output["document_kinds"]) == {item.value for item in artifact.documents[0].kind.__class__}
    assert set(output["publication_states"].values()) == {PUBLICATION_STATE}
    assert output["tool_call_count"] == 0
    assert manifest["screenshots"]["documentation-engineer-verification.png"] == hashlib.sha256(screenshot).hexdigest()


@pytest.mark.skipif(
    os.environ.get("ASCOS_BROWSER_INTEGRATION") != "1",
    reason="requires installed Playwright Chromium",
)
def test_real_chromium_inspects_documentation_engineer_output(tmp_path: Path) -> None:
    _, provider, _, architecture, sources, qa, security, devops, _, _, authority, artifact = _run_documentation(tmp_path)
    assert provider.execution_count == 1
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(item.digest for item in sources)
    assert (artifact.qa_artifact_digest, artifact.security_artifact_digest, artifact.devops_artifact_digest) == (qa.digest, security.digest, devops.digest)
    assert len(artifact.documents) == 5
    assert all(item.validation_state == VALIDATION_STATE for item in artifact.documents)
    assert all(item.publication_state == PUBLICATION_STATE for item in artifact.documents)
    assert authority.allowed_tool_ids == () and authority.max_tool_calls == 0

    server = make_server(
        "127.0.0.1", 0, _report(authority, artifact),
        server_class=_ThreadingServer, handler_class=_QuietHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    console_errors: list[str] = []
    request_failures: list[str] = []
    try:
        with pytest.importorskip("playwright.sync_api").sync_playwright() as browser_runtime:
            browser = browser_runtime.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000}, locale="en-US", timezone_id="UTC"
            )
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.on("requestfailed", lambda request: request_failures.append(request.url))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/day29-documentation-evidence",
                wait_until="networkidle",
            )
            assert response is not None and response.status == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            page.get_by_role("heading", name="Governed Documentation Engineer agent").wait_for()
            assert page.get_by_text("● DOCUMENTATION VALIDATED · 0 DOCUMENTS PUBLISHED", exact=True).is_visible()
            for heading in ("Technical", "User", "Api", "Operations", "Release"):
                assert page.get_by_role("heading", name=heading, exact=True).is_visible()
            assert page.get_by_text(VALIDATION_STATE, exact=True).count() == 5
            assert page.get_by_text(PUBLICATION_STATE, exact=True).count() >= 5
            assert page.get_by_text(artifact.devops_artifact_digest, exact=True).is_visible()
            assert page.get_by_text("No official pilot product selected", exact=True).is_visible()
            assert console_errors == [] and request_failures == []
            screenshot = page.screenshot(full_page=True)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    target = os.environ.get("ASCOS_DAY29_FOUNDER_EVIDENCE_DIR")
    if target:
        _write_evidence(
            Path(target), architecture, sources, qa, security, devops,
            authority, artifact, screenshot,
        )


def _write_evidence(
    target: Path, architecture, sources, qa, security, devops,
    authority, artifact, screenshot: bytes,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    screenshot_name = "documentation-engineer-verification.png"
    (target / screenshot_name).write_bytes(screenshot)
    commit_sha = (
        os.environ.get("ASCOS_EVIDENCE_COMMIT_SHA")
        or os.environ.get("GITHUB_SHA") or "e" * 40
    ).lower()
    assert re.fullmatch(r"[0-9a-f]{40}", commit_sha)
    documents = {item.kind.value: item.publication_state for item in artifact.documents}
    manifest = {
        "schema_version": 1,
        "result": "PASS",
        "journey": "workforce_documentation.exact_sources_to_five_drafts.inspect_output",
        "claims": [
            "EXACT_PERSISTED_ARCHITECTURE_ENGINEERING_QA_SECURITY_AND_DEVOPS_SOURCES_CONSUMED",
            "ONE_DOCUMENTATION_ENGINEER_PROFILE_EXECUTED_ON_PROVIDER_NEUTRAL_RUNTIME",
            "TECHNICAL_USER_API_OPERATIONS_RELEASE_AND_CUSTOMER_HANDOFF_DRAFTS_TYPED",
            "ALL_DOCUMENTS_EXACT_SOURCE_VALIDATED_AND_TRUTHFULLY_NOT_PUBLISHED",
            "EXACT_RETRY_AND_RESTART_ARE_SIDE_EFFECT_FREE",
            "CHROMIUM_INSPECTED_FOUNDER_SAFE_DOCUMENTATION_EVIDENCE",
            "CONSOLE_AND_NETWORK_FAILURE_COLLECTIONS_EMPTY",
            "NO_TOOLS_LIVE_PROVIDER_FILESYSTEM_REPOSITORY_COMMAND_NETWORK_CREDENTIAL_CUSTOMER_CHANNEL_WORKSPACE_COMMIT_MERGE_DEPLOYMENT_RELEASE_BILLING_OR_BUDGET_AUTHORITY",
            "NO_PRODUCT_EXECUTION_PUBLICATION_APPROVAL_PILOT_SELECTION_OR_MULTI_AGENT_ORCHESTRATION_BEHAVIOR",
            "NO_OFFICIAL_PILOT_PRODUCT_SELECTED",
        ],
        "commit_sha": commit_sha,
        "approved_day28_base_commit": APPROVED_DAY28_HEAD,
        "fixture_contract": "Generic Documentation workforce verification data only; no official pilot was selected",
        "architecture_source": {
            "artifact_id": architecture.artifact_id, "artifact_digest": architecture.digest,
            "status": architecture.status, "pilot_status": architecture.pilot_status,
        },
        "engineering_sources": [
            {
                "artifact_id": item.artifact_id, "artifact_digest": item.digest,
                "business_role": item.business_role.value, "status": item.status,
                "pilot_status": item.pilot_status,
            }
            for item in sources
        ],
        "qa_source": {"artifact_id": qa.artifact_id, "artifact_digest": qa.digest, "status": qa.status},
        "security_source": {"artifact_id": security.artifact_id, "artifact_digest": security.digest, "status": security.status},
        "devops_source": {"artifact_id": devops.artifact_id, "artifact_digest": devops.digest, "status": devops.status},
        "documentation_output": {
            "artifact_id": artifact.artifact_id, "artifact_digest": artifact.digest,
            "work_order_digest": artifact.work_order_digest,
            "business_role": artifact.business_role.value, "provider_id": artifact.provider_id,
            "status": artifact.status, "pilot_status": artifact.pilot_status,
            "document_count": len(artifact.documents),
            "document_kinds": list(documents), "publication_states": documents,
            "validation_state": VALIDATION_STATE,
            "customer_handoff_state": artifact.customer_handoff.publication_state,
            "capability_ids": list(artifact.capability_ids),
            "allowed_action_ids": list(artifact.action_ids),
            "authority_digest": artifact.authority_digest,
            "assignment_digest": artifact.assignment_digest,
            "provider_request_digest": artifact.request_digest,
            "provider_output_digest": artifact.output_digest,
            "execution_receipt_digest": artifact.receipt_digest,
            "tool_call_count": authority.max_tool_calls,
        },
        "console_errors": [], "network_failures": [],
        "screenshots": {screenshot_name: hashlib.sha256(screenshot).hexdigest()},
        "redaction_contract": "No credentials, cookies, customer secrets, raw provider payloads, exceptions, or local paths",
    }
    (target / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    )
