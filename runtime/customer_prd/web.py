"""WSGI generation checkpoint and customer PRD draft review."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from typing import Protocol
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_prd.errors import (
    CustomerPrdApprovalConflict,
    CustomerPrdApprovalCorrupt,
    CustomerPrdConflict,
    CustomerPrdCorrupt,
)
from runtime.customer_prd.models import CustomerPrdDraft, CustomerPrdRequirement
from runtime.customer_prd.service import CustomerPrdService
from runtime.customer_requirements import (
    RequirementsApprovalConflict,
    RequirementsApprovalCorrupt,
    RequirementsDraftCorrupt,
)
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond


_GENERATE = re.compile(r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/prd$")
_REVIEW = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/prd/review$"
)
_FIELDS = {"csrf_token", "expected_approval_digest", "action"}
_MAX_BODY = 4_096


class CustomerPrdApprovalLookup(Protocol):
    """Read-only lock lookup used to route an approved PRD consistently."""

    def is_locked(self, customer_id: str, request_id: str) -> bool: ...


class CustomerPrdApplication:
    """Generate one source-bound PRD draft and expose read-only customer review."""

    def __init__(
        self,
        service: CustomerPrdService,
        approvals: CustomerPrdApprovalLookup | None = None,
    ) -> None:
        self._service = service
        self._approvals = approvals

    @staticmethod
    def handles(path: str) -> bool:
        return _GENERATE.fullmatch(path) is not None or _REVIEW.fullmatch(path) is not None

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
        generate = _GENERATE.fullmatch(path)
        review = _REVIEW.fullmatch(path)
        try:
            if generate and method == "GET":
                request, draft, approval, prd = self._service.context(
                    customer_id,
                    generate.group(1),
                )
                if prd is not None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{generate.group(1)}/prd/review",
                    )
                if draft is None or approval is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{generate.group(1)}/requirements/approved",
                    )
                return _respond(
                    start_response,
                    "200 OK",
                    _generation_checkpoint(
                        request.product_name,
                        draft.revision,
                        approval.digest,
                        generate.group(1),
                        csrf,
                    ),
                )
            if generate and method == "POST":
                return self._generate(
                    environ,
                    start_response,
                    customer_id,
                    generate.group(1),
                    csrf,
                )
            if review and method == "GET":
                _, _, approval, prd = self._service.context(customer_id, review.group(1))
                if approval is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{review.group(1)}/requirements/approved",
                    )
                if prd is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{review.group(1)}/prd",
                    )
                if (
                    self._approvals is not None
                    and self._approvals.is_locked(customer_id, review.group(1))
                ):
                    return _redirect(
                        start_response,
                        f"/customer/requests/{review.group(1)}/prd/approved",
                    )
                return _respond(start_response, "200 OK", _prd_review(prd, csrf))
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
                    "PRD source changed",
                    "Reload the approved requirements before generating the PRD draft.",
                ),
            )
        except (
            CustomerPrdCorrupt,
            CustomerPrdApprovalCorrupt,
            RequirementsApprovalCorrupt,
            RequirementsDraftCorrupt,
        ):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message("PRD unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested PRD page does not exist."),
        )

    def _generate(
        self,
        environ: dict[str, object],
        start_response: Callable[[str, list[tuple[str, str]]], object],
        customer_id: str,
        request_id: str,
        csrf: str,
    ) -> Iterable[bytes]:
        try:
            fields = _form_fields(environ)
            if (
                not hmac.compare_digest(fields["csrf_token"], csrf)
                or fields["action"] != "GENERATE"
            ):
                raise ValueError("Invalid PRD generation confirmation")
            value = self._service.generate(
                customer_id=customer_id,
                request_id=request_id,
                expected_approval_digest=fields["expected_approval_digest"],
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message("PRD not generated", "Reload the approved requirements and try again."),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/prd/review",
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
        raise ValueError("Invalid customer PRD request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid customer PRD body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=6,
    )
    if set(fields) != _FIELDS or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected customer PRD fields")
    return {name: values[0] for name, values in fields.items()}


def _generation_checkpoint(
    product_name: str,
    revision: int,
    approval_digest: str,
    request_id: str,
    csrf: str,
) -> str:
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(request_id)}/requirements/approved">← Approved requirements</a>
<div class="review-head"><div><span class="eyebrow">Product manager · PRD draft</span>
<h1>Create the PRD for {escape(product_name)}</h1>
<p>ASCOS will convert approved requirements revision {revision} into a traceable draft for your review.</p></div>
<span class="status">Ready to generate</span></div>
<div class="scope-columns"><article><h2>What will be created</h2><p>Problem, target users, primary journey, functional requirements, acceptance criteria, delivery boundaries, exclusions, and source references.</p></article>
<article><h2>How it is generated</h2><p>A deterministic profile uses only the approved customer baseline. No external AI call or repository access occurs.</p></article></div>
<div class="notice"><strong>Generation creates a draft only</strong>
<p>PRD review, approval, locking, planning, agent assignment, coding, and deployment remain separate governed steps.</p></div>
<form method="post" action="/customer/requests/{escape(request_id)}/prd">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_approval_digest" value="{escape(approval_digest)}">
<input type="hidden" name="action" value="GENERATE">
<div class="actions"><a class="button secondary" href="/customer">Return to workspace</a>
<button type="submit">Generate PRD draft</button></div></form>
<footer>Approval receipt <code>{escape(approval_digest)}</code></footer></section>'''
    return _layout(f"Create PRD for {product_name} · ASCOS", content, csrf)


def _prd_review(value: CustomerPrdDraft, csrf: str) -> str:
    requirements = "".join(_requirement_card(item) for item in value.requirements)
    exclusions = (
        "".join(f"<li>{escape(item)}</li>" for item in value.explicit_exclusions)
        if value.explicit_exclusions
        else "<li>None declared</li>"
    )
    metrics = "".join(f"<li>{escape(item)}</li>" for item in value.success_metrics)
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(value.request_id)}/requirements/approved">← Approved requirements</a>
<div class="review-head"><div><span class="eyebrow">PRD {escape(value.version)} · Product manager draft</span>
<h1>{escape(value.title)}</h1><p>Traceable draft generated from the exact customer-approved baseline.</p></div>
<span class="status">Draft generated</span></div>
<div class="scope-columns"><article><h2>Problem statement</h2><p>{escape(value.problem_statement)}</p></article>
<article><h2>Target users</h2><p>{escape(value.target_users)}</p></article></div>
<article class="journey"><h2>Primary user journey</h2><p>{escape(value.primary_user_journey)}</p></article>
<h2 class="section-title">Product requirements</h2><div class="prd-list">{requirements}</div>
<h2 class="section-title">Success and scope boundaries</h2>
<div class="scope-columns"><article><h2>Success metrics</h2><ul>{metrics}</ul></article>
<article><h2>Explicit exclusions</h2><ul>{exclusions}</ul></article></div>
<div class="signals"><span><strong>Platforms</strong>{escape(', '.join(item.title() for item in value.platforms))}</span>
<span><strong>Data</strong>{escape(value.data_sensitivity.value.replace('_', ' ').title())}</span>
<span><strong>Priority</strong>{escape(value.delivery_priority.value.replace('_', ' ').title())}</span></div>
<div class="notice"><strong>PRD draft only — no implementation has started</strong>
<p>Review and approval are required before any later roadmap module. Planning, agents, repository access, coding, and deployment have not started.</p></div>
<div class="actions"><a class="button secondary" href="/customer">Return to workspace</a>
<a class="button secondary" href="/customer/requests/{escape(value.request_id)}/requirements/approved">View approved source</a>
<a class="button" href="/customer/requests/{escape(value.request_id)}/prd/approve">Review and approve PRD</a></div>
<footer>PRD <code>{escape(value.prd_id)}</code> · Artifact <code>{escape(value.digest)}</code><br>
Approved source <code>{escape(value.approval_digest)}</code> · Profile <code>{escape(value.generation_profile)}</code></footer></section>'''
    return _layout(f"{value.title} · ASCOS", content, csrf)


def _requirement_card(value: CustomerPrdRequirement) -> str:
    criteria = "".join(f"<li>{escape(item)}</li>" for item in value.acceptance_criteria)
    return f'''<article class="prd-requirement"><div class="prd-meta"><span>{escape(value.requirement_id)}</span>
<span>{escape(value.category.value.replace('_', ' ').title())}</span><span>{escape(value.priority.value.title())}</span></div>
<h2>{escape(value.title)}</h2><p>{escape(value.description)}</p>
<h3>Acceptance criteria</h3><ul>{criteria}</ul>
<div class="trace">Approved source: <code>{escape(value.source_reference)}</code></div></article>'''
