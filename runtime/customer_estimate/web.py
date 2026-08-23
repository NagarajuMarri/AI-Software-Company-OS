"""WSGI generation checkpoint and review page for customer estimate drafts."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_estimate.errors import (
    CustomerDeliveryEstimateConflict,
    CustomerDeliveryEstimateCorrupt,
)
from runtime.customer_estimate.models import (
    CustomerDeliveryEstimateDraft,
    CustomerMilestoneEstimate,
)
from runtime.customer_estimate.service import CustomerDeliveryEstimateService
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
from runtime.customer_roadmap import (
    CustomerRoadmapApprovalConflict,
    CustomerRoadmapApprovalCorrupt,
    CustomerRoadmapConflict,
    CustomerRoadmapCorrupt,
)


_GENERATE = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/estimate$"
)
_REVIEW = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/estimate/review$"
)
_FIELDS = {"csrf_token", "expected_roadmap_approval_digest"}
_MAX_BODY = 8_192


class CustomerDeliveryEstimateApplication:
    """Generate a reviewable effort estimate without execution authority."""

    def __init__(self, service: CustomerDeliveryEstimateService) -> None:
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
                _, prd, roadmap, approval, estimate = self._service.context(
                    customer_id,
                    request_id,
                )
                if estimate is not None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{request_id}/estimate/review",
                    )
                if prd is None or roadmap is None or approval is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{request_id}/roadmap/approved",
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
                _, prd, _, _, estimate = self._service.context(customer_id, request_id)
                if prd is None or estimate is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{request_id}/estimate",
                    )
                return _respond(
                    start_response,
                    "200 OK",
                    _estimate_review(prd, estimate, csrf),
                )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except (
            CustomerDeliveryEstimateConflict,
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
                    "Estimate source changed",
                    "Reload the exact locked roadmap before creating its estimate.",
                ),
            )
        except (
            CustomerDeliveryEstimateCorrupt,
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
                _message("Estimate unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested estimate page does not exist."),
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
                expected_roadmap_approval_digest=fields[
                    "expected_roadmap_approval_digest"
                ],
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message("Estimate not created", "Reload the exact estimate checkpoint."),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/estimate/review",
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
        raise ValueError("Invalid customer estimate request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid customer estimate body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=4,
    )
    if set(fields) != _FIELDS or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected customer estimate fields")
    return {name: values[0] for name, values in fields.items()}


def _generation_checkpoint(
    prd: CustomerPrdDraft,
    roadmap_approval_digest: str,
    csrf: str,
) -> str:
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(prd.request_id)}/roadmap/approved">← Locked roadmap</a>
<div class="review-head"><div><span class="eyebrow">Delivery estimate checkpoint · Version 0.1</span>
<h1>Create an effort estimate for {escape(prd.title)}</h1>
<p>ASCOS will size the exact locked roadmap with a deterministic, reviewable range.</p></div>
<span class="status">Action required</span></div>
<div class="signals"><span><strong>Locked requirements</strong>{len(prd.requirements)}</span>
<span><strong>Data class</strong>{escape(prd.data_sensitivity.value.replace('_', ' ').title())}</span>
<span><strong>Output</strong>DRAFT</span></div>
<div class="notice"><strong>This creates a non-binding effort estimate only</strong>
<p>Engineering days are relative work units, not calendar duration. This action creates no approval, price, quote, date, schedule, staffing, agent assignment, repository access, implementation task, code, deployment, billing, release, or official pilot-product selection.</p></div>
<form method="post" action="/customer/requests/{escape(prd.request_id)}/estimate">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_roadmap_approval_digest" value="{escape(roadmap_approval_digest)}">
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(prd.request_id)}/roadmap/approved">Review locked roadmap</a>
<button type="submit">Generate estimate draft</button></div></form>
<footer>Locked roadmap approval <code>{escape(roadmap_approval_digest)}</code></footer></section>'''
    return _layout(f"Estimate for {prd.title} · ASCOS", content, csrf)


def _estimate_review(
    prd: CustomerPrdDraft,
    estimate: CustomerDeliveryEstimateDraft,
    csrf: str,
) -> str:
    requirements = {item.requirement_id: item for item in prd.requirements}
    cards = "".join(_estimate_card(item, requirements) for item in estimate.milestones)
    assumptions = "".join(f"<li>{escape(value)}</li>" for value in estimate.assumptions)
    generated = estimate.generated_at.strftime("%d %b %Y, %H:%M UTC")
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(estimate.request_id)}/roadmap/approved">← Locked roadmap</a>
<div class="review-head"><div><span class="eyebrow">Customer delivery estimate · Version 0.1</span>
<h1>{escape(estimate.title)}</h1><p>Every estimate item maps to the exact locked roadmap.</p></div>
<span class="status">Draft generated</span></div>
<div class="signals"><span><strong>Status</strong>{escape(estimate.status)}</span>
<span><strong>Total effort</strong>{estimate.total_minimum_effort_days}–{estimate.total_maximum_effort_days} engineering days</span>
<span><strong>Confidence</strong>{escape(estimate.confidence.value.title())}</span></div>
<h2 class="section-title">Milestone effort ranges</h2><div class="prd-list">{cards}</div>
<h2 class="section-title">Estimate assumptions</h2><article class="journey"><ul>{assumptions}</ul></article>
<div class="receipt"><dl><dt>Generated</dt><dd>{escape(generated)}</dd>
<dt>Estimate</dt><dd><code>{escape(estimate.estimate_id)}</code></dd>
<dt>Locked roadmap digest</dt><dd><code>{escape(estimate.roadmap_digest)}</code></dd>
<dt>Estimate digest</dt><dd><code>{escape(estimate.digest)}</code></dd></dl></div>
<div class="notice"><strong>Draft estimate — no commitment or execution authority</strong>
<p>No approval, price, quote, calendar date, schedule, staffing, agents, repositories, implementation tasks, code, merge, deployment, billing, release, or pilot-product selection has been authorized.</p></div>
<div class="actions"><a class="button" href="/customer/requests/{escape(estimate.request_id)}/progress">View project progress</a>
<a class="button secondary" href="/customer/requests/{escape(estimate.request_id)}/roadmap/approved">View locked roadmap</a>
<a class="button secondary" href="/customer">Return to workspace</a></div></section>'''
    return _layout(f"Draft estimate for {prd.title} · ASCOS", content, csrf)


def _estimate_card(
    value: CustomerMilestoneEstimate,
    requirements: Mapping[str, CustomerPrdRequirement],
) -> str:
    mapped = "".join(
        f"<li><code>{escape(requirement_id)}</code> — {escape(requirements[requirement_id].title)}</li>"
        for requirement_id in value.requirement_ids
    )
    drivers = "".join(f"<li>{escape(driver)}</li>" for driver in value.drivers)
    return f'''<article class="prd-requirement"><div class="prd-meta"><span>Milestone {value.sequence}</span>
<span>{escape(value.effort_band.value.replace('_', ' ').title())}</span>
<span>{escape(value.confidence.value.title())} confidence</span></div>
<h2>{escape(value.milestone)}</h2><p><strong>{value.minimum_effort_days}–{value.maximum_effort_days} engineering days</strong> · {value.complexity_points} complexity points</p>
<h3>Locked requirement mapping</h3><ul>{mapped}</ul><h3>Estimate drivers</h3><ul>{drivers}</ul>
<div class="trace">Governed roadmap item: <code>{escape(value.roadmap_item_id)}</code></div></article>'''
