"""WSGI customer approval checkpoint and immutable locked-roadmap receipt."""

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
from runtime.customer_roadmap.approval_models import (
    CustomerRoadmapApproval,
    LockedCustomerRoadmap,
    LockedCustomerRoadmapMilestone,
)
from runtime.customer_roadmap.approval_service import CustomerRoadmapApprovalService
from runtime.customer_roadmap.errors import (
    CustomerRoadmapApprovalConflict,
    CustomerRoadmapApprovalCorrupt,
    CustomerRoadmapConflict,
    CustomerRoadmapCorrupt,
)
from runtime.customer_roadmap.models import CustomerRoadmapDraft, CustomerRoadmapMilestone


_APPROVE = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/roadmap/approve$"
)
_APPROVED = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/roadmap/approved$"
)
_FIELDS = {"csrf_token", "expected_roadmap_digest", "confirmation"}
_MAX_BODY = 8_192


class CustomerRoadmapApprovalApplication:
    """Require explicit customer confirmation before locking one exact roadmap."""

    def __init__(self, service: CustomerRoadmapApprovalService) -> None:
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
                _, prd, _, roadmap, receipt = self._service.context(
                    customer_id,
                    approve.group(1),
                )
                if receipt is not None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approve.group(1)}/roadmap/approved",
                    )
                if roadmap is None or prd is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approve.group(1)}/roadmap",
                    )
                return _respond(
                    start_response,
                    "200 OK",
                    _approval_form(prd, roadmap, csrf),
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
                _, prd, _, roadmap, receipt = self._service.context(
                    customer_id,
                    approved.group(1),
                )
                if prd is None or roadmap is None or receipt is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{approved.group(1)}/roadmap/review",
                    )
                locked = self._service.governed_roadmap(customer_id, approved.group(1))
                return _respond(
                    start_response,
                    "200 OK",
                    _approved_receipt(prd, roadmap, receipt, locked, csrf),
                )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except (
            CustomerRoadmapApprovalConflict,
            CustomerRoadmapConflict,
            CustomerPrdApprovalConflict,
            CustomerPrdConflict,
            RequirementsApprovalConflict,
        ):
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Roadmap approval changed",
                    "Reload the exact roadmap draft before approving it.",
                ),
            )
        except (
            CustomerRoadmapApprovalCorrupt,
            CustomerRoadmapCorrupt,
            CustomerPrdApprovalCorrupt,
            CustomerPrdCorrupt,
            RequirementsApprovalCorrupt,
            RequirementsDraftCorrupt,
        ):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message("Roadmap approval unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested roadmap approval page does not exist."),
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
                expected_roadmap_digest=fields["expected_roadmap_digest"],
                confirmed=fields["confirmation"] == "LOCK",
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message(
                    "Roadmap not approved",
                    "Review the exact roadmap and select the confirmation checkbox.",
                ),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/roadmap/approved",
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
        raise ValueError("Invalid customer roadmap approval request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid customer roadmap approval body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=6,
    )
    if set(fields) != _FIELDS or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected customer roadmap approval fields")
    return {name: values[0] for name, values in fields.items()}


def _milestone(
    value: CustomerRoadmapMilestone | LockedCustomerRoadmapMilestone,
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


def _roadmap_scope(
    prd: CustomerPrdDraft,
    milestones: tuple[CustomerRoadmapMilestone, ...]
    | tuple[LockedCustomerRoadmapMilestone, ...],
) -> str:
    requirements = {item.requirement_id: item for item in prd.requirements}
    cards = "".join(_milestone(item, requirements) for item in milestones)
    mapped = sum(len(item.requirement_ids) for item in milestones)
    return f'''<div class="signals"><span><strong>Milestones</strong>{len(milestones)}</span>
<span><strong>Mapped requirements</strong>{mapped}</span><span><strong>PRD version</strong>{escape(prd.version)}</span></div>
<h2 class="section-title">Traceable milestones</h2><div class="prd-list">{cards}</div>'''


def _approval_form(
    prd: CustomerPrdDraft,
    roadmap: CustomerRoadmapDraft,
    csrf: str,
) -> str:
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(roadmap.request_id)}/roadmap/review">← Review roadmap draft</a>
<div class="review-head"><div><span class="eyebrow">Roadmap approval checkpoint · Version 0.1</span>
<h1>Approve and lock {escape(roadmap.title)}</h1>
<p>Review every milestone, requirement mapping, priority, and ordering before confirming.</p></div>
<span class="status">Action required</span></div>{_roadmap_scope(prd, roadmap.milestones)}
<div class="notice"><strong>This action permanently locks this exact roadmap</strong>
<p>The locked roadmap becomes an immutable planning scope only. This action does not estimate or schedule work, assign staff or agents, grant repository access, create code or tasks, merge, deploy, bill, release, or select an official pilot product.</p></div>
<form method="post" action="/customer/requests/{escape(roadmap.request_id)}/roadmap/approve">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_roadmap_digest" value="{escape(roadmap.digest)}">
<label class="confirm"><input type="checkbox" name="confirmation" value="LOCK" required>
<span>I reviewed this exact roadmap and approve it as the immutable planning scope.</span></label>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(roadmap.request_id)}/roadmap/review">Review again</a>
<button type="submit">Approve and lock roadmap</button></div></form>
<footer>Roadmap <code>{escape(roadmap.roadmap_id)}</code><br>
Artifact <code>{escape(roadmap.digest)}</code> · Locked PRD <code>{escape(roadmap.prd_digest)}</code></footer></section>'''
    return _layout(f"Approve {roadmap.title} · ASCOS", content, csrf)


def _approved_receipt(
    prd: CustomerPrdDraft,
    roadmap: CustomerRoadmapDraft,
    receipt: CustomerRoadmapApproval,
    locked: LockedCustomerRoadmap,
    csrf: str,
) -> str:
    timestamp = receipt.approved_at.strftime("%d %b %Y, %H:%M UTC")
    content = f'''<section class="review"><a class="back" href="/customer">← Customer workspace</a>
<div class="review-head"><div><span class="eyebrow">Customer roadmap 0.1 · Immutable baseline</span>
<h1>{escape(locked.title)}</h1><p>The exact customer-reviewed roadmap is approved and locked.</p></div>
<span class="status approved">Approved and locked</span></div>{_roadmap_scope(prd, locked.milestones)}
<div class="receipt"><dl><dt>Governed status</dt><dd>{escape(locked.status)}</dd>
<dt>Approved</dt><dd>{escape(timestamp)}</dd><dt>Receipt</dt><dd><code>{escape(receipt.approval_id)}</code></dd>
<dt>Roadmap digest</dt><dd><code>{escape(receipt.roadmap_digest)}</code></dd>
<dt>Receipt digest</dt><dd><code>{escape(receipt.digest)}</code></dd></dl></div>
<div class="notice"><strong>Locked planning scope — implementation has not started</strong>
<p>No estimate, date, schedule, staffing, agent assignment, repository access, task creation, coding, merge, deployment, billing, release, or official pilot-product selection has been authorized.</p></div>
<div class="actions"><a class="button" href="/customer/requests/{escape(roadmap.request_id)}/estimate">Create delivery estimate draft</a>
<a class="button secondary" href="/customer/requests/{escape(roadmap.request_id)}/prd/approved">View locked PRD</a>
<a class="button secondary" href="/customer">Return to workspace</a></div></section>'''
    return _layout(f"Approved roadmap for {locked.title} · ASCOS", content, csrf)
