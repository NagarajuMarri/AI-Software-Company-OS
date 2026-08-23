"""Deterministic shared provider for the Day 25 Engineering agent family."""

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
from runtime.workforce_engineering.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    ENGINEERING_ROLES,
    PILOT_STATUS,
    WORK_STATUS,
    action_ids_for,
    capability_ids_for,
    change_kind_for,
    contract_kind_for,
    discipline_for,
)


_CONTEXT_KEYS = {
    "work_order_id",
    "work_order_digest",
    "work_order_status",
    "assignment_title",
    "assignment_objective",
    "engineering_role",
    "opportunity_id",
    "opportunity_digest",
    "opportunity_title",
    "architecture_artifact_id",
    "architecture_artifact_digest",
    "architecture_status",
    "architecture_summary",
    "target_components_json",
    "technology_recommendations_json",
    "acceptance_checks_json",
    "constraints_json",
    "pilot_status",
}


class EngineeringAgentProvider:
    """One offline provider implementing four exact, tool-free Engineering profiles."""

    requires_live_authorization = False

    def __init__(self, provider_id: str = "deterministic-engineering-family-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("Engineering provider ID is invalid")
        self.provider_id = provider_id
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return ENGINEERING_ROLES

    def supported_capabilities(self) -> tuple[str, ...]:
        values: list[str] = []
        for role in ENGINEERING_ROLES:
            for capability_id in capability_ids_for(role):
                if capability_id not in values:
                    values.append(capability_id)
        return tuple(values)

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
        """Rebuild one role-bound output for restart reconciliation."""

        if not isinstance(request, ProviderExecutionRequest):
            raise ValueError("Engineering provider request is invalid")
        role = request.business_role
        if not (
            request.provider_id == self.provider_id
            and role in ENGINEERING_ROLES
            and request.required_capability_ids == capability_ids_for(role)
            and request.allowed_action_ids == action_ids_for(role)
            and request.allowed_tool_ids == ()
            and request.max_tool_calls == 0
        ):
            raise ValueError("Engineering provider request profile is invalid")
        context = {item.key: item.value for item in request.context}
        if len(context) != len(request.context) or set(context) != _CONTEXT_KEYS:
            raise ValueError("Engineering provider context is not closed")
        if not (
            context["engineering_role"] == role.value
            and context["work_order_status"] == ASSIGNMENT_STATUS
            and context["architecture_status"] == ARCHITECTURE_STATUS
            and context["pilot_status"] == PILOT_STATUS
        ):
            raise ValueError("Engineering provider context state is invalid")
        components = _records(
            context["target_components_json"],
            {"component_id", "name", "responsibility", "data_responsibility"},
        )
        technologies = _records(
            context["technology_recommendations_json"],
            {"area", "technology", "status"},
        )
        acceptance_checks = _items(context["acceptance_checks_json"], "acceptance checks")
        constraints = _items(context["constraints_json"], "constraints")
        if (
            not components
            or not technologies
            or not acceptance_checks
            or not constraints
            or any(item["status"] != "PROPOSED" for item in technologies)
        ):
            raise ValueError("Engineering upstream context is incomplete")
        output = _output(role, context["assignment_title"], components, acceptance_checks)
        return ProviderExecutionResult(
            execution_id=request.execution_id,
            provider_id=self.provider_id,
            request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary=f"Bounded {role.value} assignment completed",
            output=tuple(ContextValue(key, value) for key, value in output),
        )


def _output(
    role: AgentRole,
    title: str,
    components: tuple[dict[str, object], ...],
    acceptance_checks: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    target_ids = tuple(str(item["component_id"]) for item in components)
    primary = target_ids[0]
    secondary = target_ids[-1]
    discipline = discipline_for(role).value
    change_kind = change_kind_for(role).value
    contract_kind = contract_kind_for(role).value

    if role is AgentRole.BACKEND_ENGINEER:
        items = (
            _item(
                "backend-use-case",
                discipline,
                primary,
                change_kind,
                "Define the application-service command flow, validate tenant and request identity, and coordinate the approved domain use case without infrastructure coupling.",
                "The bounded service workflow has explicit inputs, outcomes, and failure states.",
            ),
            _item(
                "backend-domain-invariant",
                discipline,
                secondary,
                change_kind,
                "Define deterministic domain transitions, idempotency behavior, and transaction boundaries for the assigned outcome.",
                "Repeated requests preserve business invariants and return a stable result.",
            ),
        )
        contracts = (
            _contract(
                "backend-service-command",
                contract_kind,
                "Tenant-bound service command",
                "Application Service",
                "Domain Core",
                ("tenant identity", "request identity", "validated command"),
                ("typed outcome", "canonical state revision"),
                "Reject unknown fields, cross-tenant identity, stale revisions, and invalid transitions.",
            ),
        )
        validation = (
            "Exercise domain invariants with deterministic unit checks",
            "Exercise idempotent retry and transaction rollback behavior",
            "Confirm no repository, command, deployment, or release effect occurred",
        )
    elif role is AgentRole.FRONTEND_ENGINEER:
        items = (
            _item(
                "frontend-reviewed-flow",
                discipline,
                primary,
                change_kind,
                "Define the reviewed end-user flow with semantic structure, keyboard operation, responsive layout, and explicit empty, loading, success, and failure states.",
                "The assigned journey is understandable and operable across supported viewport sizes.",
            ),
            _item(
                "frontend-state-contract",
                discipline,
                secondary,
                change_kind,
                "Define client state transitions and bounded service integration without embedding domain or authorization rules in the interface.",
                "The interface renders only validated state and exposes recoverable failures clearly.",
            ),
        )
        contracts = (
            _contract(
                "frontend-view-model",
                contract_kind,
                "Accessible reviewed view model",
                "Application Service",
                "Interface Boundary",
                ("typed read model", "allowed user actions", "validation messages"),
                ("semantic view state", "bounded user intent"),
                "Render a safe error state and do not infer missing authorization or domain values.",
            ),
        )
        validation = (
            "Inspect semantic names, focus order, keyboard behavior, and responsive states",
            "Inspect explicit loading, empty, success, validation, and service-failure states",
            "Confirm no subjective UX acceptance or release approval was granted",
        )
    elif role is AgentRole.AI_ENGINEER:
        items = (
            _item(
                "ai-provider-boundary",
                discipline,
                primary,
                change_kind,
                "Define a provider-neutral typed model boundary with bounded inputs, closed outputs, timeouts, sanitized failures, and no credential exposure.",
                "AI behavior is replaceable, schema validated, and unable to bypass product authority.",
            ),
            _item(
                "ai-evaluation-evidence",
                discipline,
                secondary,
                change_kind,
                "Define deterministic fixture evaluation, output-digest evidence, uncertainty handling, and escalation for results requiring human judgment.",
                "AI quality and failure behavior can be evaluated without storing raw secrets or prompts.",
            ),
        )
        contracts = (
            _contract(
                "ai-inference-boundary",
                contract_kind,
                "Governed AI inference request",
                "Application Service",
                "AI Provider Adapter",
                ("bounded objective", "non-secret context", "closed response schema"),
                ("typed result", "confidence or uncertainty", "sanitized evidence digest"),
                "Fail closed on schema drift, timeout, identity mismatch, or authority mismatch.",
            ),
        )
        validation = (
            "Evaluate deterministic fixtures for schema, boundary, and uncertainty behavior",
            "Exercise timeout, malformed output, and provider-failure paths",
            "Confirm no live provider, network, credential, or model-purchase authority was used",
        )
    elif role is AgentRole.DATA_ENGINEER:
        items = (
            _item(
                "data-tenant-model",
                discipline,
                primary,
                change_kind,
                "Define tenant-scoped record identity, canonical fields, integrity constraints, revision rules, and ownership boundaries for the assigned data.",
                "The proposed data model rejects cross-tenant and structurally invalid records.",
            ),
            _item(
                "data-schema-evolution",
                discipline,
                secondary,
                change_kind,
                "Define forward migration, compatibility verification, rollback preparation, retention metadata, and recovery checks without executing a migration.",
                "Schema evolution is reviewable, reversible, and bound to explicit data invariants.",
            ),
        )
        contracts = (
            _contract(
                "data-record-boundary",
                contract_kind,
                "Canonical tenant record",
                "Domain Core",
                "Persistence Adapter",
                ("tenant identity", "record identity", "expected revision", "typed fields"),
                ("stored revision", "integrity outcome", "retention metadata"),
                "Reject cross-tenant, stale, malformed, non-canonical, and constraint-breaking writes.",
            ),
        )
        validation = (
            "Check schema constraints, tenant isolation, and canonical serialization rules",
            "Check migration compatibility, rollback preparation, and recovery invariants",
            "Confirm no database migration, environment, deployment, or release effect occurred",
        )
    else:  # pragma: no cover - protected by the closed role profile above
        raise ValueError("Engineering role is unsupported")

    return (
        ("title", f"{role.value} bounded execution: {title}"),
        (
            "summary",
            "The exact assigned engineering outcome was translated into typed implementation "
            "instructions and interface contracts inside the approved role boundary; product "
            "workspace execution remains separately authorized.",
        ),
        ("implementation_items_json", _json(items)),
        ("interface_contracts_json", _json(contracts)),
        ("validation_checks_json", _json(validation)),
        (
            "handoff_notes_json",
            _json(
                (
                    "Preserve the exact architecture and work-order digests in any later workspace execution",
                    "Independent QA and Security review remain Days 26 and 27 and were not performed here",
                    "Repository, command, deployment, merge, release, and pilot authority remain excluded",
                )
            ),
        ),
        ("status_state", WORK_STATUS),
        (
            "completed_items_json",
            _json((f"{role.value} bounded engineering output and interface contract prepared",)),
        ),
        (
            "next_actions_json",
            _json(("Obtain required architecture and workspace authorization before applying changes",)),
        ),
        (
            "blockers_json",
            _json(("Human architecture review and an authorized isolated product workspace are pending",)),
        ),
        (
            "escalations_json",
            _json(("Escalate scope, architecture, security-policy, quality-signoff, or release decisions",)),
        ),
        ("artifact_status", ARTIFACT_STATUS),
        ("architecture_status", ARCHITECTURE_STATUS),
        ("pilot_status", PILOT_STATUS),
        ("acceptance_checks_json", _json(acceptance_checks)),
    )


def _item(
    item_id: str,
    discipline: str,
    target_component_id: str,
    change_kind: str,
    implementation: str,
    expected_outcome: str,
) -> dict[str, str]:
    return {
        "item_id": item_id,
        "discipline": discipline,
        "target_component_id": target_component_id,
        "change_kind": change_kind,
        "implementation": implementation,
        "expected_outcome": expected_outcome,
    }


def _contract(
    contract_id: str,
    kind: str,
    name: str,
    producer: str,
    consumer: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    failure_behavior: str,
) -> dict[str, object]:
    return {
        "contract_id": contract_id,
        "kind": kind,
        "name": name,
        "producer": producer,
        "consumer": consumer,
        "inputs": inputs,
        "outputs": outputs,
        "failure_behavior": failure_behavior,
    }


def _items(value: str, label: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError(f"Engineering {label} are invalid")
    return tuple(decoded)


def _records(value: str, keys: set[str]) -> tuple[dict[str, object], ...]:
    decoded = json.loads(value)
    if (
        not isinstance(decoded, list)
        or any(not isinstance(item, dict) or set(item) != keys for item in decoded)
    ):
        raise ValueError("Engineering structured context is invalid")
    return tuple(decoded)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
