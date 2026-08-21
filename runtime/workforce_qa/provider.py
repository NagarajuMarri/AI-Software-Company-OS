"""Deterministic tool-free provider for the Day 26 QA Engineer agent."""

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
from runtime.workforce_engineering import ENGINEERING_ROLES
from runtime.workforce_qa.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    DEFECT_STATUS,
    ENGINEERING_STATUS,
    EXECUTION_STATE,
    PILOT_STATUS,
    QA_ACTIONS,
    QA_CAPABILITIES,
    QA_ROLE,
    WORK_STATUS,
)


_CONTEXT_KEYS = {
    "work_order_id",
    "work_order_digest",
    "work_order_status",
    "assignment_title",
    "assignment_objective",
    "qa_role",
    "opportunity_id",
    "opportunity_digest",
    "opportunity_title",
    "architecture_artifact_id",
    "architecture_artifact_digest",
    "architecture_status",
    "engineering_artifact_digests_json",
    "engineering_sources_json",
    "acceptance_checks_json",
    "quality_risks_json",
    "constraints_json",
    "pilot_status",
}

_SOURCE_KEYS = {
    "artifact_digest",
    "business_role",
    "interface_contract_ids",
    "target_component_ids",
    "status",
    "pilot_status",
}


class QAEngineerProvider:
    """One offline provider implementing the exact zero-tool QA profile."""

    requires_live_authorization = False

    def __init__(self, provider_id: str = "deterministic-qa-engineer-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("QA provider ID is invalid")
        self.provider_id = provider_id
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return (QA_ROLE,)

    def supported_capabilities(self) -> tuple[str, ...]:
        return QA_CAPABILITIES

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
        """Rebuild the closed QA output for retry/restart reconciliation."""

        if not isinstance(request, ProviderExecutionRequest):
            raise ValueError("QA provider request is invalid")
        if not (
            request.provider_id == self.provider_id
            and request.business_role is QA_ROLE
            and request.required_capability_ids == QA_CAPABILITIES
            and request.allowed_action_ids == QA_ACTIONS
            and request.allowed_tool_ids == ()
            and request.max_tool_calls == 0
        ):
            raise ValueError("QA provider request profile is invalid")
        context = {item.key: item.value for item in request.context}
        if len(context) != len(request.context) or set(context) != _CONTEXT_KEYS:
            raise ValueError("QA provider context is not closed")
        if not (
            context["qa_role"] == QA_ROLE.value
            and context["work_order_status"] == ASSIGNMENT_STATUS
            and context["architecture_status"] == ARCHITECTURE_STATUS
            and context["pilot_status"] == PILOT_STATUS
        ):
            raise ValueError("QA provider context state is invalid")
        sources = _records(context["engineering_sources_json"], _SOURCE_KEYS)
        digests = _items(context["engineering_artifact_digests_json"], "source digests")
        acceptance_checks = _items(context["acceptance_checks_json"], "acceptance checks")
        quality_risks = _items(context["quality_risks_json"], "quality risks")
        constraints = _items(context["constraints_json"], "constraints")
        if not (
            len(sources) == len(digests) == 4
            and tuple(item["business_role"] for item in sources)
            == tuple(role.value for role in ENGINEERING_ROLES)
            and tuple(item["artifact_digest"] for item in sources) == digests
            and all(item["status"] == ENGINEERING_STATUS for item in sources)
            and all(item["pilot_status"] == PILOT_STATUS for item in sources)
            and all(_string_list(item["target_component_ids"]) for item in sources)
            and all(_string_list(item["interface_contract_ids"]) for item in sources)
            and acceptance_checks
            and quality_risks
            and constraints
        ):
            raise ValueError("QA upstream context is incomplete")
        output = _output(context["assignment_title"], sources, acceptance_checks)
        return ProviderExecutionResult(
            execution_id=request.execution_id,
            provider_id=self.provider_id,
            request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary="Bounded QA Engineer assignment completed",
            output=tuple(ContextValue(key, value) for key, value in output),
        )


def _output(
    title: str,
    sources: tuple[dict[str, object], ...],
    acceptance_checks: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    levels = ("UNIT", "END_TO_END", "CONTRACT", "UNIT")
    kinds = ("UNIT", "CONTRACT", "PROPERTY", "PROPERTY")
    plans = []
    automation = []
    for index, source in enumerate(sources):
        role = str(source["business_role"])
        digest = str(source["artifact_digest"])
        components = _string_list(source["target_component_ids"])
        primary = components[0]
        slug = role.casefold().replace("_", "-")
        plans.append(
            {
                "item_id": f"qa-plan-{slug}",
                "level": levels[index],
                "source_engineering_artifact_digest": digest,
                "target_component_ids": components,
                "objective": (
                    f"Verify the {role} bounded output, acceptance behavior, negative paths, "
                    "and source-bound failure handling without executing product code."
                ),
                "preconditions": (
                    "The exact persisted Engineering artifact is available",
                    "An isolated product workspace and executable build are separately authorized",
                ),
                "expected_outcome": (
                    "Every specified assertion has deterministic evidence and failures produce "
                    "a source-bound defect report."
                ),
            }
        )
        automation.append(
            {
                "spec_id": f"qa-auto-{slug}",
                "kind": kinds[index],
                "source_engineering_artifact_digest": digest,
                "target_component_id": primary,
                "scenario": (
                    f"Specify deterministic {role} checks for valid input, invalid input, retry, "
                    "tenant isolation, and typed failure behavior."
                ),
                "fixture": "Generic non-customer fixture with fixed identities and expected outcomes",
                "assertions": (
                    "The documented success outcome is exact and schema-valid",
                    "The documented failure outcome is closed, sanitized, and source-bound",
                ),
                "negative_cases": (
                    "Reject wrong tenant, stale source digest, malformed values, and extra fields",
                    "Reject any unintended repository, command, network, or release effect",
                ),
                "execution_state": EXECUTION_STATE,
            }
        )
    backend, frontend, ai, data = sources
    integration = (
        _integration(
            "qa-integration-interface-service",
            (backend, frontend),
            "Validate the interface-to-service contract across bounded Frontend and Backend outputs",
        ),
        _integration(
            "qa-integration-service-data",
            (backend, data),
            "Validate service-to-persistence behavior across bounded Backend and Data outputs",
        ),
    )
    defects = (
        _defect(
            "qa-defect-frontend-runtime-evidence",
            "SPECIFICATION_GAP",
            "MEDIUM",
            frontend,
            "Frontend runtime evidence is not yet executable",
            "The Engineering artifact defines interface behavior but Day 31 workspace and runtime "
            "authorization do not yet exist.",
            "A later authorized run must prove semantic, responsive, keyboard, console, and network behavior.",
        ),
        _defect(
            "qa-defect-ai-failure-fixtures",
            "INTEGRATION_RISK",
            "HIGH",
            ai,
            "AI failure fixtures require authorized execution",
            "The Engineering artifact specifies malformed-output, timeout, and uncertainty handling "
            "without an executable product boundary in Day 26.",
            "A later authorized run must prove schema drift, timeout, and provider failures fail closed.",
        ),
    )
    return (
        ("title", f"QA_ENGINEER bounded execution: {title}"),
        (
            "summary",
            "The exact four persisted Engineering outputs were translated into a typed QA plan, "
            "automated-test specifications, integration-test specifications, and draft defect "
            "reports; no test code was written or executed.",
        ),
        ("test_plan_backend_json", _json((plans[0],))),
        ("test_plan_frontend_json", _json((plans[1],))),
        ("test_plan_ai_json", _json((plans[2],))),
        ("test_plan_data_json", _json((plans[3],))),
        ("automated_test_backend_json", _json((automation[0],))),
        ("automated_test_frontend_json", _json((automation[1],))),
        ("automated_test_ai_json", _json((automation[2],))),
        ("automated_test_data_json", _json((automation[3],))),
        ("integration_test_interface_service_json", _json((integration[0],))),
        ("integration_test_service_data_json", _json((integration[1],))),
        ("defect_reports_json", _json(defects)),
        (
            "coverage_requirements_json",
            _json(
                (
                    "Cover every Engineering role and exact persisted source digest",
                    "Cover success, validation, authorization, tenant, retry, and failure behavior",
                    "Cover Backend-Frontend and Backend-Data integration contracts",
                    "Record deterministic evidence and source-bound defects when execution is authorized",
                )
            ),
        ),
        (
            "handoff_notes_json",
            _json(
                (
                    "Preserve exact architecture, Engineering source, work-order, and receipt digests",
                    "Test code creation and execution require a later authorized isolated workspace",
                    "Security, DevOps, Documentation, orchestration, merge, deployment, and release remain excluded",
                )
            ),
        ),
        ("status_state", WORK_STATUS),
        (
            "completed_items_json",
            _json(("QA plan, automated-test specs, integration specs, and draft defects prepared",)),
        ),
        (
            "next_actions_json",
            _json(("Obtain authorization for an isolated workspace before writing or executing tests",)),
        ),
        (
            "blockers_json",
            _json(("Human architecture review and an authorized product workspace are pending",)),
        ),
        (
            "escalations_json",
            _json(("Escalate quality-signoff, security, scope, architecture, and release decisions",)),
        ),
        ("artifact_status", ARTIFACT_STATUS),
        ("architecture_status", ARCHITECTURE_STATUS),
        ("engineering_status", ENGINEERING_STATUS),
        ("defect_status", DEFECT_STATUS),
        ("pilot_status", PILOT_STATUS),
        ("acceptance_checks_json", _json(acceptance_checks)),
    )


def _integration(
    spec_id: str,
    sources: tuple[dict[str, object], dict[str, object]],
    scenario: str,
) -> dict[str, object]:
    return {
        "spec_id": spec_id,
        "source_engineering_artifact_digests": tuple(
            str(item["artifact_digest"]) for item in sources
        ),
        "interface_contract_ids": tuple(
            _string_list(item["interface_contract_ids"])[0] for item in sources
        ),
        "scenario": scenario,
        "preconditions": (
            "Both exact Engineering artifacts and their interface contracts are present",
            "The later product build is isolated and bound to the approved source commit",
        ),
        "steps": (
            "Arrange the exact generic request and expected interface states",
            "Exercise the producer-to-consumer success contract",
            "Exercise validation, timeout, identity, and rollback failure contracts",
            "Capture source-bound assertions and sanitized evidence",
        ),
        "expected_outcome": "Producer and consumer agree on typed success and fail-closed behavior",
        "failure_behavior": "Create a draft defect bound to both source digests; do not approve release",
        "execution_state": EXECUTION_STATE,
    }


def _defect(
    defect_id: str,
    kind: str,
    severity: str,
    source: dict[str, object],
    title: str,
    basis: str,
    expected: str,
) -> dict[str, object]:
    return {
        "defect_id": defect_id,
        "kind": kind,
        "severity": severity,
        "source_engineering_artifact_digest": str(source["artifact_digest"]),
        "title": title,
        "evidence_basis": basis,
        "expected_behavior": expected,
        "observed_risk": "The required behavior is specified but cannot be proven before authorized execution",
        "reproduction_conditions": (
            "Use the exact source-bound generic fixture",
            "Execute only after workspace and test authority are granted",
            "Record the exact commit, environment, assertion, and sanitized failure evidence",
        ),
        "status": DEFECT_STATUS,
    }


def _items(value: str, label: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError(f"QA {label} are invalid")
    return tuple(decoded)


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("QA nested source collection is invalid")
    return tuple(value)


def _records(value: str, keys: set[str]) -> tuple[dict[str, object], ...]:
    decoded = json.loads(value)
    if (
        not isinstance(decoded, list)
        or any(not isinstance(item, dict) or set(item) != keys for item in decoded)
    ):
        raise ValueError("QA structured context is invalid")
    return tuple(decoded)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
