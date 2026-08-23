"""Deterministic role provider for bounded CEO and Product Manager work."""

from __future__ import annotations

import json

from runtime.agents import AgentRole
from runtime.digital_twin import (
    ContextValue,
    DigitalTwinExecutionStatus,
    ProviderExecutionRequest,
    ProviderExecutionResult,
)
from runtime.digital_twin.contracts import DigitalTwinToolGateway
from runtime.workforce_leadership.models import (
    ARTIFACT_STATUS,
    CEO_ACTION_IDS,
    CEO_CAPABILITY_IDS,
    LeadershipArtifactKind,
    PILOT_STATUS,
    PRODUCT_MANAGER_ACTION_IDS,
    PRODUCT_MANAGER_CAPABILITY_IDS,
    WORK_STATUS,
    validate_action_profile,
)


_COMMON_CONTEXT = {
    "opportunity_id",
    "opportunity_digest",
    "title",
    "problem_statement",
    "pilot_status",
}
_PM_CONTEXT = {"upstream_artifact_digest", "upstream_summary"}


class LeadershipAgentProvider:
    """Local provider with no filesystem, network, subprocess, or approval capability."""

    requires_live_authorization = False

    def __init__(self, provider_id: str = "deterministic-leadership-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("Leadership provider ID is invalid")
        self.provider_id = provider_id
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return (AgentRole.CEO, AgentRole.PROJECT_MANAGER)

    def supported_capabilities(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(CEO_CAPABILITY_IDS + PRODUCT_MANAGER_CAPABILITY_IDS))

    def supported_tool_ids(self) -> tuple[str, ...]:
        return ()

    def execute(
        self,
        request: ProviderExecutionRequest,
        _tools: DigitalTwinToolGateway,
    ) -> ProviderExecutionResult:
        self.execution_count += 1
        return self.render(request)

    def render(self, request: ProviderExecutionRequest) -> ProviderExecutionResult:
        """Purely rebuild the exact typed output for restart reconciliation."""

        if not isinstance(request, ProviderExecutionRequest):
            raise ValueError("Leadership provider request is invalid")
        if request.provider_id != self.provider_id:
            raise ValueError("Leadership provider identity does not match")
        if request.allowed_tool_ids or request.max_tool_calls != 0:
            raise ValueError("Leadership role profiles have no tool authority")
        context = _context_map(request)
        if context["pilot_status"] != PILOT_STATUS:
            raise ValueError("Leadership work cannot select an official pilot")
        target_users = _indexed(context, "target_user")
        desired_outcomes = _indexed(context, "desired_outcome")
        constraints = _indexed(context, "constraint", required=False)
        if request.business_role is AgentRole.CEO:
            validate_action_profile(request.allowed_action_ids, CEO_ACTION_IDS)
            if request.required_capability_ids != CEO_CAPABILITY_IDS:
                raise ValueError("CEO capability profile is invalid")
            if set(context) != _expected_context_keys(
                target_users, desired_outcomes, constraints, include_upstream=False
            ):
                raise ValueError("CEO opportunity context is not closed")
            output = _ceo_output(context, target_users, desired_outcomes, constraints)
            summary = "CEO opportunity intake and status report completed as a draft"
        elif request.business_role is AgentRole.PROJECT_MANAGER:
            validate_action_profile(request.allowed_action_ids, PRODUCT_MANAGER_ACTION_IDS)
            if request.required_capability_ids != PRODUCT_MANAGER_CAPABILITY_IDS:
                raise ValueError("Product Manager capability profile is invalid")
            if set(context) != _expected_context_keys(
                target_users, desired_outcomes, constraints, include_upstream=True
            ):
                raise ValueError("Product Manager scope context is not closed")
            output = _product_manager_output(
                context,
                target_users,
                desired_outcomes,
                constraints,
            )
            summary = "Product Manager scope, plan, and status report completed as a draft"
        else:
            raise ValueError("Leadership provider received an unsupported Business Role")
        return ProviderExecutionResult(
            execution_id=request.execution_id,
            provider_id=self.provider_id,
            request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary=summary,
            output=tuple(ContextValue(key, value) for key, value in output),
        )


def _context_map(request: ProviderExecutionRequest) -> dict[str, str]:
    values = {item.key: item.value for item in request.context}
    if len(values) != len(request.context) or not _COMMON_CONTEXT <= set(values):
        raise ValueError("Leadership provider context is invalid")
    return values


def _indexed(
    values: dict[str, str],
    prefix: str,
    *,
    required: bool = True,
) -> tuple[str, ...]:
    keys = {key for key in values if key.startswith(f"{prefix}_")}
    positions: list[int] = []
    for key in keys:
        suffix = key.removeprefix(f"{prefix}_")
        if not suffix.isdigit() or suffix.startswith("0"):
            raise ValueError("Leadership indexed context is invalid")
        positions.append(int(suffix))
    if sorted(positions) != list(range(1, len(positions) + 1)):
        raise ValueError("Leadership indexed context is not contiguous")
    found = [values[f"{prefix}_{index}"] for index in range(1, len(positions) + 1)]
    if required and not found:
        raise ValueError("Leadership indexed context is missing")
    return tuple(found)


def _expected_context_keys(
    target_users: tuple[str, ...],
    desired_outcomes: tuple[str, ...],
    constraints: tuple[str, ...],
    *,
    include_upstream: bool,
) -> set[str]:
    values = set(_COMMON_CONTEXT)
    values.update(f"target_user_{index}" for index in range(1, len(target_users) + 1))
    values.update(
        f"desired_outcome_{index}" for index in range(1, len(desired_outcomes) + 1)
    )
    values.update(f"constraint_{index}" for index in range(1, len(constraints) + 1))
    if include_upstream:
        values.update(_PM_CONTEXT)
    return values


def _ceo_output(
    context: dict[str, str],
    target_users: tuple[str, ...],
    desired_outcomes: tuple[str, ...],
    constraints: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    constraint_question = (
        f"Which constraint is non-negotiable before scope planning: {constraints[0]}?"
        if constraints
        else "Which operating constraint must be confirmed before scope planning?"
    )
    return (
        ("artifact_kind", LeadershipArtifactKind.CEO_OPPORTUNITY_BRIEF.value),
        (
            "summary",
            f"{context['title']} frames a bounded opportunity for {target_users[0]}: "
            f"{_clip(context['problem_statement'], 700)}",
        ),
        ("goals_json", _json(desired_outcomes)),
        (
            "clarification_questions_json",
            _json(
                (
                    f"Which outcome should be validated first for {target_users[0]}?",
                    constraint_question,
                )
            ),
        ),
        ("status_state", WORK_STATUS),
        (
            "completed_items_json",
            _json(("Opportunity intake framed with goals and constraints",)),
        ),
        (
            "next_actions_json",
            _json(("Human reviews opportunity fit before any Product Manager delegation",)),
        ),
        ("blockers_json", _json(("Human opportunity review is pending",))),
        (
            "human_decisions_json",
            _json(("Opportunity fit and priority", "Any budget or official pilot decision")),
        ),
        ("artifact_status", ARTIFACT_STATUS),
        ("pilot_status", PILOT_STATUS),
    )


def _product_manager_output(
    context: dict[str, str],
    target_users: tuple[str, ...],
    desired_outcomes: tuple[str, ...],
    constraints: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    scope_in = desired_outcomes
    scope_out = (
        "Architecture, technology selection, ADRs, and technical risk analysis",
        "Engineering implementation, repository changes, and deployment",
        "Budget approval, release approval, billing, and official pilot selection",
    )
    plan_items = (
        "Confirm the primary user outcome and measurable success evidence",
        "Reconcile the minimum product scope against declared constraints",
        "Present the bounded product plan for human review before execution",
    )
    constraint_question = (
        f"How should the first reviewed scope satisfy this constraint: {constraints[0]}?"
        if constraints
        else "Which constraint should govern the first reviewed product scope?"
    )
    return (
        ("artifact_kind", LeadershipArtifactKind.PRODUCT_MANAGER_PLAN.value),
        (
            "summary",
            f"Draft product scope for {context['title']} is linked to CEO brief "
            f"{context['upstream_artifact_digest'][:16]} and awaits human review.",
        ),
        ("goals_json", _json(desired_outcomes)),
        ("scope_in_json", _json(scope_in)),
        ("scope_out_json", _json(scope_out)),
        (
            "clarification_questions_json",
            _json(
                (
                    f"Is {target_users[0]} the priority user for the first scope?",
                    f"Which desired outcome is mandatory first: {desired_outcomes[0]}?",
                    constraint_question,
                )
            ),
        ),
        ("plan_items_json", _json(plan_items)),
        ("status_state", WORK_STATUS),
        (
            "completed_items_json",
            _json(("Scope, non-goals, questions, and product plan drafted",)),
        ),
        (
            "next_actions_json",
            _json(("Human reviews and revises the draft product plan",)),
        ),
        ("blockers_json", _json(("Human product-plan review is pending",))),
        (
            "human_decisions_json",
            _json(("Final product scope", "Any material scope or budget change")),
        ),
        ("artifact_status", ARTIFACT_STATUS),
        ("pilot_status", PILOT_STATUS),
    )


def _json(values: tuple[str, ...]) -> str:
    return json.dumps(values, separators=(",", ":"), ensure_ascii=False)


def _clip(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    return f"{value[: maximum - 1].rstrip()}…"
