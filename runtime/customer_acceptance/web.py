"""Authenticated dashboard for isolated preview and end-user browser acceptance."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.customer_acceptance.errors import (
    CustomerAcceptanceConflict,
    CustomerAcceptanceCorrupt,
    CustomerAcceptanceNotConfigured,
    CustomerAcceptanceNotFound,
    CustomerAcceptancePolicyError,
    CustomerAcceptanceReconciliationRequired,
)
from runtime.customer_acceptance.models import (
    CustomerAcceptanceRecord,
    CustomerAcceptanceStatus,
)
from runtime.customer_acceptance.service import CustomerAcceptanceService
from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_delivery import CustomerDeliveryConflict, CustomerDeliveryCorrupt
from runtime.customer_evidence import CustomerEvidenceConflict, CustomerEvidenceCorrupt
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond
from runtime.managed_product_browser import BrowserArtifactError, BrowserPlanError


_ID = r"([A-Za-z0-9][A-Za-z0-9_.-]{0,127})"
_BASE = re.compile(rf"^/customer/requests/{_ID}/acceptance$")
_ACTION = re.compile(rf"^/customer/requests/{_ID}/acceptance/(prepare|approve|execute)$")
_MAX_BODY = 4_096


class CustomerAcceptanceApplication:
    """Expose only customer-scoped, CSRF-protected Module 5 transitions."""

    def __init__(self, service: CustomerAcceptanceService) -> None:
        self._service = service

    @staticmethod
    def handles(path: str) -> bool:
        return _BASE.fullmatch(path) is not None or _ACTION.fullmatch(path) is not None

    def __call__(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
    ) -> Iterable[bytes]:
        customer_id = environ.get("REMOTE_USER")
        csrf = _csrf(environ)
        if not isinstance(customer_id, str) or not customer_id or csrf is None:
            return _respond(
                start_response,
                "401 Unauthorized",
                _message("Sign in required", "A verified customer session is required."),
            )
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        base = _BASE.fullmatch(path)
        action = _ACTION.fullmatch(path)
        request_id = base.group(1) if base is not None else action.group(1) if action else ""
        try:
            if base is not None and method == "GET":
                record = self._service.find(customer_id, request_id)
                return _respond(
                    start_response,
                    "200 OK",
                    _dashboard(
                        request_id,
                        record,
                        csrf,
                        configured=self._service.configured,
                        live_enabled=self._service.live_enabled,
                    ),
                )
            if action is not None and method == "POST":
                name = action.group(2)
                fields = _fields(environ, name)
                if not hmac.compare_digest(fields["csrf_token"][0], csrf):
                    raise ValueError("CSRF mismatch")
                if name == "prepare":
                    self._service.prepare(customer_id, request_id)
                elif name == "approve":
                    self._service.approve(
                        customer_id,
                        request_id,
                        expected_approval_digest=fields["approval_digest"][0],
                        confirm_preview_scope=fields["confirm_scope"] == ["yes"],
                    )
                else:
                    self._service.execute(
                        customer_id,
                        request_id,
                        expected_approval_digest=fields["approval_digest"][0],
                        confirm_preview_deployment=fields["confirm_preview"] == ["yes"],
                        confirm_browser_execution=fields["confirm_browser"] == ["yes"],
                    )
                return _redirect(start_response, f"/customer/requests/{request_id}/acceptance")
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message("Acceptance request rejected", "Reload the exact plan and try again."),
            )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except CustomerAcceptanceNotConfigured:
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Preview acceptance is not enabled",
                    "An operator must bind the preview workflow, URL, and browser plan, then separately confirm both effects.",
                ),
            )
        except (
            CustomerAcceptanceConflict,
            CustomerAcceptanceNotFound,
            CustomerAcceptancePolicyError,
            CustomerDeliveryConflict,
            CustomerEvidenceConflict,
            BrowserPlanError,
        ):
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Acceptance authority changed",
                    "No preview or browser effect was authorized. Reload the governed state.",
                ),
            )
        except CustomerAcceptanceReconciliationRequired:
            return _respond(
                start_response,
                "502 Bad Gateway",
                _message(
                    "Acceptance requires reconciliation",
                    "ASCOS stopped without retrying. Inspect the workflow, preview, and browser evidence before continuing.",
                ),
            )
        except (
            CustomerAcceptanceCorrupt,
            CustomerDeliveryCorrupt,
            CustomerEvidenceCorrupt,
            BrowserArtifactError,
        ):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message(
                    "Acceptance evidence unavailable",
                    "ASCOS stopped because exact preview evidence could not be verified.",
                ),
            )
        if base is not None or action is not None:
            return _respond(
                start_response,
                "405 Method Not Allowed",
                _message("Method not allowed", "Use the displayed governed dashboard action."),
                extra_headers=[("Allow", "GET" if base is not None else "POST")],
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The acceptance page does not exist."),
        )


def _fields(environ: dict[str, object], action: str) -> dict[str, list[str]]:
    expected = {
        "prepare": {"csrf_token"},
        "approve": {"csrf_token", "approval_digest", "confirm_scope"},
        "execute": {
            "csrf_token",
            "approval_digest",
            "confirm_preview",
            "confirm_browser",
        },
    }[action]
    content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0].strip().lower()
    try:
        length = int(str(environ.get("CONTENT_LENGTH", "")))
    except ValueError:
        length = -1
    stream = environ.get("wsgi.input")
    if (
        content_type != "application/x-www-form-urlencoded"
        or not 0 <= length <= _MAX_BODY
        or stream is None
        or not hasattr(stream, "read")
    ):
        raise ValueError("Invalid acceptance form")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid acceptance form body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=8,
    )
    if set(fields) != expected or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected acceptance fields")
    return fields


def _dashboard(
    request_id: str,
    record: CustomerAcceptanceRecord | None,
    csrf: str,
    *,
    configured: bool,
    live_enabled: bool,
) -> str:
    if record is None:
        action = (
            f'''<form method="post" action="/customer/requests/{escape(request_id)}/acceptance/prepare">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<button type="submit">Prepare exact preview acceptance</button></form>'''
            if configured
            else ""
        )
        notice = (
            "The operator-bound preview workflow and browser plan are ready. Preparing the plan performs no external effect."
            if configured
            else "Restart the launcher with a trusted preview workflow, preview origin, and declarative journey plan."
        )
        content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(request_id)}/delivery">← Draft delivery</a>
<div class="review-head"><div><span class="eyebrow">Completion Module 5 · Preview acceptance</span>
<h1>Approve isolated end-user testing</h1><p>Bind the exact draft-delivery commit to one non-production preview and locked browser journeys.</p></div>
<span class="status">{'Ready to plan' if configured else 'Operator setup required'}</span></div>
<div class="notice"><strong>No external authority yet</strong><p>{escape(notice)}</p></div>
<div class="actions">{action}<a class="button secondary" href="/customer/requests/{escape(request_id)}/delivery">Return to delivery</a></div>
<div class="notice"><strong>Hard boundary</strong><p>This module cannot approve or merge the draft PR, target production, release, or start FamilyVault.</p></div></section>'''
        return _layout("Preview acceptance · ASCOS", content, csrf)

    journeys = "".join(
        f"<li><strong>{escape(value.title)}</strong><br><code>{escape(value.start_path)}</code> · {value.step_count} steps</li>"
        for value in record.journeys
    )
    action = _action(record, csrf, live_enabled)
    receipt = _receipt(record)
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(request_id)}/delivery">← Draft delivery</a>
<div class="review-head"><div><span class="eyebrow">Completion Module 5 · Preview acceptance</span>
<h1>Governed preview and end-user testing</h1><p>One exact draft commit, one isolated preview, and one locked browser run.</p></div>
<span class="status">{escape(record.status.value.replace('_', ' ').title())}</span></div>
<div class="signals"><span><strong>Repository</strong>{escape(record.repository_full_name)}</span>
<span><strong>Commit</strong>{escape(record.commit_sha[:12])}</span>
<span><strong>Preview</strong>{escape(record.preview_url)}</span>
<span><strong>Journeys</strong>{len(record.journeys)}</span></div>
<article class="journey"><h2>Locked end-user journeys</h2><ol>{journeys}</ol>
<p><strong>Automated test gate</strong> {escape(record.automated_test_job)}<br>
<strong>Security gate</strong> {escape(record.security_job)}<br>
<strong>Browser plan</strong> <code>{escape(record.browser_plan_digest)}</code></p></article>
{receipt}{action}
<div class="receipt"><dl><dt>Acceptance authority</dt><dd><code>{escape(record.acceptance_id)}</code></dd>
<dt>Locked approval digest</dt><dd><code>{escape(record.approval_digest)}</code></dd>
<dt>Draft PR</dt><dd><a href="{escape(record.pull_request_url)}">#{record.pull_request_number}</a> remains open, draft, and unmerged</dd></dl></div>
<div class="notice"><strong>Final non-production boundary</strong><p>Success publishes preview evidence for ACCEPT/REVISE review. It never merges, deploys production, releases, or starts FamilyVault.</p></div></section>'''
    return _layout("Governed preview acceptance · ASCOS", content, csrf)


def _action(record: CustomerAcceptanceRecord, csrf: str, live_enabled: bool) -> str:
    target = f"/customer/requests/{escape(record.request_id)}/acceptance"
    if record.status is CustomerAcceptanceStatus.AWAITING_APPROVAL:
        return f'''<form method="post" action="{target}/approve">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="approval_digest" value="{escape(record.approval_digest)}">
<label class="check"><input type="checkbox" name="confirm_scope" value="yes" required>
<span>I reviewed the exact commit, draft PR, preview origin, workflow gates, and ordered browser journeys.</span></label>
<div class="actions"><button type="submit">Approve exact preview acceptance</button></div></form>'''
    if record.status is CustomerAcceptanceStatus.APPROVED:
        if not live_enabled:
            return '''<div class="notice"><strong>Preview effects disabled by operator</strong>
<p>The plan is approved, but the launcher lacks all three Module 5 enablement flags.</p></div>'''
        return f'''<form method="post" action="{target}/execute">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="approval_digest" value="{escape(record.approval_digest)}">
<label class="check"><input type="checkbox" name="confirm_preview" value="yes" required>
<span>Dispatch one isolated non-production preview workflow for this exact commit.</span></label>
<label class="check"><input type="checkbox" name="confirm_browser" value="yes" required>
<span>Run the locked end-user journeys and capture secret-safe browser evidence.</span></label>
<div class="actions"><button type="submit">Deploy preview and run acceptance</button></div></form>'''
    if record.status is CustomerAcceptanceStatus.EVIDENCE_READY:
        return f'''<div class="actions"><a class="button" href="/customer/requests/{escape(record.request_id)}/evidence">Review preview evidence</a>
<a class="button secondary" href="{escape(record.preview_url)}/">Open isolated preview</a></div>'''
    if record.status is CustomerAcceptanceStatus.RECONCILIATION_REQUIRED:
        return '''<div class="notice"><strong>Manual reconciliation required</strong>
<p>ASCOS will not retry a possibly-created preview or browser run.</p></div>'''
    return '<div class="notice"><strong>Execution is in progress</strong><p>Do not submit a second request.</p></div>'


def _receipt(record: CustomerAcceptanceRecord) -> str:
    if record.status is not CustomerAcceptanceStatus.EVIDENCE_READY:
        return ""
    return f'''<article class="journey"><h2>Durable preview acceptance receipt</h2>
<p><strong>Workflow run</strong> <a href="{escape(record.workflow_run_url or '')}">#{record.workflow_run_id}</a><br>
<strong>Deployment revision</strong> <code>{escape(record.deployment_revision or '')}</code><br>
<strong>Deployment receipt</strong> <code>{escape(record.deployment_receipt_digest or '')}</code><br>
<strong>Browser execution</strong> <code>{escape(record.browser_execution_digest or '')}</code><br>
<strong>Evidence package</strong> <code>{escape(record.evidence_package_digest or '')}</code></p></article>'''
