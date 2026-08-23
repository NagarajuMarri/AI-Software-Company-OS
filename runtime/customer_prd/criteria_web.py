"""WSGI checkpoint for customer-authored feature acceptance criteria."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from typing import Protocol
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_prd.criteria_models import CustomerPrdCriteriaRefinement
from runtime.customer_prd.criteria_service import CustomerPrdCriteriaService
from runtime.customer_prd.errors import (
    CustomerPrdConflict,
    CustomerPrdCorrupt,
    CustomerPrdCriteriaConflict,
    CustomerPrdCriteriaCorrupt,
)
from runtime.customer_prd.models import CustomerPrdDraft, CustomerPrdRequirement
from runtime.customer_requirements import (
    RequirementsApprovalConflict,
    RequirementsApprovalCorrupt,
    RequirementsDraftCorrupt,
)
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond


_CRITERIA = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/prd/criteria$"
)
_BASE_FIELDS = {"csrf_token", "expected_prd_digest", "confirmation"}
_MAX_BODY = 131_072


class CustomerPrdLockLookup(Protocol):
    """Read-only PRD lock boundary used to stop post-approval refinement."""

    def is_locked(self, customer_id: str, request_id: str) -> bool: ...


class CustomerPrdCriteriaApplication:
    """Collect and lock one complete feature-criteria baseline."""

    def __init__(
        self,
        service: CustomerPrdCriteriaService,
        approvals: CustomerPrdLockLookup | None = None,
    ) -> None:
        self._service = service
        self._approvals = approvals

    @staticmethod
    def handles(path: str) -> bool:
        return _CRITERIA.fullmatch(path) is not None

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
        path = str(environ.get("PATH_INFO", "/"))
        match = _CRITERIA.fullmatch(path)
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if match is None:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Page not found", "The criteria page does not exist."),
            )
        request_id = match.group(1)
        try:
            if self._approvals is not None and self._approvals.is_locked(
                customer_id,
                request_id,
            ):
                return _redirect(
                    start_response,
                    f"/customer/requests/{request_id}/prd/approved",
                )
            prd, refinement = self._service.context(customer_id, request_id)
            if prd is None:
                return _redirect(start_response, f"/customer/requests/{request_id}/prd")
            if method == "GET":
                if refinement is not None:
                    effective = self._service.effective_prd(customer_id, request_id, required=True)
                    assert effective is not None
                    return _respond(
                        start_response,
                        "200 OK",
                        _locked_receipt(effective, refinement, csrf),
                    )
                return _respond(start_response, "200 OK", _criteria_form(prd, csrf))
            if method == "POST":
                return self._lock(environ, start_response, customer_id, prd, csrf)
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except (
            CustomerPrdCriteriaConflict,
            CustomerPrdConflict,
            RequirementsApprovalConflict,
        ):
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Acceptance criteria changed",
                    "Reload the exact PRD before locking its feature criteria.",
                ),
            )
        except (
            CustomerPrdCriteriaCorrupt,
            CustomerPrdCorrupt,
            RequirementsApprovalCorrupt,
            RequirementsDraftCorrupt,
        ):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message("Acceptance criteria unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "405 Method Not Allowed",
            _message("Method not allowed", "Use the criteria review form."),
            extra_headers=[("Allow", "GET, POST")],
        )

    def _lock(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
        customer_id: str,
        prd: CustomerPrdDraft,
        csrf: str,
    ) -> Iterable[bytes]:
        try:
            feature_ids = tuple(
                item.requirement_id
                for item in prd.requirements
                if item.requirement_id.startswith("REQ-FEATURE-")
            )
            fields = _form_fields(environ, feature_ids)
            if not hmac.compare_digest(fields["csrf_token"], csrf):
                raise ValueError("CSRF mismatch")
            criteria = {
                requirement_id: _criteria_lines(fields[f"criteria__{requirement_id}"])
                for requirement_id in feature_ids
            }
            value = self._service.lock(
                customer_id=customer_id,
                request_id=prd.request_id,
                expected_prd_digest=fields["expected_prd_digest"],
                criteria=criteria,
                confirmed=fields["confirmation"] == "LOCK",
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message(
                    "Criteria not locked",
                    "Provide two to five specific criteria for every feature and confirm review.",
                ),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/prd/review",
        )


def _form_fields(environ: dict[str, object], feature_ids: tuple[str, ...]) -> dict[str, str]:
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
        raise ValueError("Invalid customer PRD criteria request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid customer PRD criteria body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=30,
    )
    expected = _BASE_FIELDS | {f"criteria__{item}" for item in feature_ids}
    if set(fields) != expected or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected customer PRD criteria fields")
    return {name: values[0] for name, values in fields.items()}


def _criteria_lines(value: str) -> tuple[str, ...]:
    lines = tuple(line.strip() for line in value.splitlines() if line.strip())
    if not 2 <= len(lines) <= 5:
        raise ValueError("Two to five criteria are required")
    return lines


def _feature_requirements(value: CustomerPrdDraft) -> tuple[CustomerPrdRequirement, ...]:
    return tuple(
        item for item in value.requirements if item.requirement_id.startswith("REQ-FEATURE-")
    )


def _criteria_form(value: CustomerPrdDraft, csrf: str) -> str:
    cards = "".join(
        f'''<article class="prd-requirement"><div class="prd-meta"><span>{escape(item.requirement_id)}</span>
<span>Feature criteria</span><span>Required</span></div><h2>{escape(item.title)}</h2>
<p>{escape(item.description)}</p><label>Specific testable criteria <span>one per line; 2–5 required</span>
<textarea name="criteria__{escape(item.requirement_id)}" rows="6" required>{escape(chr(10).join(item.acceptance_criteria))}</textarea></label>
<div class="trace">Approved source: <code>{escape(item.source_reference)}</code></div></article>'''
        for item in _feature_requirements(value)
    )
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(value.request_id)}/prd/review">← PRD draft</a>
<div class="review-head"><div><span class="eyebrow">Governed criteria refinement · PRD {escape(value.version)}</span>
<h1>Refine feature acceptance criteria</h1><p>Replace every generated template with observable, measurable product behavior.</p></div>
<span class="status">Action required</span></div>
<div class="notice"><strong>This checkpoint uses no external AI and no repository</strong>
<p>Only acceptance criteria for approved feature requirements may change. Scope, constraints, exclusions, metrics, and source references remain fixed.</p></div>
<form method="post" action="/customer/requests/{escape(value.request_id)}/prd/criteria">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_prd_digest" value="{escape(value.digest)}">
<div class="prd-list">{cards}</div>
<label class="confirm"><input type="checkbox" name="confirmation" value="LOCK" required>
<span>I reviewed every feature criterion and lock this exact criteria baseline.</span></label>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(value.request_id)}/prd/review">Cancel</a>
<button type="submit">Lock refined criteria</button></div></form>
<footer>Source PRD <code>{escape(value.digest)}</code></footer></section>'''
    return _layout(f"Refine {value.title} criteria · ASCOS", content, csrf)


def _locked_receipt(
    value: CustomerPrdDraft,
    refinement: CustomerPrdCriteriaRefinement,
    csrf: str,
) -> str:
    cards = "".join(
        f'''<article class="prd-requirement"><div class="prd-meta"><span>{escape(item.requirement_id)}</span>
<span>Refined and locked</span></div><h2>{escape(item.title)}</h2><ul>{''.join(f'<li>{escape(criterion)}</li>' for criterion in item.acceptance_criteria)}</ul></article>'''
        for item in _feature_requirements(value)
    )
    timestamp = refinement.locked_at.strftime("%d %b %Y, %H:%M UTC")
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(value.request_id)}/prd/review">← PRD review</a>
<div class="review-head"><div><span class="eyebrow">Governed criteria baseline</span>
<h1>Feature acceptance criteria are locked</h1><p>The refined criteria now form part of the exact PRD proposed for approval.</p></div>
<span class="status approved">Locked</span></div><div class="prd-list">{cards}</div>
<div class="receipt"><dl><dt>Locked</dt><dd>{escape(timestamp)}</dd>
<dt>Refinement</dt><dd><code>{escape(refinement.refinement_id)}</code></dd>
<dt>Digest</dt><dd><code>{escape(refinement.digest)}</code></dd></dl></div>
<div class="actions"><a class="button" href="/customer/requests/{escape(value.request_id)}/prd/approve">Review and approve PRD</a>
<a class="button secondary" href="/customer/requests/{escape(value.request_id)}/prd/review">Return to PRD</a></div></section>'''
    return _layout(f"Locked criteria · {value.title} · ASCOS", content, csrf)
