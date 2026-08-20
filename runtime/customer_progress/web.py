"""Customer-scoped read-only project-progress dashboard."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from html import escape
import re

from runtime.customer_application.errors import ProductRequestNotFound
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
from runtime.customer_progress.errors import (
    CustomerProjectProgressConflict,
    CustomerProjectProgressCorrupt,
)
from runtime.customer_progress.models import (
    CustomerProgressMilestone,
    CustomerProgressTask,
    CustomerProjectProgressSnapshot,
)
from runtime.customer_progress.service import CustomerProjectProgressService
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


_PROGRESS = re.compile(
    r"^/customer/requests/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})/progress$"
)


class CustomerProjectProgressApplication:
    """Display governed progress without exposing a mutation boundary."""

    def __init__(self, service: CustomerProjectProgressService) -> None:
        self._service = service

    @staticmethod
    def handles(path: str) -> bool:
        return _PROGRESS.fullmatch(path) is not None

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
        match = _PROGRESS.fullmatch(str(environ.get("PATH_INFO", "/")))
        request_id = match.group(1) if match is not None else ""
        if method != "GET":
            return _respond(
                start_response,
                "405 Method Not Allowed",
                _message("Read-only dashboard", "Project progress cannot be changed here."),
                extra_headers=[("Allow", "GET")],
            )
        try:
            snapshot = self._service.view(customer_id, request_id)
            return _respond(start_response, "200 OK", _dashboard(snapshot, csrf))
        except ProductRequestNotFound:
            return _respond(
                start_response,
                "404 Not Found",
                _message("Request not found", "This product request is unavailable."),
            )
        except CustomerProjectProgressConflict:
            return _redirect(
                start_response,
                f"/customer/requests/{request_id}/estimate",
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
                    "Progress source changed",
                    "Reload the exact governed customer plan before viewing progress.",
                ),
            )
        except (
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
                _message("Progress unavailable", "Please try again later."),
            )


def _dashboard(snapshot: CustomerProjectProgressSnapshot, csrf: str) -> str:
    tasks = {value.task_id: value for value in snapshot.tasks}
    milestone_cards = "".join(_milestone(value, tasks) for value in snapshot.milestones)
    blockers = "".join(
        f'''<article><div class="prd-meta"><span>{escape(value.status)}</span></div>
<h2>{escape(value.title)}</h2><p>{escape(value.detail)}</p></article>'''
        for value in snapshot.blockers
    )
    decisions = "".join(
        f'''<article><div class="prd-meta"><span>{escape(value.outcome.replace('_', ' ').title())}</span></div>
<h2>{escape(value.title)}</h2><p>{escape(value.rationale)}</p>
<div class="trace">Authority <code>{escape(value.authority_digest)}</code> · {escape(value.recorded_at.strftime('%d %b %Y, %H:%M UTC'))}</div></article>'''
        for value in snapshot.decisions
    )
    content = f'''<section class="review"><a class="back" href="/customer/requests/{escape(snapshot.request_id)}/estimate/review">← Delivery estimate</a>
<div class="review-head"><div><span class="eyebrow">Project progress dashboard · Day 20</span>
<h1>{escape(snapshot.title)}</h1><p>Live visibility over the exact governed scope. No implementation work has started.</p></div>
<span class="status">Awaiting authority</span></div>
<div class="signals"><span><strong>Overall progress</strong>{snapshot.progress_percentage}%</span>
<span><strong>Tasks</strong>{snapshot.completed_tasks}/{snapshot.total_tasks} complete</span>
<span><strong>Assigned agents</strong>{len(snapshot.assigned_agent_ids)}</span></div>
<article class="journey"><h2>Execution state</h2>
<p><strong>{snapshot.progress_percentage}% complete</strong> · {snapshot.total_tasks} planned tasks · {snapshot.in_progress_tasks} in progress · {snapshot.blocked_tasks} task-level blocked</p>
<progress value="{snapshot.progress_percentage}" max="100">{snapshot.progress_percentage}%</progress></article>
<h2 class="section-title">Milestones and tasks</h2><div class="prd-list">{milestone_cards}</div>
<h2 class="section-title">Agent assignments</h2><div class="journey"><strong>No operational agents assigned</strong>
<p>The dashboard exposes the assignment state only. Digital Twin execution remains a separately approved Day 22 module.</p></div>
<h2 class="section-title">Open blockers</h2><div class="grid">{blockers}</div>
<h2 class="section-title">Governed decisions</h2><div class="prd-list">{decisions}</div>
<div class="receipt"><dl><dt>Project progress</dt><dd><code>{escape(snapshot.progress_id)}</code></dd>
<dt>Locked roadmap</dt><dd><code>{escape(snapshot.roadmap_digest)}</code></dd>
<dt>Estimate</dt><dd><code>{escape(snapshot.estimate_digest)}</code></dd>
<dt>Projection digest</dt><dd><code>{escape(snapshot.digest)}</code></dd></dl></div>
<div class="notice"><strong>Visibility only — no execution authority</strong>
<p>This dashboard does not approve an estimate, assign an agent, create an executable task, connect a repository, write code, merge, deploy, bill, release, or select a pilot product.</p></div>
<div class="actions"><a class="button" href="/customer/requests/{escape(snapshot.request_id)}/evidence">Open preview and evidence centre</a>
<a class="button secondary" href="/customer/requests/{escape(snapshot.request_id)}/estimate/review">View estimate</a>
<a class="button secondary" href="/customer">Return to workspace</a></div></section>'''
    return _layout(f"Project progress for {snapshot.title} · ASCOS", content, csrf)


def _milestone(
    value: CustomerProgressMilestone,
    tasks: Mapping[str, CustomerProgressTask],
) -> str:
    task_rows = "".join(
        f'''<li><code>{escape(tasks[task_id].requirement_id)}</code> — {escape(tasks[task_id].title)}
<small>{escape(tasks[task_id].priority.title())} · Not started · Unassigned</small></li>'''
        for task_id in value.task_ids
    )
    return f'''<article class="prd-requirement"><div class="prd-meta"><span>Milestone {value.sequence}</span>
<span>{escape(value.status.replace('_', ' ').title())}</span><span>{value.progress_percentage}% complete</span></div>
<h2>{escape(value.title)}</h2><p><strong>{value.minimum_effort_days}–{value.maximum_effort_days} relative engineering days</strong></p>
<progress value="{value.progress_percentage}" max="100">{value.progress_percentage}%</progress>
<h3>Planned tasks</h3><ul>{task_rows}</ul>
<div class="trace">Governed roadmap item <code>{escape(value.milestone_id)}</code></div></article>'''
