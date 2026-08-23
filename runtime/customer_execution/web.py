"""Authenticated customer dashboard for governed planning and one coding turn."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from html import escape
import hmac
import re
from urllib.parse import parse_qs

from runtime.coding_providers import CodingProviderError
from runtime.customer_application.errors import ProductRequestNotFound
from runtime.customer_estimate import CustomerDeliveryEstimateError
from runtime.customer_execution.errors import (
    CustomerExecutionConflict,
    CustomerExecutionCorrupt,
    CustomerExecutionNotConfigured,
    CustomerExecutionPolicyError,
    CustomerExecutionReconciliationRequired,
)
from runtime.customer_execution.models import (
    CustomerExecutionPlan,
    CustomerExecutionPlanStatus,
    CustomerExecutionTask,
    CustomerExecutionTaskStatus,
)
from runtime.customer_execution.service import CustomerExecutionService
from runtime.customer_prd import CustomerPrdError
from runtime.customer_progress import CustomerProjectProgressError
from runtime.customer_requirements import CustomerRequirementsError
from runtime.customer_requirements.web import _csrf, _layout, _message, _redirect, _respond
from runtime.customer_roadmap import CustomerRoadmapError


_BASE = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/execution$"
)
_ACTION = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/execution/(plan|approve|execute)$"
)
_MAX_BODY = 4_096


class CustomerExecutionApplication:
    """Expose only customer-scoped, CSRF-protected execution transitions."""

    def __init__(
        self,
        service: CustomerExecutionService,
        *,
        delivery_available: bool = False,
    ) -> None:
        self._service = service
        self._delivery_available = delivery_available

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
                plan = self._service.find(customer_id, request_id)
                return _respond(
                    start_response,
                    "200 OK",
                    _dashboard(
                        request_id,
                        plan,
                        csrf,
                        configured=self._service.configured,
                        live_enabled=self._service.live_enabled,
                        delivery_available=self._delivery_available,
                    ),
                )
            if action is not None and method == "POST":
                fields = _fields(environ, action.group(2))
                if not hmac.compare_digest(fields["csrf_token"][0], csrf):
                    raise ValueError("CSRF mismatch")
                if action.group(2) == "plan":
                    self._service.plan(customer_id, request_id)
                elif action.group(2) == "approve":
                    if fields["confirm_plan"] != ["yes"]:
                        raise ValueError("Plan approval missing")
                    self._service.approve(
                        customer_id,
                        request_id,
                        expected_scope_digest=fields["scope_digest"][0],
                    )
                else:
                    self._service.execute_next(
                        customer_id,
                        request_id,
                        expected_scope_digest=fields["scope_digest"][0],
                        confirm_scope=fields["confirm_scope"] == ["yes"],
                        confirm_usage_consumption=fields["confirm_usage"] == ["yes"],
                    )
                return _redirect(
                    start_response, f"/customer/requests/{request_id}/execution"
                )
        except (UnicodeDecodeError, ValueError):
            return _respond(
                start_response,
                "400 Bad Request",
                _message("Execution request rejected", "Reload the exact plan and try again."),
            )
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except CustomerExecutionNotConfigured:
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Execution is not enabled",
                    "An operator must bind a trusted product workspace before planning or coding.",
                ),
            )
        except (CustomerExecutionConflict, CustomerExecutionPolicyError):
            return _respond(
                start_response,
                "409 Conflict",
                _message(
                    "Execution authority changed",
                    "No coding turn was authorized. Reload and review the current governed state.",
                ),
            )
        except CustomerExecutionReconciliationRequired:
            return _respond(
                start_response,
                "502 Bad Gateway",
                _message(
                    "Execution requires reconciliation",
                    "ASCOS persisted the live intent and stopped without retrying. Review durable provider and workspace state before continuing.",
                ),
            )
        except (
            CustomerExecutionCorrupt,
            CustomerProjectProgressError,
            CustomerDeliveryEstimateError,
            CustomerPrdError,
            CustomerRequirementsError,
            CustomerRoadmapError,
        ):
            return _respond(
                start_response,
                "503 Service Unavailable",
                _message(
                    "Execution authority unavailable",
                    "ASCOS stopped because the governed planning chain could not be verified.",
                ),
            )
        except CodingProviderError:
            return _respond(
                start_response,
                "502 Bad Gateway",
                _message(
                    "Codex turn requires reconciliation",
                    "ASCOS stopped without retrying. Review durable provider state before continuing.",
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
            _message("Page not found", "The execution page does not exist."),
        )


def _fields(environ: dict[str, object], action: str) -> dict[str, list[str]]:
    expected = {
        "plan": {"csrf_token"},
        "approve": {"csrf_token", "scope_digest", "confirm_plan"},
        "execute": {"csrf_token", "scope_digest", "confirm_scope", "confirm_usage"},
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
        raise ValueError("Invalid execution form")
    content = stream.read(length)
    if not isinstance(content, bytes) or len(content) != length:
        raise ValueError("Invalid execution form body")
    fields = parse_qs(
        content.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=True,
        max_num_fields=8,
    )
    if set(fields) != expected or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Unexpected execution fields")
    return fields


def _dashboard(
    request_id: str,
    plan: CustomerExecutionPlan | None,
    csrf: str,
    *,
    configured: bool,
    live_enabled: bool,
    delivery_available: bool = False,
) -> str:
    if plan is None:
        action = (
            f'''<form method="post" action="/customer/requests/{escape(request_id)}/execution/plan">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<button type="submit">Create governed execution plan</button></form>'''
            if configured
            else ""
        )
        notice = (
            "The operator-bound workspace is ready. Creating a plan does not call Codex or consume usage."
            if configured
            else "Start the launcher with a trusted product workspace, allow-list, and candidate files. Repository paths and credentials are never accepted from this browser page."
        )
        content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(request_id)}/progress">← Project progress</a>
<div class="review-head"><div><span class="eyebrow">Completion Module 3 · Execution centre</span>
<h1>Governed product execution</h1><p>Convert the exact locked customer roadmap into bounded coding tasks.</p></div>
<span class="status">{'Ready to plan' if configured else 'Operator setup required'}</span></div>
<div class="notice"><strong>No coding authority yet</strong><p>{escape(notice)}</p></div>
<div class="actions">{action}<a class="button secondary" href="/customer/requests/{escape(request_id)}/progress">Return to progress</a></div>
<div class="notice"><strong>Hard boundary</strong><p>This module cannot commit, push, open a pull request, merge, deploy, release, or start a pilot product.</p></div></section>'''
        return _layout("Governed execution · ASCOS", content, csrf)

    tasks = "".join(_task(value) for value in plan.tasks)
    action = _action(plan, csrf, live_enabled, delivery_available)
    receipt = _receipt(plan)
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(request_id)}/progress">← Project progress</a>
<div class="review-head"><div><span class="eyebrow">Completion Module 3 · Execution centre</span>
<h1>Governed product execution</h1><p>One exact plan, one explicit usage gate, and one coding turn before review.</p></div>
<span class="status">{escape(plan.status.value.replace('_', ' ').title())}</span></div>
<div class="signals"><span><strong>Provider</strong>Codex SDK</span>
<span><strong>Model</strong>{escape(plan.model)}</span>
<span><strong>Authentication</strong>{escape(plan.authentication_mode)}</span>
<span><strong>Billing</strong>{escape(_billing(plan.billing_source))}</span></div>
<article class="journey"><h2>Approved workspace identity</h2>
<p><strong>Branch</strong> <code>{escape(plan.workspace_branch)}</code><br>
<strong>Commit before turn</strong> <code>{escape(plan.workspace_commit)}</code></p>
<p>The local repository path remains operator-owned and is not exposed to the browser.</p></article>
<h2 class="section-title">Bounded coding tasks</h2><div class="prd-list">{tasks}</div>
{receipt}{action}
<div class="receipt"><dl><dt>Plan</dt><dd><code>{escape(plan.plan_id)}</code></dd>
<dt>Locked plan digest</dt><dd><code>{escape(plan.scope_digest)}</code></dd>
<dt>Roadmap authority</dt><dd><code>{escape(plan.roadmap_approval_digest)}</code></dd></dl></div>
<div class="notice"><strong>Stops at human review</strong><p>No dashboard action in this module can commit, push, create a PR, merge, deploy, release, or select FamilyVault.</p></div></section>'''
    return _layout("Governed execution · ASCOS", content, csrf)


def _task(value: CustomerExecutionTask) -> str:
    criteria = "".join(f"<li>{escape(item)}</li>" for item in value.acceptance_criteria)
    paths = ", ".join(value.allowed_paths)
    candidates = ", ".join(value.candidate_files)
    result = ""
    if value.status is CustomerExecutionTaskStatus.REVIEW_REQUIRED:
        changed = ", ".join(value.changed_paths) or "No changed files"
        result = f'''<p><strong>Codex result:</strong> {escape(value.result_summary or 'Result received')}</p>
<p><strong>Changed paths:</strong> {escape(changed)} · {value.additions} additions · {value.deletions} deletions</p>'''
    return f'''<article class="prd-requirement"><div class="prd-meta"><span>{escape(value.requirement_id)}</span>
<span>{escape(value.status.value.replace('_', ' ').title())}</span></div><h2>{escape(value.title)}</h2>
<p>{escape(value.objective)}</p><h3>Acceptance criteria</h3><ul>{criteria}</ul>
<div class="trace">Allowed product paths: <code>{escape(paths)}</code><br>
Candidate context files: <code>{escape(candidates)}</code></div>{result}</article>'''


def _action(
    plan: CustomerExecutionPlan,
    csrf: str,
    live_enabled: bool,
    delivery_available: bool = False,
) -> str:
    target = f"/customer/requests/{escape(plan.request_id)}/execution"
    if plan.status is CustomerExecutionPlanStatus.AWAITING_APPROVAL:
        return f'''<form method="post" action="{target}/approve">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="scope_digest" value="{escape(plan.scope_digest)}">
<label class="check"><input type="checkbox" name="confirm_plan" value="yes" required>
<span>I reviewed this exact task plan, branch, commit, path allow-list, model, authentication mode, and billing source.</span></label>
<div class="actions"><button type="submit">Approve exact execution plan</button></div></form>'''
    if plan.status is CustomerExecutionPlanStatus.APPROVED:
        if not live_enabled:
            return '''<div class="notice"><strong>Live turn disabled by operator</strong>
<p>The plan is approved, but the launcher was not started with both live-execution flags.</p></div>'''
        return f'''<form method="post" action="{target}/execute">
<input type="hidden" name="csrf_token" value="{escape(csrf)}">
<input type="hidden" name="scope_digest" value="{escape(plan.scope_digest)}">
<label class="check"><input type="checkbox" name="confirm_scope" value="yes" required>
<span>Run only the first pending task against this exact clean branch and commit.</span></label>
<label class="check"><input type="checkbox" name="confirm_usage" value="yes" required>
<span>I authorize one chargeable Codex turn billed to {escape(_billing(plan.billing_source))}.</span></label>
<div class="actions"><button type="submit">Start one governed Codex coding turn</button></div></form>'''
    if plan.status is CustomerExecutionPlanStatus.REVIEW_REQUIRED:
        next_action = (
            f'''<div class="actions"><a class="button" href="/customer/requests/{escape(plan.request_id)}/delivery">Review exact patch</a></div>'''
            if delivery_available
            else ""
        )
        return f'''<div class="notice"><strong>Human review required</strong>
<p>ASCOS applied the validated text patch locally and stopped. No repository effect occurs until a separately configured Module 4 review.</p></div>{next_action}'''
    if plan.status is CustomerExecutionPlanStatus.RECONCILIATION_REQUIRED:
        return '''<div class="notice"><strong>Manual reconciliation required</strong>
<p>ASCOS will not retry automatically because the provider or patch effect may already exist.</p></div>'''
    return '''<div class="notice"><strong>Coding turn in progress</strong>
<p>Do not resubmit or change the product workspace.</p></div>'''


def _receipt(plan: CustomerExecutionPlan) -> str:
    completed = next(
        (value for value in plan.tasks if value.status is CustomerExecutionTaskStatus.REVIEW_REQUIRED),
        None,
    )
    if completed is None:
        return ""
    if completed.input_units is None or completed.output_units is None:
        usage = "Usage units not reported"
    else:
        total = completed.input_units + completed.output_units
        usage = (
            f"{completed.input_units} input + {completed.output_units} output = {total} units"
        )
    return f'''<article class="journey"><h2>Durable Codex receipt</h2>
<p><strong>Provider task</strong> <code>{escape(completed.provider_task_id or '')}</code><br>
<strong>Usage</strong> {escape(usage)} across {completed.request_count or 0} request<br>
<strong>Authentication</strong> {escape(plan.authentication_mode)} · <strong>Billing</strong> {escape(_billing(plan.billing_source))}<br>
<strong>Patch manifest</strong> <code>{escape(completed.manifest_digest or '')}</code></p></article>'''


def _billing(value: str) -> str:
    return "ChatGPT plan" if value == "chatgpt-plan" else "OpenAI Platform API account"
