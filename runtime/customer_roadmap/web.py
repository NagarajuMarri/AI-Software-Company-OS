"""WSGI generation checkpoint and review page for customer roadmap drafts."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_prd import (
    CustomerPrdApprovalConflict,
    CustomerPrdApprovalCorrupt,
    CustomerPrdConflict,
    CustomerPrdCorrupt,
    CustomerPrdDraft,
    CustomerPrdRequirement,
)
from runtime.customer_requirements import (
    RequirementsApprovalConflict,
    RequirementsApprovalCorrupt,
    RequirementsDraftCorrupt,
)
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond
from runtime.customer_roadmap.errors import CustomerRoadmapConflict, CustomerRoadmapCorrupt
from runtime.customer_roadmap.models import CustomerRoadmapDraft, CustomerRoadmapMilestone
from runtime.customer_roadmap.service import CustomerRoadmapService


_GENERATE = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/roadmap$"
)
_REVIEW = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/roadmap/review$"
)
_FIELDS = {"csrf_token", "expected_prd_approval_digest"}
_MAX_BODY = 8_192


class CustomerRoadmapApplication:
    """Generate a traceable planning draft without starting implementation."""

    def __init__(self, service: CustomerRoadmapService) -> None:
        self._service = service

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
        selected = generate or review
        request_id = selected.group(1) if selected is not None else ""
        try:
            if generate and method == "GET":
                _, prd, approval, roadmap = self._service.context(customer_id, request_id)
                if roadmap is not None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{request_id}/roadmap/review",
                    )
                if prd is None:
                    return _redirect(start_response, f"/customer/requests/{request_id}/prd")
                if approval is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{request_id}/prd/approve",
                    )
                return _respond(
                    start_response,
                    "200 OK",
                    _generation_checkpoint(prd, approval.digest, csrf),
                )
            if generate and method == "POST":
                return self._generate(
                    environ,
                    start_response,
                    customer_id,
                    request_id,
                    csrf,
                )
            if review and method == "GET":
                _, prd, _, roadmap = self._service.context(customer_id, request_id)
                if roadmap is None or prd is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{request_id}/roadmap",
                    )
                return _respond(start_response, "200 OK", _roadmap_review(prd, roadmap, csrf))
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except (
            CustomerRoadmapConflict,
            CustomerPrdApprovalConflict,
            CustomerPrdConflict,
            RequirementsApprovalConflict,
        ):
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Roadmap source changed",
                    "Reload the exact locked PRD before creating its roadmap.",
                ),
            )
        except (
            CustomerRoadmapCorrupt,
            CustomerPrdApprovalCorrupt,
            CustomerPrdCorrupt,
            RequirementsApprovalCorrupt,
            RequirementsDraftCorrupt,
        ):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message("Roadmap unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested roadmap page does not exist."),
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
            if not hmac.compare_digest(fields["csrf_token"], csrf):
                raise ValueError("CSRF mismatch")
            value = self._service.generate(
                customer_id=customer_id,
                request_id=request_id,
                expected_prd_approval_digest=fields["expected_prd_approval_digest"],
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message("Roadmap not created", "Reload the exact roadmap checkpoint."),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/roadmap/review",
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
        raise ValueError("Invalid customer roadmap request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid customer roadmap body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=4,
    )
    if set(fields) != _FIELDS or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected customer roadmap fields")
    return {name: values[0] for name, values in fields.items()}


def _generation_checkpoint(
    prd: CustomerPrdDraft,
    prd_approval_digest: str,
    csrf: str,
) -> str:
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(prd.request_id)}/prd/approved">← Locked PRD</a>
<div class="review-head"><div><span class="eyebrow">Roadmap generation checkpoint · PRD {escape(prd.version)}</span>
<h1>Create a roadmap draft for {escape(prd.title)}</h1>
<p>ASCOS will group every locked requirement into deterministic governed milestones.</p></div>
<span class="status">Action required</span></div>
<div class="signals"><span><strong>Locked requirements</strong>{len(prd.requirements)}</span>
<span><strong>PRD version</strong>{escape(prd.version)}</span><span><strong>Output</strong>DRAFT</span></div>
<div class="notice"><strong>This creates a planning draft only</strong>
<p>The roadmap contains exact requirement mappings and ordering. It contains no estimate, date, schedule commitment, staffing, agent assignment, repository access, code, deployment, billing, release authority, or official pilot-product selection.</p></div>
<form method="post" action="/customer/requests/{escape(prd.request_id)}/roadmap">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_prd_approval_digest" value="{escape(prd_approval_digest)}">
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(prd.request_id)}/prd/approved">Review locked PRD</a>
<button type="submit">Generate roadmap draft</button></div></form>
<footer>PRD <code>{escape(prd.prd_id)}</code> · Locked artifact <code>{escape(prd.digest)}</code><br>
Approval <code>{escape(prd_approval_digest)}</code></footer></section>'''
    return _layout(f"Roadmap for {prd.title} · ASCOS", content, csrf)


def _roadmap_review(
    prd: CustomerPrdDraft,
    roadmap: CustomerRoadmapDraft,
    csrf: str,
) -> str:
    requirements = {item.requirement_id: item for item in prd.requirements}
    milestones = "".join(_milestone_card(item, requirements) for item in roadmap.milestones)
    generated = roadmap.generated_at.strftime("%d %b %Y, %H:%M UTC")
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(prd.request_id)}/prd/approved">← Locked PRD</a>
<div class="review-head"><div><span class="eyebrow">Customer delivery roadmap · Version 0.1</span>
<h1>{escape(roadmap.title)}</h1><p>Every item is derived from the exact locked PRD.</p></div>
<span class="status">Draft generated</span></div>
<div class="signals"><span><strong>Status</strong>{escape(roadmap.status)}</span>
<span><strong>Milestones</strong>{len(roadmap.milestones)}</span>
<span><strong>Mapped requirements</strong>{len(roadmap.requirement_ids)}</span></div>
<h2 class="section-title">Traceable milestones</h2><div class="prd-list">{milestones}</div>
<div class="receipt"><dl><dt>Generated</dt><dd>{escape(generated)}</dd>
<dt>Roadmap</dt><dd><code>{escape(roadmap.roadmap_id)}</code></dd>
<dt>Locked PRD digest</dt><dd><code>{escape(roadmap.prd_digest)}</code></dd>
<dt>Roadmap digest</dt><dd><code>{escape(roadmap.digest)}</code></dd></dl></div>
<div class="notice"><strong>Draft plan — no execution authority</strong>
<p>No estimates, dates, schedule commitments, staffing, agents, repositories, coding, merge, deployment, billing, release, or pilot-product selection have been authorized.</p></div>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(prd.request_id)}/prd/approved">View locked PRD</a>
<a class="button secondary" href="/customer">Return to workspace</a></div></section>'''
    return _layout(f"Draft roadmap for {prd.title} · ASCOS", content, csrf)


def _milestone_card(
    value: CustomerRoadmapMilestone,
    requirements: Mapping[str, CustomerPrdRequirement],
) -> str:
    items = "".join(
        f'''<li><code>{escape(requirement_id)}</code> — {escape(requirements[requirement_id].title)}
<span>{escape(priority.value.title())}</span></li>'''
        for requirement_id, priority in zip(
            value.requirement_ids,
            value.priorities,
            strict=True,
        )
    )
    return f'''<article class="prd-requirement"><div class="prd-meta"><span>Milestone {value.sequence}</span>
<span>{escape(value.status)}</span><span>{len(value.requirement_ids)} requirements</span></div>
<h2>{escape(value.milestone)}</h2><ul>{items}</ul>
<div class="trace">Governed item: <code>{escape(value.roadmap_item_id)}</code></div></article>'''
