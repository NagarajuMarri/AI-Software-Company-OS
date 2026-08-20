"""WSGI customer confirmation and immutable requirements-approval receipt."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_requirements.approval_models import CustomerRequirementsApproval
from runtime.customer_requirements.approval_service import CustomerRequirementsApprovalService
from runtime.customer_requirements.errors import (
    RequirementsApprovalConflict,
    RequirementsApprovalCorrupt,
    RequirementsDraftCorrupt,
)
from runtime.customer_requirements.models import CustomerRequirementsDraft
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond


_APPROVE = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/requirements/approve$"
)
_APPROVED = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/requirements/approved$"
)
_FIELDS = {"csrf_token", "expected_revision", "expected_digest", "confirmation"}
_MAX_BODY = 8_192


class CustomerRequirementsApprovalApplication:
    """Require explicit customer confirmation before locking one exact draft."""

    def __init__(self, service: CustomerRequirementsApprovalService) -> None:
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
                request, draft, receipt = self._service.context(customer_id, approve.group(1))
                if receipt is not None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approve.group(1)}/requirements/approved",
                    )
                if draft is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approve.group(1)}/requirements",
                    )
                return _respond(
                    start_response,
                    "200 OK",
                    _approval_form(request.product_name, draft, csrf),
                )
            if approve and method == "POST":
                return self._approve(
                    environ,
                    start_response,
                    customer_id,
                    approve.group(1),
                    csrf,
                )
            if approved and method == "GET":
                request, draft, receipt = self._service.context(customer_id, approved.group(1))
                if draft is None or receipt is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approved.group(1)}/requirements/review",
                    )
                return _respond(
                    start_response,
                    "200 OK",
                    _approved_receipt(request.product_name, draft, receipt, csrf),
                )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except RequirementsApprovalConflict:
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Approval changed",
                    "Reload the latest requirements draft before approving it.",
                ),
            )
        except (RequirementsApprovalCorrupt, RequirementsDraftCorrupt):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message("Approval unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested approval page does not exist."),
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
                expected_revision=int(fields["expected_revision"]),
                expected_digest=fields["expected_digest"],
                confirmed=fields["confirmation"] == "LOCK",
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message(
                    "Requirements not approved",
                    "Review the exact scope and select the confirmation checkbox.",
                ),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/requirements/approved",
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
        raise ValueError("Invalid approval request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid approval body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=8,
    )
    if set(fields) != _FIELDS or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected approval fields")
    return {name: values[0] for name, values in fields.items()}


def _items(values: tuple[str, ...], empty: str = "None declared") -> str:
    if not values:
        return f"<li>{escape(empty)}</li>"
    return "".join(f"<li>{escape(item)}</li>" for item in values)


def _scope(value: CustomerRequirementsDraft) -> str:
    return f'''<article class="journey"><h2>Primary user journey</h2><p>{escape(value.primary_user_journey)}</p></article>
<div class="grid"><article><h2>Desired outcomes</h2><ul>{_items(value.desired_outcomes)}</ul></article>
<article><h2>Must-have features</h2><ul>{_items(value.must_have_features)}</ul></article>
<article><h2>Success metrics</h2><ul>{_items(value.success_metrics)}</ul></article>
<article><h2>Non-goals</h2><ul>{_items(value.non_goals)}</ul></article></div>
<div class="signals"><span><strong>Platforms</strong>{escape(', '.join(item.title() for item in value.platforms))}</span>
<span><strong>Data</strong>{escape(value.data_sensitivity.value.replace('_', ' ').title())}</span>
<span><strong>Priority</strong>{escape(value.delivery_priority.value.replace('_', ' ').title())}</span></div>'''


def _approval_form(product_name: str, value: CustomerRequirementsDraft, csrf: str) -> str:
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(value.request_id)}/requirements/review">← Review draft</a>
<div class="review-head"><div><span class="eyebrow">Approval checkpoint · Revision {value.revision}</span>
<h1>Approve {escape(product_name)}</h1><p>Confirm the exact requirements baseline that ASCOS may use in the next governed step.</p></div>
<span class="status">Action required</span></div>{_scope(value)}
<div class="notice"><strong>This action permanently locks revision {value.revision}</strong>
<p>You will no longer be able to edit this draft. Approval does not start planning, coding, agents, or deployment.</p></div>
<form method="post" action="/customer/requests/{escape(value.request_id)}/requirements/approve">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_revision" value="{value.revision}">
<input type="hidden" name="expected_digest" value="{escape(value.digest)}">
<label class="confirm"><input type="checkbox" name="confirmation" value="LOCK" required>
<span>I reviewed this exact scope and approve it as the immutable requirements baseline.</span></label>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(value.request_id)}/requirements">Edit instead</a>
<button type="submit">Approve and lock requirements</button></div></form>
<footer>Source request <code>{escape(value.source_request_digest)}</code><br>Draft <code>{escape(value.digest)}</code></footer></section>'''
    return _layout(f"Approve {product_name} · ASCOS", content, csrf)


def _approved_receipt(
    product_name: str,
    value: CustomerRequirementsDraft,
    receipt: CustomerRequirementsApproval,
    csrf: str,
) -> str:
    timestamp = receipt.approved_at.strftime("%d %b %Y, %H:%M UTC")
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(value.request_id)}">← Product request</a>
<div class="review-head"><div><span class="eyebrow">Requirements baseline · Revision {value.revision}</span>
<h1>{escape(product_name)}</h1><p>The customer-approved scope is locked and ready for the next governed step.</p></div>
<span class="status approved">Approved</span></div>{_scope(value)}
<div class="receipt"><dl><dt>Approved</dt><dd>{escape(timestamp)}</dd>
<dt>Receipt</dt><dd><code>{escape(receipt.approval_id)}</code></dd>
<dt>Requirements digest</dt><dd><code>{escape(receipt.requirements_digest)}</code></dd>
<dt>Receipt digest</dt><dd><code>{escape(receipt.digest)}</code></dd></dl></div>
<div class="notice"><strong>Approved baseline — implementation has not started</strong>
<p>PRD generation, planning, agent assignment, coding, and deployment remain separate governed modules.</p></div>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(value.request_id)}/requirements/review">View approved scope</a>
<a class="button" href="/customer">Return to workspace</a></div></section>'''
    return _layout(f"Approved requirements for {product_name} · ASCOS", content, csrf)
