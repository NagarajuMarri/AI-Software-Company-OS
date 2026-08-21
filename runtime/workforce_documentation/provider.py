"""Deterministic tool-free provider for the Day 29 Documentation Engineer."""

from __future__ import annotations

import json

from runtime.agents import AgentRole
from runtime.digital_twin import ContextValue, DigitalTwinExecutionStatus, ProviderExecutionRequest, ProviderExecutionResult
from runtime.digital_twin.contracts import DigitalTwinToolGateway
from runtime.workforce_engineering import ENGINEERING_ROLES
from runtime.workforce_documentation.models import (
    ARCHITECTURE_STATUS, ARTIFACT_STATUS, ASSIGNMENT_STATUS, DEVOPS_STATUS,
    DOCUMENTATION_ACTIONS, DOCUMENTATION_CAPABILITIES, DOCUMENTATION_ROLE,
    DOCUMENT_STATUS, ENGINEERING_STATUS, PILOT_STATUS, PUBLICATION_STATE,
    QA_STATUS, SECURITY_STATUS, VALIDATION_STATE, WORK_STATUS,
)


_CONTEXT_KEYS = {
    "work_order_id", "work_order_digest", "work_order_status", "assignment_title",
    "assignment_objective", "documentation_role", "opportunity_id", "opportunity_digest",
    "opportunity_title", "architecture_artifact_id", "architecture_artifact_digest",
    "architecture_status", "engineering_artifact_digests_json", "engineering_sources_json",
    "qa_artifact_id", "qa_artifact_digest", "qa_status", "security_artifact_id",
    "security_artifact_digest", "security_status", "devops_artifact_id",
    "devops_artifact_digest", "devops_status", "acceptance_checks_json",
    "documentation_risks_json", "constraints_json", "pilot_status",
}
_SOURCE_KEYS = {"artifact_digest", "business_role", "interface_contract_ids", "target_component_ids", "status", "pilot_status"}


