"""Deterministic Software Architect provider for the Day 22 execution boundary."""

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
from runtime.workforce_architecture.models import (
    ADR_STATUS,
    ARCHITECT_ACTION_IDS,
    ARCHITECT_CAPABILITY_IDS,
    ARTIFACT_STATUS,
    PILOT_STATUS,
    RECOMMENDATION_STATUS,
    WORK_STATUS,
)


_CONTEXT_KEYS = {
    "opportunity_id",
    "opportunity_digest",
    "opportunity_title",
    "product_manager_artifact_id",
    "product_manager_artifact_digest",
    "product_manager_summary",
    "goals_json",
    "scope_in_json",
    "scope_out_json",
    "plan_items_json",
    "pilot_status",
}


class SoftwareArchitectProvider:
    """Local architecture provider with no ambient host or approval capability."""

    requires_live_authorization = False

    def __init__(self, provider_id: str = "deterministic-architect-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("Software Architect provider ID is invalid")
        self.provider_id = provider_id
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return (AgentRole.SOFTWARE_ARCHITECT,)

    def supported_capabilities(self) -> tuple[str, ...]:
        return ARCHITECT_CAPABILITY_IDS

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
        """Purely rebuild the same proposed architecture for restart reconciliation."""

        if not isinstance(request, ProviderExecutionRequest) or not (
            request.provider_id == self.provider_id
            and request.business_role is AgentRole.SOFTWARE_ARCHITECT
            and request.required_capability_ids == ARCHITECT_CAPABILITY_IDS
            and request.allowed_action_ids == ARCHITECT_ACTION_IDS
            and request.allowed_tool_ids == ()
            and request.max_tool_calls == 0
        ):
            raise ValueError("Software Architect provider request profile is invalid")
        context = {item.key: item.value for item in request.context}
        if len(context) != len(request.context) or set(context) != _CONTEXT_KEYS:
            raise ValueError("Software Architect context is not closed")
        if context["pilot_status"] != PILOT_STATUS:
            raise ValueError("Software Architect cannot select an official pilot")
        goals = _items(context["goals_json"], "goals")
        scope_in = _items(context["scope_in_json"], "scope in")
        scope_out = _items(context["scope_out_json"], "scope out")
        plan_items = _items(context["plan_items_json"], "plan items")
        if not goals or not scope_in or not scope_out or not plan_items:
            raise ValueError("Software Architect source plan is incomplete")
        title = context["opportunity_title"]
        output = _output(title, goals, scope_in, scope_out)
        return ProviderExecutionResult(
            execution_id=request.execution_id,
            provider_id=self.provider_id,
            request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary="Software architecture, technology, ADR, and risk drafts completed",
            output=tuple(ContextValue(key, value) for key, value in output),
        )


def _output(
    title: str,
    goals: tuple[str, ...],
    scope_in: tuple[str, ...],
    scope_out: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    principles = (
        "Keep product rules independent from delivery and infrastructure adapters",
        "Enforce tenant isolation and least privilege at every boundary",
        "Prefer replaceable standards-based interfaces over provider coupling",
        "Produce testable, observable, and content-addressed evidence",
    )
    components = (
        {
            "component_id": "interface-boundary",
            "name": "Interface Boundary",
            "responsibility": "Presents reviewed user workflows and validates bounded inputs",
            "interfaces": ["HTTPS"],
            "data_responsibility": "Accepts transient input and exposes no persistence authority",
        },
        {
            "component_id": "application-service",
            "name": "Application Service",
            "responsibility": "Coordinates product use cases without infrastructure coupling",
            "interfaces": ["Interface Boundary", "Domain Core"],
            "data_responsibility": "Coordinates validated commands and read models",
        },
        {
            "component_id": "domain-core",
            "name": "Domain Core",
            "responsibility": "Owns product rules and explicit state transitions",
            "interfaces": ["Application Service", "Persistence Port"],
            "data_responsibility": "Owns canonical business invariants",
        },
        {
            "component_id": "persistence-adapter",
            "name": "Persistence Adapter",
            "responsibility": "Provides tenant-scoped transactions and migrations",
            "interfaces": ["Persistence Port", "PostgreSQL"],
            "data_responsibility": "Stores canonical tenant records and retention metadata",
        },
        {
            "component_id": "evidence-boundary",
            "name": "Evidence Boundary",
            "responsibility": "Records content-addressed audit and acceptance evidence",
            "interfaces": ["Application Service"],
            "data_responsibility": "Stores sanitized identities, outcomes, and digests",
        },
    )
    technologies = (
        {
            "recommendation_id": "tech-runtime",
            "area": "Application runtime",
            "technology": "Python 3.11+",
            "rationale": "Matches governed ASCOS contracts and supports typed portable services",
            "alternatives_considered": ["TypeScript on Node.js", "Java 21"],
            "status": RECOMMENDATION_STATUS,
        },
        {
            "recommendation_id": "tech-interface",
            "area": "Service interface",
            "technology": "HTTPS JSON API with server-rendered HTML where suitable",
            "rationale": "Keeps the external contract standards based and browser verifiable",
            "alternatives_considered": ["Single-page application only", "GraphQL only"],
            "status": RECOMMENDATION_STATUS,
        },
        {
            "recommendation_id": "tech-persistence",
            "area": "Transactional persistence",
            "technology": "PostgreSQL 16+",
            "rationale": "Provides constraints, transactions, recovery, and tenant-aware indexing",
            "alternatives_considered": ["SQLite", "Document database"],
            "status": RECOMMENDATION_STATUS,
        },
        {
            "recommendation_id": "tech-verification",
            "area": "Runtime verification",
            "technology": "pytest plus Playwright Chromium",
            "rationale": "Combines deterministic domain checks with actual end-user journeys",
            "alternatives_considered": ["Manual-only testing", "Unit tests only"],
            "status": RECOMMENDATION_STATUS,
        },
    )
    adrs = (
        {
            "adr_id": "adr-d24-modular-boundary",
            "title": "Adopt a modular domain service boundary",
            "context": "The product scope needs stable rules while interfaces and providers evolve.",
            "decision": "Separate interface, application, domain, persistence, and evidence boundaries.",
            "consequences": [
                "Adapters can change without rewriting domain rules",
                "Boundary contracts require explicit integration tests",
            ],
            "status": ADR_STATUS,
            "human_approval_required": True,
        },
        {
            "adr_id": "adr-d24-relational-persistence",
            "title": "Use transactional relational persistence",
            "context": "Tenant records require integrity, migrations, concurrency, and recovery.",
            "decision": "Use PostgreSQL behind a domain-owned persistence port.",
            "consequences": [
                "Schema migrations become governed release artifacts",
                "Operational backup and recovery procedures are required",
            ],
            "status": ADR_STATUS,
            "human_approval_required": True,
        },
    )
    risks = (
        {
            "risk_id": "risk-d24-scope-drift",
            "title": "Scope-to-architecture drift",
            "severity": "HIGH",
            "likelihood": "MEDIUM",
            "impact": "Components could implement behavior outside the reviewed product scope.",
            "mitigation": "Trace every component responsibility to reviewed scope and non-goals.",
            "escalation": "Escalate material scope changes to Product and founder review.",
        },
        {
            "risk_id": "risk-d24-tenant-isolation",
            "title": "Tenant isolation failure",
            "severity": "HIGH",
            "likelihood": "LOW",
            "impact": "A boundary defect could expose records across customer workspaces.",
            "mitigation": "Carry tenant identity through contracts and enforce database constraints.",
            "escalation": "Escalate detailed threat analysis to the Day 27 Security Engineer.",
        },
        {
            "risk_id": "risk-d24-technology-lock-in",
            "title": "Technology lock-in",
            "severity": "MEDIUM",
            "likelihood": "MEDIUM",
            "impact": "Provider-specific coupling could increase replacement cost.",
            "mitigation": "Use ports, standards-based APIs, and replaceable adapters.",
            "escalation": "Return incompatible changes to architecture review.",
        },
    )
    return (
        ("title", f"Draft software architecture for {title}"),
        (
            "summary",
            "A modular tenant-scoped service architecture is proposed for the exact reviewed "
            "Product Manager plan; all decisions remain subject to human architecture review.",
        ),
        (
            "domain_boundary",
            f"Own only the reviewed outcomes for {title}; exclude {scope_out[0]} and all "
            "repository, deployment, billing, release, and pilot-selection operations.",
        ),
        ("principles_json", _json(principles)),
        ("components_json", _json(components)),
        (
            "integration_points_json",
            _json(("Browser to HTTPS interface", "Application to domain ports", "Persistence port to PostgreSQL")),
        ),
        (
            "data_lifecycle_json",
            _json(("Validate before acceptance", "Bind records to tenant identity", "Persist canonical revisions", "Retain audit digests for review")),
        ),
        (
            "security_controls_json",
            _json(("Authenticated tenant boundary", "Least-privilege adapters", "No secrets in artifacts", "Explicit security review before release")),
        ),
        (
            "quality_strategy_json",
            _json(("Unit-test domain invariants", "Integration-test adapters", "Run actual Chromium journeys", "Bind evidence to the exact commit")),
        ),
        ("technology_recommendations_json", _json(technologies)),
        ("adr_drafts_json", _json(adrs)),
        ("technical_risks_json", _json(risks)),
        ("status_state", WORK_STATUS),
        (
            "completed_items_json",
            _json(("Architecture, technology, ADR, and technical-risk drafts prepared",)),
        ),
        (
            "next_actions_json",
            _json(("Human architecture, security, quality, and product stakeholders review the proposal",)),
        ),
        ("blockers_json", _json(("Human architecture approval is pending",))),
        (
            "human_decisions_json",
            _json(("Major architecture direction", "Technology recommendations and proposed ADRs")),
        ),
        ("artifact_status", ARTIFACT_STATUS),
        ("pilot_status", PILOT_STATUS),
    )


def _items(value: str, label: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError(f"Software Architect {label} are invalid")
    return tuple(decoded)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
