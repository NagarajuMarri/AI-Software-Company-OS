"""Authenticated dashboard for exact patch review and draft-PR delivery."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_delivery.errors import (
    CustomerDeliveryConflict,
    CustomerDeliveryCorrupt,
    CustomerDeliveryNotConfigured,
    CustomerDeliveryNotFound,
    CustomerDeliveryPolicyError,
    CustomerDeliveryReconciliationRequired,
)
from runtime.customer_delivery.models import CustomerDeliveryReview, CustomerDeliveryStatus
from runtime.customer_delivery.service import CustomerDeliveryService
from runtime.customer_execution import CustomerExecutionConflict, CustomerExecutionCorrupt
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond


_BASE = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/delivery$"
)
_ACTION = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/delivery/(prepare|approve|deliver)$"
)
_MAX_BODY = 4_096


class CustomerDeliveryApplication:
    """Expose only customer-scoped, CSRF-protected delivery transitions."""

    def __init__(self, service: CustomerDeliveryService) -> None:
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
                review, diff = self._service.view(customer_id, request_id)
                return _respond(
                    start_response,
                    "200 OK",
                    _dashboard(
                        request_id,
                        review,
                        diff,
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
                        expected_review_digest=fields["review_digest"][0],
                        confirm_review=fields["confirm_review"] == ["yes"],
                    )
                else:
                    self._service.deliver(
                        customer_id,
                        request_id,
                        expected_review_digest=fields["review_digest"][0],
                        confirm_repository_write=fields["confirm_delivery"] == ["yes"],
                    )
                return _redirect(start_response, f"/customer/requests/{request_id}/delivery")
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message("Delivery request rejected", "Reload the exact review and try again."),
            )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except CustomerDeliveryNotConfigured:
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Delivery is not enabled",
                    "An operator must bind the repository and separately confirm product writes.",
                ),
            )
        except (
            CustomerDeliveryConflict,
            CustomerDeliveryNotFound,
            CustomerDeliveryPolicyError,
            CustomerExecutionConflict,
        ):
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Delivery authority changed",
                    "No repository effect was authorized. Reload and review the governed state.",
                ),
            )
        except CustomerDeliveryReconciliationRequired:
            return _respond(
                start_response,
                "502 Bad Gateway",
                _message(
                    "Delivery requires reconciliation",
                    "ASCOS stopped without retrying. Inspect the commit, remote branch, and draft PR before continuing.",
                ),
            )
        except (CustomerDeliveryCorrupt, CustomerExecutionCorrupt):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message(
                    "Delivery evidence unavailable",
                    "ASCOS stopped because exact review evidence could not be verified.",
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
            _message("Page not found", "The delivery page does not exist."),
        )


def _fields(environ: dict[str, object], action: str) -> dict[str, list[str]]:
    expected = {
        "prepare": {"csrf_token"},
        "approve": {"csrf_token", "review_digest", "confirm_review"},
        "deliver": {"csrf_token", "review_digest", "confirm_delivery"},
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
        raise ValueError("Invalid delivery form")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid delivery form body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=6,
    )
    if set(fields) != expected or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected delivery fields")
    return fields


def _dashboard(
    request_id: str,
    review: CustomerDeliveryReview | None,
    diff: str,
    csrf: str,
    *,
    configured: bool,
    live_enabled: bool,
) -> str:
    if review is None:
        action = (
            f'''<form method="post" action="/customer/requests/{escape(request_id)}/delivery/prepare">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<button type="submit">Prepare exact patch review</button></form>'''
            if configured
            else ""
        )
        notice = (
            "The operator-bound repository target is ready. Preparing review performs no Git or GitHub write."
            if configured
            else "Restart the launcher with a trusted repository identity and integration branch. Credentials and repository paths are never browser inputs."
        )
        content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(request_id)}/execution">← Governed execution</a>
<div class="review-head"><div><span class="eyebrow">Completion Module 4 · Review and delivery</span>
<h1>Review the exact product patch</h1><p>Verify Codex output before any commit, push, or draft pull request.</p></div>
<span class="status">{'Ready to review' if configured else 'Operator setup required'}</span></div>
<div class="notice"><strong>No repository authority yet</strong><p>{escape(notice)}</p></div>
<div class="actions">{action}<a class="button secondary" href="/customer/requests/{escape(request_id)}/execution">Return to execution</a></div>
<div class="notice"><strong>Hard boundary</strong><p>This module can create only one reviewed commit, one non-force feature-branch push, and one open draft PR. It cannot approve or merge, deploy, release, or start FamilyVault.</p></div></section>'''
        return _layout("Patch review · ASCOS", content, csrf)

    files = "".join(
        f"<li><code>{escape(item.path)}</code><br><small>{escape(item.content_digest)}</small></li>"
        for item in review.reviewed_files
    )
    patch = (
        f'<article class="journey"><h2>Exact escaped Git patch</h2><pre>{escape(diff)}</pre></article>'
        if diff
        else ""
    )
    receipt = _receipt(review)
    action = _action(review, csrf, live_enabled)
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(request_id)}/execution">← Governed execution</a>
<div class="review-head"><div><span class="eyebrow">Completion Module 4 · Review and delivery</span>
<h1>Governed patch delivery</h1><p>Human-reviewed evidence before a single controlled draft-PR effect.</p></div>
<span class="status">{escape(review.status.value.replace('_', ' ').title())}</span></div>
<div class="signals"><span><strong>Repository</strong>{escape(review.repository_full_name)}</span>
<span><strong>Base</strong>{escape(review.base_branch)}</span>
<span><strong>Head</strong>{escape(review.workspace_branch)}</span>
<span><strong>Changes</strong>{review.additions} additions · {review.deletions} deletions</span></div>
<article class="journey"><h2>Content-addressed reviewed files</h2><ul>{files}</ul>
<p><strong>Patch manifest</strong> <code>{escape(review.patch_manifest_digest)}</code><br>
<strong>Git diff</strong> <code>{escape(review.git_diff_digest)}</code></p></article>
{patch}{receipt}{action}
<div class="receipt"><dl><dt>Review</dt><dd><code>{escape(review.delivery_id)}</code></dd>
<dt>Locked review digest</dt><dd><code>{escape(review.review_digest)}</code></dd>
<dt>Execution plan</dt><dd><code>{escape(review.execution_plan_id)}</code></dd></dl></div>
<div class="notice"><strong>Stops at an open draft PR</strong><p>No action can approve or merge the PR, deploy preview or production, release, or select FamilyVault.</p></div></section>'''
    return _layout("Governed delivery · ASCOS", content, csrf)


def _action(review: CustomerDeliveryReview, csrf: str, live_enabled: bool) -> str:
    target = f"/customer/requests/{escape(review.request_id)}/delivery"
    if review.status is CustomerDeliveryStatus.AWAITING_REVIEW:
        return f'''<form method="post" action="{target}/approve">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="review_digest" value="{escape(review.review_digest)}">
<label class="check"><input type="checkbox" name="confirm_review" value="yes" required>
<span>I reviewed the exact escaped patch, content digests, branch, commit, repository, and draft-PR target.</span></label>
<div class="actions"><button type="submit">Approve exact patch for draft delivery</button></div></form>'''
    if review.status is CustomerDeliveryStatus.REVIEW_APPROVED:
        if not live_enabled:
            return '''<div class="notice"><strong>Repository writes disabled by operator</strong>
<p>The patch is approved, but the launcher lacks both delivery enablement flags.</p></div>'''
        return f'''<form method="post" action="{target}/deliver">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="review_digest" value="{escape(review.review_digest)}">
<label class="check"><input type="checkbox" name="confirm_delivery" value="yes" required>
<span>Create one exact commit, push only this agent/* branch without force, and open one draft PR. This does not merge or deploy.</span></label>
<div class="actions"><button type="submit">Create reviewed draft delivery</button></div></form>'''
    if review.status is CustomerDeliveryStatus.DRAFT_PR_CREATED:
        return '''<div class="notice"><strong>Draft review required on GitHub</strong>
<p>ASCOS completed its bounded repository effect and stopped. Merge and deployment remain unavailable.</p></div>'''
    if review.status is CustomerDeliveryStatus.RECONCILIATION_REQUIRED:
        return '''<div class="notice"><strong>Manual reconciliation required</strong>
<p>ASCOS will not retry because a commit, remote branch, or draft PR may already exist.</p></div>'''
    return '''<div class="notice"><strong>Delivery in progress</strong>
<p>Do not resubmit or modify the product repository.</p></div>'''


def _receipt(review: CustomerDeliveryReview) -> str:
    if review.status is not CustomerDeliveryStatus.DRAFT_PR_CREATED:
        return ""
    return f'''<article class="journey"><h2>Durable draft-delivery receipt</h2>
<p><strong>Commit</strong> <code>{escape(review.commit_sha or '')}</code><br>
<strong>Tree</strong> <code>{escape(review.tree_sha or '')}</code><br>
<strong>Draft PR</strong> <a href="{escape(review.pull_request_url or '')}">#{review.pull_request_number or 0}</a><br>
<strong>State</strong> Open draft · unmerged · undeployed</p></article>'''