class DocumentationEngineerProvider:
    requires_live_authorization = False

    def __init__(self, provider_id: str = "deterministic-documentation-engineer-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("Documentation provider ID is invalid")
        self.provider_id = provider_id
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return (DOCUMENTATION_ROLE,)

    def supported_capabilities(self) -> tuple[str, ...]:
        return DOCUMENTATION_CAPABILITIES

    def supported_tool_ids(self) -> tuple[str, ...]:
        return ()

    def execute(self, request: ProviderExecutionRequest, _tools: DigitalTwinToolGateway) -> ProviderExecutionResult:
        self.execution_count += 1
        return self.render(request)

    def render(self, request: ProviderExecutionRequest) -> ProviderExecutionResult:
        if not isinstance(request, ProviderExecutionRequest):
            raise ValueError("Documentation provider request is invalid")
        if not (request.provider_id == self.provider_id and request.business_role is DOCUMENTATION_ROLE
                and request.required_capability_ids == DOCUMENTATION_CAPABILITIES
                and request.allowed_action_ids == DOCUMENTATION_ACTIONS and request.allowed_tool_ids == ()
                and request.max_tool_calls == 0):
            raise ValueError("Documentation provider request profile is invalid")
        context = {item.key: item.value for item in request.context}
        if len(context) != len(request.context) or set(context) != _CONTEXT_KEYS:
            raise ValueError("Documentation provider context is not closed")
        if not (context["documentation_role"] == DOCUMENTATION_ROLE.value
                and context["work_order_status"] == ASSIGNMENT_STATUS
                and context["architecture_status"] == ARCHITECTURE_STATUS
                and context["qa_status"] == QA_STATUS and context["security_status"] == SECURITY_STATUS
                and context["devops_status"] == DEVOPS_STATUS and context["pilot_status"] == PILOT_STATUS):
            raise ValueError("Documentation provider context state is invalid")
        sources = _records(context["engineering_sources_json"], _SOURCE_KEYS)
        digests = _items(context["engineering_artifact_digests_json"], "source digests")
        acceptance = _items(context["acceptance_checks_json"], "acceptance checks")
        if not (len(sources) == len(digests) == 4
                and tuple(item["business_role"] for item in sources) == tuple(role.value for role in ENGINEERING_ROLES)
                and tuple(item["artifact_digest"] for item in sources) == digests
                and all(item["status"] == ENGINEERING_STATUS and item["pilot_status"] == PILOT_STATUS for item in sources)
                and _items(context["documentation_risks_json"], "risks")
                and _items(context["constraints_json"], "constraints") and acceptance):
            raise ValueError("Documentation upstream context is incomplete")
        output = _output(context, sources, acceptance)
        return ProviderExecutionResult(
            execution_id=request.execution_id, provider_id=self.provider_id, request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary="Bounded Documentation Engineer assignment completed",
            output=tuple(ContextValue(key, value) for key, value in output),
        )


def _section(section_id: str, heading: str, content: str) -> dict[str, str]:
    return {"section_id": section_id, "heading": heading, "content": content}


def _document(document_id: str, kind: str, title: str, audience: tuple[str, ...], purpose: str,
              sources: tuple[str, ...], sections: tuple[dict[str, str], ...]) -> dict[str, object]:
    return {
        "document_id": document_id, "kind": kind, "title": title, "audience": audience,
        "purpose": purpose, "source_artifact_digests": sources, "sections": sections,
        "validation_checks": (
            "Claims bind exact persisted sources",
            "Required draft sections and boundaries are complete",
            "Human review is required before publication",
        ),
        "validation_state": VALIDATION_STATE, "publication_state": PUBLICATION_STATE,
        "status": DOCUMENT_STATUS,
    }


def _output(context: dict[str, str], sources: tuple[dict[str, object], ...], acceptance: tuple[str, ...]):
    engineering = tuple(str(item["artifact_digest"]) for item in sources)
    architecture = context["architecture_artifact_digest"]
    qa = context["qa_artifact_digest"]
    security = context["security_artifact_digest"]
    devops = context["devops_artifact_digest"]
    documents = (
        _document("documentation-technical", "TECHNICAL", "Technical architecture and component guide",
                  ("Software engineers", "Technical reviewers"),
                  "Explain the source-bound architecture, components, interfaces, data flow, and implementation boundaries.",
                  (architecture, *engineering), (
                      _section("technical-overview", "Architecture overview", "The draft architecture defines the product boundary and exact component responsibilities; it remains pending human architecture review."),
                      _section("technical-components", "Components and interfaces", "Backend, Frontend, AI, and Data outputs are separate draft implementation instructions with explicit component and interface ownership."),
                      _section("technical-data", "Data and integration flow", "Interface contracts and the Data Engineering boundary define source-bound integration and persistence behavior without claiming implementation."),
                      _section("technical-boundaries", "Authority and lifecycle boundaries", "No product workspace, code application, merge, deployment, release, or pilot authority is created by these draft documents."),
                  )),
        _document("documentation-user", "USER", "User guide and expected journeys",
                  ("Customers", "Product reviewers"),
                  "Describe expected customer journeys, visible states, limitations, and review expectations.",
                  (engineering[1], qa), (
                      _section("user-purpose", "Product purpose", "The source product plan and interface output describe a customer-facing journey that must be verified in an authorized workspace before release."),
                      _section("user-journeys", "Expected user journeys", "Follow the QA plan for happy paths, validation paths, persistence recovery, access control, and browser behavior."),
                      _section("user-errors", "Errors and recovery", "Show bounded, non-sensitive errors; preserve user input safely; and provide recovery without exposing internal state."),
                      _section("user-limits", "Current limitations", "All described behavior is draft, no official pilot is selected, and no product deployment or customer availability is claimed."),
                  )),
        _document("documentation-api", "API", "API and interface contract reference",
                  ("API consumers", "Backend and frontend engineers"),
                  "Document exact interface ownership, inputs, outputs, failures, authorization, and evidence expectations.",
                  (architecture, engineering[0], engineering[1], engineering[2]), (
                      _section("api-contracts", "Interface contracts", "Use only the persisted architecture and Engineering interface contract identifiers; unknown fields and cross-role ownership fail closed."),
                      _section("api-auth", "Authentication and authorization", "Every request must bind tenant, role, assignment, source digest, and least-privilege authority server-side."),
                      _section("api-errors", "Failure semantics", "Reject malformed, stale, cross-tenant, oversized, or unauthorized requests with bounded non-sensitive responses."),
                      _section("api-evidence", "Observability and evidence", "Record sanitized digest-bound outcomes and correlation identifiers without credentials, customer secrets, or raw provider payloads."),
                  )),
        _document("documentation-operations", "OPERATIONS", "Operations, monitoring, and rollback guide",
                  ("Operators", "Security and reliability reviewers"),
                  "Describe gated preview operations, monitoring, incident response, and rollback preparation.",
                  (security, devops), (
                      _section("operations-preflight", "Preflight and approval", "Require an exact authorized isolated preview target, source/configuration digests, QA/Security gates, and human approval before mutation."),
                      _section("operations-deploy", "Migration and deployment", "Follow the DevOps migration and deployment plans in order; every step currently remains NOT_EXECUTED."),
                      _section("operations-monitor", "Monitoring and incident response", "Evaluate availability, latency, integrity, tenant isolation, authorization, provider, QA, Security, browser, and evidence signals."),
                      _section("operations-rollback", "Rollback and escalation", "Stop traffic and mutations, restore approved identities, verify recovery, and require human disposition for irreversible or security-relevant failures."),
                  )),
        _document("documentation-release", "RELEASE", "Draft release notes and readiness record",
                  ("Customers", "Release reviewers", "Operators"),
                  "Summarize source-bound capabilities, validation evidence, known limitations, and release blockers.",
                  (architecture, *engineering, qa, security, devops), (
                      _section("release-summary", "Capability summary", "Architecture, Engineering, QA, Security, and DevOps drafts are bound; product implementation and delivery have not occurred."),
                      _section("release-validation", "Validation evidence", "QA specifications, Security check specifications, and DevOps gates exist; operational checks remain NOT_EXECUTED until authorized workspace execution."),
                      _section("release-limitations", "Known limitations", "No workspace, code, scan, deployment, production environment, billing, official pilot, or customer release exists."),
                      _section("release-gates", "Remaining release gates", "Complete Days 30–35 with explicit human authorization, exact-source evidence, customer preview acceptance, and final release approval."),
                  )),
    )
    handoff = {
        "handoff_id": "documentation-customer-handoff",
        "audience": ("Founder", "Customer reviewer"),
        "readiness_summary": "Five source-validated draft documents are ready for human review; no product, preview, release, or customer communication is published.",
        "deliverable_document_ids": tuple(item["document_id"] for item in documents),
        "review_checklist": (
            "Confirm technical and API claims against the exact Architecture and Engineering sources",
            "Confirm user journeys against QA specifications and product scope",
            "Confirm operations and release claims against Security and DevOps boundaries",
            "Approve or request revisions before any repository write, publication, or customer delivery",
        ),
        "known_limitations": (
            "All upstream implementation, QA, Security, and DevOps artifacts remain draft",
            "No isolated product workspace, coding loop, GitHub delivery, preview deployment, or customer acceptance exists",
        ),
        "next_actions": (
            "Human-review the five documents and exact source bindings",
            "Proceed to multi-agent orchestration only under the separately authorized Day 30 module",
        ),
        "publication_state": PUBLICATION_STATE,
    }
    status = {
        "state": WORK_STATUS,
        "completed_items": (
            "Bound the exact persisted Architecture, Engineering, QA, Security, and DevOps sources",
            "Generated five typed source-validated draft documents and one customer handoff",
            "Kept publication, repository, release, deployment, and customer communication authority at zero",
        ),
        "next_actions": ("Obtain human documentation review", "Authorize later workspace publication separately"),
        "blockers": ("No authorized documentation workspace or publication target exists",),
        "escalations": ("Escalate source conflicts, unsupported claims, secrets, or publication requests to a human",),
    }
    states = {
        "artifact_status": ARTIFACT_STATUS, "architecture_status": ARCHITECTURE_STATUS,
        "engineering_status": ENGINEERING_STATUS, "qa_status": QA_STATUS,
        "security_status": SECURITY_STATUS, "devops_status": DEVOPS_STATUS,
        "document_status": DOCUMENT_STATUS, "validation_state": VALIDATION_STATE,
        "publication_state": PUBLICATION_STATE, "pilot_status": PILOT_STATUS,
    }
    return (
        ("title", f"{context['assignment_title']} — governed documentation set"),
        ("summary", "Generated and exact-source validated five draft documentation records plus a customer handoff without accessing or publishing to any workspace, repository, customer channel, deployment, or release target."),
        ("technical_document_json", _json(documents[0])),
        ("user_document_json", _json(documents[1])),
        ("api_document_json", _json(documents[2])),
        ("operations_document_json", _json(documents[3])),
        ("release_document_json", _json(documents[4])),
        ("customer_handoff_json", _json(handoff)),
        ("coverage_requirements_json", _json((
            "Technical, user, API, operations, release, and customer handoff coverage",
            "Exact Architecture, four Engineering, QA, Security, and DevOps source bindings",
            "Audience, limitation, authority, human-review, and publication-state coverage",
            "No unsupported implementation, validation, publication, release, or pilot claim",
        ))),
        ("status_report_json", _json(status)), ("source_states_json", _json(states)),
        ("acceptance_checks_json", _json(acceptance)),
    )


def _records(value: str, keys: set[str]) -> tuple[dict[str, object], ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, dict) or set(item) != keys for item in decoded):
        raise ValueError("Documentation source records are invalid")
    return tuple(decoded)


def _items(value: str, label: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not decoded or any(not isinstance(item, str) or not item for item in decoded):
        raise ValueError(f"Documentation {label} are invalid")
    return tuple(decoded)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
