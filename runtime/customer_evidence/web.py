"""Authenticated Preview and Evidence Centre with explicit customer review."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_evidence.errors import CustomerEvidenceConflict, CustomerEvidenceCorrupt
from runtime.customer_evidence.models import (
    CustomerPreviewEvidencePackage,
    CustomerPreviewReview,
)
from runtime.customer_evidence.service import CustomerPreviewEvidenceService
from runtime.customer_estimate import (
    CustomerDeliveryEstimateConflict,
    CustomerDeliveryEstimateCorrupt,
)
from runtime.customer_prd import (
    CustomerPrdApprovalConflict,
    CustomerPrdApprovalCorrupt,
    CustomerPrdConflict,
    CustomerPrdCorrupt,
)
from runtime.customer_progress import (
    CustomerProjectProgressConflict,
    CustomerProjectProgressCorrupt,
    CustomerProjectProgressSnapshot,
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
from runtime.runtime_acceptance import EvidenceArtifact


_ID = r"([A-Za-z0-9][A-Za-z0-9_.-]{0,127})"
_CENTRE = re.compile(rf"^/customer/requests/{_ID}/evidence$")
_OPEN = re.compile(rf"^/customer/requests/{_ID}/evidence/preview$")
_REVIEW = re.compile(rf"^/customer/requests/{_ID}/evidence/review$")
_FIELDS = {
    "csrf_token",
    "expected_package_digest",
    "decision",
    "comments",
    "confirmation",
}
_MAX_BODY = 8_192


class CustomerPreviewEvidenceApplication:
    """Expose only governed read and explicit customer-decision routes."""

    def __init__(self, service: CustomerPreviewEvidenceService) -> None:
        self._service = service

    @staticmethod
    def handles(path: str) -> bool:
        return any(pattern.fullmatch(path) is not None for pattern in (_CENTRE, _OPEN, _REVIEW))

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
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        centre = _CENTRE.fullmatch(path)
        preview = _OPEN.fullmatch(path)
        review = _REVIEW.fullmatch(path)
        try:
            if centre and method == "GET":
                snapshot, package, receipt = self._service.context(
                    customer_id,
                    centre.group(1),
                )
                return _respond(
                    start_response,
                    "200 OK",
                    _centre(snapshot, package, receipt, csrf),
                )
            if preview and method == "GET":
                _, package, _ = self._service.context(customer_id, preview.group(1))
                if package is None:
                    return _redirect(
                        start_response,
                        f"/customer/requests/{preview.group(1)}/evidence",
                    )
                return _redirect(start_response, package.preview_url)
            if review and method == "POST":
                return self._review(
                    environ,
                    start_response,
                    customer_id,
                    review.group(1),
                    csrf,
                )
            if centre or preview or review:
                allow = "GET" if centre or preview else "POST"
                return _respond(
                    start_response,
                    "405 Method Not Allowed",
                    _message("Method not allowed", "Use the governed review controls."),
                    extra_headers=[("Allow", allow)],
                )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except (
            CustomerEvidenceConflict,
            CustomerProjectProgressConflict,
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
                    "Preview review changed",
                    "Reload the exact preview and evidence before deciding.",
                ),
            )
        except (
            CustomerEvidenceCorrupt,
            CustomerProjectProgressCorrupt,
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
                _message("Preview evidence unavailable", "Please try again later."),
            )
        return _respond(
            start_response,
            "404 Not Found",
            _message("Page not found", "The requested evidence page does not exist."),
        )

    def _review(
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
            value = self._service.review(
                customer_id=customer_id,
                request_id=request_id,
                expected_package_digest=fields["expected_package_digest"],
                decision=fields["decision"],
                comments=fields["comments"],
                confirmed=fields["confirmation"] == "REVIEWED",
            )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message(
                    "Decision not recorded",
                    "Choose ACCEPT or REVISE, confirm the exact evidence, and explain revisions.",
                ),
            )
        return _redirect(
            start_response,
            f"/customer/requests/{value.request_id}/evidence",
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
        raise ValueError("Invalid customer preview review request")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid customer preview review body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=6,
    )
    if set(fields) != _FIELDS or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected customer preview review fields")
    return {name: values[0] for name, values in fields.items()}


def _centre(
    snapshot: CustomerProjectProgressSnapshot,
    package: CustomerPreviewEvidencePackage | None,
    review: CustomerPreviewReview | None,
    csrf: str,
) -> str:
    if package is None:
        content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(snapshot.request_id)}/progress">← Project progress</a>
<div class="review-head"><div><span class="eyebrow">Preview and Evidence Centre · Day 21</span>
<h1>Preview evidence is pending</h1><p>No governed preview package is available for this project yet.</p></div>
<span class="status">Awaiting evidence</span></div>
<article class="journey"><h2>What happens here</h2><p>When a separately authorized preview exists, this centre binds its exact commit, browser results, test evidence, screenshot, and security result for customer review.</p></article>
<div class="notice"><strong>No preview creation or deployment authority</strong><p>Day 21 records and reviews existing evidence only. It does not create a workspace, run agents, write code, deploy, merge, release, bill, or select a pilot product.</p></div>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(snapshot.request_id)}/progress">Return to progress</a></div></section>'''
        return _layout("Preview evidence pending · ASCOS", content, csrf)

    evidence_cards = "".join(_evidence(item) for item in package.evidence)
    passed = sum(item.outcome.value == "PASS" for item in package.evidence)
    if review is None:
        decision = _decision_form(snapshot.request_id, package, csrf)
        status = "Customer review required"
    else:
        decision = _receipt(review)
        status = "Accepted" if review.decision == "ACCEPT" else "Revision requested"
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(snapshot.request_id)}/progress">← Project progress</a>
<div class="review-head"><div><span class="eyebrow">Preview and Evidence Centre · Day 21</span>
<h1>{escape(package.preview_label)}</h1><p>Open the exact preview and inspect every governed result before deciding.</p></div>
<span class="status {'approved' if review and review.decision == 'ACCEPT' else ''}">{escape(status)}</span></div>
<div class="signals"><span><strong>Exact commit</strong>{escape(package.commit_sha[:12])}…</span>
<span><strong>Evidence passed</strong>{passed}/{len(package.evidence)}</span>
<span><strong>Project progress</strong>{snapshot.progress_percentage}%</span></div>
<article class="journey"><h2>Product preview</h2><p>This link opens only the exact allow-listed preview recorded in package <code>{escape(package.package_id)}</code>.</p>
<div class="actions"><a class="button" target="_blank" rel="noopener noreferrer" href="/customer/requests/{escape(snapshot.request_id)}/evidence/preview">Open product preview</a></div></article>
<h2 class="section-title">Test and security evidence</h2><div class="grid">{evidence_cards}</div>
<div class="receipt"><dl><dt>Preview commit</dt><dd><code>{escape(package.commit_sha)}</code></dd>
<dt>Project projection</dt><dd><code>{escape(package.progress_digest)}</code></dd>
<dt>Evidence package</dt><dd><code>{escape(package.digest)}</code></dd></dl></div>
{decision}
<div class="notice"><strong>Customer decision only — no delivery side effect</strong>
<p>ACCEPT or REVISE records review of this exact preview evidence. It does not assign an agent, create a task, write a repository, merge, deploy, bill, release, select a pilot product, or start Day 22.</p></div>
<div class="actions"><a class="button secondary" href="/customer/requests/{escape(snapshot.request_id)}/progress">Return to progress</a>
<a class="button secondary" href="/customer">Return to workspace</a></div></section>'''
    return _layout(f"Preview evidence for {package.preview_label} · ASCOS", content, csrf)


def _evidence(value: EvidenceArtifact) -> str:
    label = value.kind.value.replace("_EVIDENCE", "").replace("_", " ").title()
    return f'''<article><div class="prd-meta"><span>{escape(value.outcome.value)}</span><span>{escape(label)}</span></div>
<h2>{escape(value.summary)}</h2><p>Journey <code>{escape(value.journey_id)}</code></p>
<div class="trace">Evidence <code>{escape(value.evidence_id)}</code><br>Artifact reference <code>{escape(value.artifact_uri)}</code><br>Digest <code>{escape(value.digest)}</code></div></article>'''


def _decision_form(
    request_id: str,
    package: CustomerPreviewEvidencePackage,
    csrf: str,
) -> str:
    accept_disabled = "" if package.all_required_evidence_passed else " disabled"
    return f'''<h2 class="section-title">Customer decision</h2>
<form method="post" action="/customer/requests/{escape(request_id)}/evidence/review">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="expected_package_digest" value="{escape(package.digest)}">
<fieldset><legend>Choose one decision</legend><div class="checks">
<label class="check"><input type="radio" name="decision" value="ACCEPT" required{accept_disabled}> ACCEPT</label>
<label class="check"><input type="radio" name="decision" value="REVISE" required> REVISE</label></div></fieldset>
<label>Review comments <span>required for REVISE</span><textarea name="comments" maxlength="2000" rows="4"></textarea></label>
<label class="check"><input type="checkbox" name="confirmation" value="REVIEWED" required> I opened the preview and reviewed this exact evidence package.</label>
<div class="actions"><button type="submit">Submit customer decision</button></div></form>'''


def _receipt(value: CustomerPreviewReview) -> str:
    timestamp = value.reviewed_at.strftime("%d %b %Y, %H:%M UTC")
    comments = escape(value.comments) if value.comments else "No additional comments"
    return f'''<h2 class="section-title">Immutable customer decision</h2><div class="receipt"><dl>
<dt>Decision</dt><dd>{escape(value.decision)}</dd><dt>Reviewed</dt><dd>{escape(timestamp)}</dd>
<dt>Comments</dt><dd>{comments}</dd><dt>Review receipt</dt><dd><code>{escape(value.review_id)}</code></dd>
<dt>Receipt digest</dt><dd><code>{escape(value.digest)}</code></dd></dl></div>'''
