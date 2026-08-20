"""WSGI customer approval checkpoint and immutable locked-PRD receipt."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_prd.approval_models import CustomerPrdApproval
from runtime.customer_prd.approval_service import CustomerPrdApprovalService
from runtime.customer_prd.errors import (
    CustomerPrdApprovalConflict,
    CustomerPrdApprovalCorrupt,
    CustomerPrdConflict,
    CustomerPrdCorrupt,
)
from runtime.customer_prd.models import CustomerPrdDraft, CustomerPrdRequirement
from runtime.customer_requirements import (
    RequirementsApprovalConflict,
    RequirementsApprovalCorrupt,
    RequirementsDraftCorrupt,
)
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond


_APPROVE = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/prd/approve$"
)
_APPROVED = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/prd/approved$"
)
_FIELDS = {"csrf_token", "expected_prd_digest", "confirmation"}
_MAX_BODY = 8_192


class CustomerPrdApprovalApplication:
    """Require explicit customer confirmation before locking one exact PRD."""

    def __init__(self, service: CustomerPrdApprovalService) -> None:
        self._service = service

    @staticmethod
    def handles(path: str) -> bool:
        return _APPROVE.fullmatch(path) is not None or _APPROVED.fullmatch(path) is not None

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
        approve = _APPROVE.fullmatch(path)
        approved = _APPROVED.fullmatch(path)
        try:
            if approve and method == "GET":
                _, _, _, prd, receipt = self._service.context(customer_id, approve.group(1))
                if receipt is not None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approve.group(1)}/prd/approved",
                    )
                if prd is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approve.group(1)}/prd",
                    )
                return _respond(start_response, "200 OK", _approval_form(prd, csrf))
            if approve and method == "POST":
                return self._approve(
                    environ,
                    start_response,
                    customer_id,
                    approve.group(1),
                    csrf,
                )
            if approved and method == "GET":
                _, _, _, prd, receipt = self._service.context(customer_id, approved.group(1))
                if prd is None or receipt is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approved.group(1)}/prd/review",
                    )
                locked = self._service.governed_document(customer_id, approved.group(1))
                return _respond(
                    start_response,
                    "200 OK",
                    _approved_receipt(prd, receipt, locked.status.value, csrf),
                )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except (
            CustomerPrdApprovalConflict,
            CustomerPrdConflict,
            RequirementsApprovalConflict,
        ):
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "PRD approval changed",
                    "Reload the exact PRD draft before approving it.",
                ),
            )
        except (
            CustomerPrdApprovalCorrupt,
            CustomerPrdCorrupt,
            RequirementsApprovalCorrupt,
            RequirementsDraftCorrupt,
        ):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message("PRD approval unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested PRD approval page does not exist."),
        )

    def _approve(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
        customer_id: str,
        request_id: str,
        csrf: str,
    ) -> Iterable[bytes]:
        try:
            fields = _form_fields(environ)
            if not hmac.compare_digest(fields["csrf_token"], csrf):
                raise ValueError("CSRF mismatch")
            value = self._service.approve(
                customer_id=customer_id,
                request_id=request_id,
                expected_prd_digest=fields["expected_prd_digest"],
                confirmed=fields["confirmation"] == "LOCK",
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message(
                    "PRD not approved",
                    "Review the exact PRD and select the confirmation checkbox.",
                ),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/prd/approved",
        )


def _form_fields(environ: dict[str, object]) -> dict[str, str]:
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
        raise ValueError("Invalid customer PRD approval request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid customer PRD approval body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=6,
    )
    if set(fields) != _FIELDS or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected customer PRD approval fields")
    return {name: values[0] for name, values in fields.items()}


def _scope(value: CustomerPrdDraft) -> str:
    requirements = "".join(_requirement_card(item) for item in value.requirements)
    exclusions = _items(value.explicit_exclusions)
    metrics = _items(value.success_metrics)
    return f'''<div class="scope-columns"><article><h2>Problem statement</h2><p>{escape(value.problem_statement)}</p></article>
<article><h2>Target users</h2><p>{escape(value.target_users)}</p></article></div>
<article class="journey"><h2>Primary user journey</h2><p>{escape(value.primary_user_journey)}</p></article>
<h2 class="section-title">Product requirements</h2><div class="prd-list">{requirements}</div>
<h2 class="section-title">Success and scope boundaries</h2>
<div class="scope-columns"><article><h2>Success metrics</h2><ul>{metrics}</ul></article>
<article><h2>Explicit exclusions</h2><ul>{exclusions}</ul></article></div>
<div class="signals"><span><strong>Platforms</strong>{escape(', '.join(item.title() for item in value.platforms))}</span>
<span><strong>Data</strong>{escape(value.data_sensitivity.value.replace('_', ' ').title())}</span>
<span><strong>Priority</strong>{escape(value.delivery_priority.value.replace('_', ' ').title())}</span></div>'''


def _items(values: tuple[str, ...]) -> str:
    if not values:
        return "<li>None declared</li>"
    return "".join(f"<li>{escape(item)}</li>" for item in values)


def _requirement_card(value: CustomerPrdRequirement) -> str:
    criteria = _items(value.acceptance_criteria)
    return f'''<article class="prd-requirement"><div class="prd-meta"><span>{escape(value.requirement_id)}</span>
<span>{escape(value.category.value.replace('_', ' ').title())}</span><span>{escape(value.priority.value.title())}</span></div>
<h2>{escape(value.title)}</h2><p>{escape(value.description)}</p>
<h3>Acceptance criteria</h3><ul>{criteria}</ul>
<div class="trace">Approved source: <code>{escape(value.source_reference)}</code></div></article>'''


def _approval_form(value: CustomerPrdDraft, csrf: str) -> str:
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(value.request_id)}/prd/review">← Review PRD draft</a>
<div class="review-head"><div><span class="eyebrow">PRD approval checkpoint · Version {escape(value.version)}</span>
<h1>Approve and lock {escape(value.title)}</h1>
<p>Review every requirement, acceptance criterion, success signal, and exclusion before confirming.</p></div>
<span class="status">Action required</span></div>{_scope(value)}
<div class="notice"><strong>This action permanently locks PRD version {escape(value.version)}</strong>
<p>The locked PRD becomes eligible only for a separately governed planning module. This action does not create a roadmap, estimate work, assign agents, connect repositories, code, deploy, bill, or release.</p></div>
<form method="post" action="/customer/requests/{escape(value.request_id)}/prd/approve">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_prd_digest" value="{escape(value.digest)}">
<label class="confirm"><input type="checkbox" name="confirmation" value="LOCK" required>
<span>I reviewed this exact PRD and approve it as the immutable product scope.</span></label>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(value.request_id)}/prd/review">Review again</a>
<button type="submit">Approve and lock PRD</button></div></form>
<footer>PRD <code>{escape(value.prd_id)}</code> · Version <code>{escape(value.version)}</code><br>
Artifact <code>{escape(value.digest)}</code> · Approved source <code>{escape(value.approval_digest)}</code></footer></section>'''
    return _layout(f"Approve {value.title} · ASCOS", content, csrf)


def _approved_receipt(
    value: CustomerPrdDraft,
    receipt: CustomerPrdApproval,
    governed_status: str,
    csrf: str,
) -> str:
    timestamp = receipt.approved_at.strftime("%d %b %Y, %H:%M UTC")
    content = f'''<section class="review"><a class="back" href="/customer">← Customer workspace</a>
<div class="review-head"><div><span class="eyebrow">PRD {escape(value.version)} · Immutable baseline</span>
<h1>{escape(value.title)}</h1><p>The exact customer-reviewed PRD is approved and locked.</p></div>
<span class="status approved">Approved and locked</span></div>{_scope(value)}
<div class="receipt"><dl><dt>Governed status</dt><dd>{escape(governed_status)}</dd>
<dt>Approved</dt><dd>{escape(timestamp)}</dd><dt>Receipt</dt><dd><code>{escape(receipt.approval_id)}</code></dd>
<dt>PRD digest</dt><dd><code>{escape(receipt.prd_digest)}</code></dd>
<dt>Receipt digest</dt><dd><code>{escape(receipt.digest)}</code></dd></dl></div>
<div class="notice"><strong>Locked scope — planning and implementation have not started</strong>
<p>Roadmaps, estimates, agent assignment, repository access, coding, merge, deployment, billing, and release require separate founder-governed modules.</p></div>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(value.request_id)}/requirements/approved">View approved source</a>
<a class="button secondary" href="/customer">Return to workspace</a></div></section>'''
    return _layout(f"Approved {value.title} · ASCOS", content, csrf)
