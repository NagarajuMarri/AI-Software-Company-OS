"""Deterministic tool-free provider for the Day 28 DevOps Engineer agent."""

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
from runtime.workforce_devops.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    DEVOPS_ACTIONS,
    DEVOPS_CAPABILITIES,
    DEVOPS_ROLE,
    ENGINEERING_STATUS,
    EXECUTION_STATE,
    PILOT_STATUS,
    PREVIEW_ENVIRONMENT_CLASS,
    QA_STATUS,
    SECURITY_STATUS,
    WORK_STATUS,
)


_CONTEXT_KEYS = {
    "work_order_id", "work_order_digest", "work_order_status", "assignment_title",
    "assignment_objective", "devops_role", "opportunity_id", "opportunity_digest",
    "opportunity_title", "architecture_artifact_id", "architecture_artifact_digest",
    "architecture_status", "engineering_artifact_digests_json", "engineering_sources_json",
    "qa_artifact_id", "qa_execution_id", "qa_artifact_digest", "qa_status",
    "security_artifact_id", "security_execution_id", "security_artifact_digest",
    "security_status", "acceptance_checks_json", "operational_risks_json",
    "constraints_json", "pilot_status",
}
_SOURCE_KEYS = {
    "artifact_digest", "business_role", "interface_contract_ids", "target_component_ids",
    "status", "pilot_status",
}


class DevOpsEngineerProvider:
    """One offline provider implementing the exact zero-tool DevOps profile."""

    requires_live_authorization = False

    def __init__(self, provider_id: str = "deterministic-devops-engineer-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("DevOps provider ID is invalid")
        self.provider_id = provider_id
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return (DEVOPS_ROLE,)

    def supported_capabilities(self) -> tuple[str, ...]:
        return DEVOPS_CAPABILITIES

    def supported_tool_ids(self) -> tuple[str, ...]:
        return ()

    def execute(
        self, request: ProviderExecutionRequest, _tools: DigitalTwinToolGateway
    ) -> ProviderExecutionResult:
        self.execution_count += 1
        return self.render(request)

    def render(self, request: ProviderExecutionRequest) -> ProviderExecutionResult:
        """Rebuild the closed DevOps output for retry/restart reconciliation."""

        if not isinstance(request, ProviderExecutionRequest):
            raise ValueError("DevOps provider request is invalid")
        if not (
            request.provider_id == self.provider_id
            and request.business_role is DEVOPS_ROLE
            and request.required_capability_ids == DEVOPS_CAPABILITIES
            and request.allowed_action_ids == DEVOPS_ACTIONS
            and request.allowed_tool_ids == ()
            and request.max_tool_calls == 0
        ):
            raise ValueError("DevOps provider request profile is invalid")
        context = {item.key: item.value for item in request.context}
        if len(context) != len(request.context) or set(context) != _CONTEXT_KEYS:
            raise ValueError("DevOps provider context is not closed")
        if not (
            context["devops_role"] == DEVOPS_ROLE.value
            and context["work_order_status"] == ASSIGNMENT_STATUS
            and context["architecture_status"] == ARCHITECTURE_STATUS
            and context["qa_status"] == QA_STATUS
            and context["security_status"] == SECURITY_STATUS
            and context["pilot_status"] == PILOT_STATUS
        ):
            raise ValueError("DevOps provider context state is invalid")
        sources = _records(context["engineering_sources_json"], _SOURCE_KEYS)
        digests = _items(context["engineering_artifact_digests_json"], "source digests")
        acceptance = _items(context["acceptance_checks_json"], "acceptance checks")
        risks = _items(context["operational_risks_json"], "operational risks")
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
            and acceptance and risks and constraints
        ):
            raise ValueError("DevOps upstream context is incomplete")
        output = _output(
            context["assignment_title"], sources, context["qa_artifact_digest"],
            context["security_artifact_digest"], acceptance,
        )
        return ProviderExecutionResult(
            execution_id=request.execution_id,
            provider_id=self.provider_id,
            request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary="Bounded DevOps Engineer assignment completed",
            output=tuple(ContextValue(key, value) for key, value in output),
        )


def _output(
    title: str,
    sources: tuple[dict[str, object], ...],
    qa_digest: str,
    security_digest: str,
    acceptance: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    source_digests = tuple(str(item["artifact_digest"]) for item in sources)
    components = tuple(
        dict.fromkeys(
            component
            for item in sources
            for component in _string_list(item["target_component_ids"])
        )
    )
    data = sources[-1]
    ci = {
        "plan_id": "devops-ci-pipeline",
        "source_engineering_artifact_digests": source_digests,
        "qa_artifact_digest": qa_digest,
        "security_artifact_digest": security_digest,
        "stages": (
            "Validate immutable source digests and closed configuration",
            "Run formatting, lint, type, compile, and unit checks",
            "Run integration, browser, and real persistence checks",
            "Evaluate QA and Security evidence gates",
            "Package sanitized immutable evidence only after every gate succeeds",
        ),
        "required_gates": (
            "Exact source, dependency lock, and configuration binding",
            "All QA plans and Security check specifications represented",
            "No critical or high unresolved authorized-workspace findings",
            "Human authorization before any environment mutation",
        ),
        "artifact_requirements": (
            "Commit, source-tree, configuration, tool, and ruleset digests",
            "Test totals, redacted findings, browser screenshot, and failure collections",
            "A manifest that labels every unperformed operation NOT_EXECUTED",
        ),
        "failure_policy": "Fail closed, publish no deployable output, preserve sanitized diagnostics, and require human disposition.",
        "execution_state": EXECUTION_STATE,
    }
    preview = {
        "plan_id": "devops-preview-environment",
        "environment_class": PREVIEW_ENVIRONMENT_CLASS,
        "target_component_ids": components,
        "isolation_controls": (
            "Separate tenant-scoped namespace with no production routes or production data",
            "Least-privilege short-lived identity references supplied only by the authorized workspace",
            "Deny-by-default ingress, egress, persistence, and administrative access",
            "Immutable source and configuration digests attached to all evidence",
        ),
        "configuration_contract": (
            "Non-secret configuration is schema-validated and source controlled",
            "Secret values are referenced by opaque identifiers and never included in artifacts",
            "Synthetic or explicitly approved sanitized datasets only",
        ),
        "secret_reference_policy": "Resolve opaque secret references only inside an authorized executor; never receive, persist, log, or display secret values.",
        "health_checks": (
            "Component readiness, dependency reachability, and schema compatibility",
            "Tenant isolation, bounded provider behavior, and customer-path smoke checks",
            "Telemetry receipt without sensitive values",
        ),
        "lifecycle_steps": (
            "Require human authorization and validate exact source bindings",
            "Provision isolated preview resources using approved infrastructure controls",
            "Run migrations, deployment, checks, and evidence capture in gated order",
            "Expire identities and destroy preview resources after evidence retention",
        ),
        "execution_state": EXECUTION_STATE,
    }
    migration = {
        "plan_id": "devops-migration-plan",
        "data_engineering_artifact_digest": str(data["artifact_digest"]),
        "target_component_ids": _string_list(data["target_component_ids"]),
        "migration_scopes": (
            "Schema and index changes declared by the bounded Data Engineering artifact",
            "Deterministic seed or synthetic fixture changes required by preview verification",
        ),
        "preflight_checks": (
            "Verify exact Data artifact, schema, migration, and backup-policy digests",
            "Reject destructive or irreversible operations without explicit human approval",
            "Confirm preview isolation, capacity, compatibility, and rollback prerequisites",
            "Capture sanitized baseline counts and integrity checks",
        ),
        "apply_steps": (
            "Acquire a preview-only migration lock and record the authorized change identity",
            "Apply ordered idempotent migrations with bounded timeout and stop-on-error behavior",
            "Record sanitized step receipts without connection material",
        ),
        "verification_steps": (
            "Verify schema version, constraints, indexes, and expected synthetic record counts",
            "Run Data and service integration checks against the migrated preview state",
        ),
        "rollback_steps": (
            "Stop application writes and preserve sanitized failure evidence",
            "Run the reviewed reversible migration path or restore the approved preview snapshot",
            "Re-verify schema, data integrity, and service compatibility",
        ),
        "execution_state": EXECUTION_STATE,
    }
    deployment = {
        "plan_id": "devops-deployment-plan",
        "target_environment": PREVIEW_ENVIRONMENT_CLASS,
        "source_engineering_artifact_digests": source_digests,
        "qa_artifact_digest": qa_digest,
        "security_artifact_digest": security_digest,
        "prerequisites": (
            "Explicit human authorization for the exact isolated preview target",
            "Successful CI gates bound to the exact sources, QA, and Security artifacts",
            "Validated secret references, configuration schema, capacity, and rollback readiness",
            "No production route, credential, dataset, or mutation authority",
        ),
        "deployment_steps": (
            "Resolve immutable build outputs and attest their source digests",
            "Apply preview configuration and migration plan through the authorized executor",
            "Deploy components in dependency order with bounded health gates",
            "Run customer-path smoke checks and capture sanitized evidence",
            "Stop promotion and initiate rollback on any failed gate",
        ),
        "approval_gates": (
            "Human approval before preview mutation",
            "Human review before any later promotion beyond preview",
        ),
        "evidence_requirements": (
            "Authorized target identity, source and configuration digests, and step receipts",
            "Health, QA, Security, monitoring, and rollback-readiness results",
        ),
        "success_criteria": (
            "Every component is healthy in the isolated preview with exact source binding",
            "Customer journeys, persistence, tenant isolation, and telemetry checks pass",
            "No secret, credential, production route, or unredacted sensitive value appears in evidence",
        ),
        "execution_state": EXECUTION_STATE,
    }
    monitoring = {
        "plan_id": "devops-monitoring-plan",
        "target_environment": PREVIEW_ENVIRONMENT_CLASS,
        "signals": (
            "Request availability, latency, error rate, saturation, and bounded retries",
            "Database connectivity, migration version, query health, and integrity checks",
            "Provider request outcomes, budget bounds, and zero unauthorized tool calls",
            "Tenant isolation, authorization denials, and security-relevant state changes",
            "Browser journey, console, network failure, and evidence completeness totals",
        ),
        "alert_conditions": (
            "Any failed readiness, customer-path, tenant-isolation, or integrity gate",
            "Unexpected error-rate, latency, resource, retry, or provider-budget threshold",
            "Any unauthorized action, tool call, secret exposure signal, or source-digest drift",
            "Missing, stale, malformed, or non-canonical evidence",
        ),
        "dashboard_requirements": (
            "Preview-only service, persistence, provider, QA, Security, and customer-path panels",
            "Source/configuration digests, deployment identity, freshness, and evidence links",
        ),
        "evidence_requirements": (
            "Sanitized timestamped signal summaries and alert evaluation outcomes",
            "No raw credentials, customer content, prompts, tokens, or secret values",
        ),
        "execution_state": EXECUTION_STATE,
    }
    rollback = {
        "plan_id": "devops-rollback-plan",
        "target_environment": PREVIEW_ENVIRONMENT_CLASS,
        "deployment_plan_id": deployment["plan_id"],
        "migration_plan_id": migration["plan_id"],
        "triggers": (
            "Failed readiness, smoke, QA, Security, tenant-isolation, or integrity gate",
            "Source, configuration, schema, artifact, or evidence digest mismatch",
            "Unexpected error, latency, saturation, authorization, or secret-exposure signal",
        ),
        "rollback_steps": (
            "Stop preview traffic and further mutations while preserving sanitized evidence",
            "Restore the last approved component set and configuration digests",
            "Execute the reviewed preview migration rollback or snapshot restoration path",
            "Re-run health, integrity, isolation, and customer-path verification",
            "Keep the target blocked until a human reviews the incident and evidence",
        ),
        "data_safety_controls": (
            "Preview-only synthetic data and verified backup/restore prerequisites",
            "No destructive production command and no automatic data-loss acceptance",
            "Bounded locks, timeouts, idempotency checks, and sanitized receipts",
        ),
        "verification_steps": (
            "Confirm exact prior source, configuration, schema, and deployment identity",
            "Confirm service health, data integrity, tenant isolation, and alert recovery",
        ),
        "escalation_policy": "Stop and require authorized human disposition for an irreversible migration, unavailable restore point, secret exposure, security control failure, or production impact.",
        "execution_state": EXECUTION_STATE,
    }
    status = {
        "state": WORK_STATUS,
        "completed_items": (
            "Bound exact Architecture, Engineering, QA, and Security source artifacts",
            "Prepared CI, isolated preview, migration, deployment, monitoring, and rollback plans",
            "Kept every operational action at NOT_EXECUTED with zero tools",
        ),
        "next_actions": (
            "Obtain explicit human authorization for an isolated operational workspace",
            "Execute each approved gate with exact source binding and sanitized evidence",
        ),
        "blockers": (
            "No authorized infrastructure workspace, credentials, provider, repository, or network exists in this assignment",
        ),
        "escalations": (
            "Human review is mandatory before any preview mutation, migration, deployment, rollback, promotion, or release",
        ),
    }
    states = {
        "artifact_status": ARTIFACT_STATUS,
        "architecture_status": ARCHITECTURE_STATUS,
        "engineering_status": ENGINEERING_STATUS,
        "qa_status": QA_STATUS,
        "security_status": SECURITY_STATUS,
        "execution_state": EXECUTION_STATE,
        "pilot_status": PILOT_STATUS,
    }
    return (
        ("title", f"{title} — governed DevOps preparation"),
        ("summary", "Prepared six exact-source operational plans without accessing or mutating any workspace, infrastructure, repository, credential, network, deployment, or release target."),
        ("ci_pipeline_json", _json(ci)),
        ("preview_environment_json", _json(preview)),
        ("migration_plan_json", _json(migration)),
        ("deployment_plan_json", _json(deployment)),
        ("monitoring_plan_json", _json(monitoring)),
        ("rollback_plan_json", _json(rollback)),
        ("coverage_requirements_json", _json((
            "All four Engineering roles and exact Architecture, QA, and Security digests",
            "CI, preview, migration, deployment, monitoring, and rollback preparation",
            "Customer-path, persistence, tenant-isolation, security, and evidence gates",
            "Truthful NOT_EXECUTED state for every operational action",
        ))),
        ("handoff_notes_json", _json((
            "Use only an explicitly authorized isolated workspace with least-privilege short-lived references.",
            "Revalidate all source digests and human approval before any operational step.",
            "Do not infer production, release, promotion, pilot, or risk-acceptance authority from this artifact.",
        ))),
        ("status_report_json", _json(status)),
        ("source_states_json", _json(states)),
        ("acceptance_checks_json", _json(acceptance)),
    )


def _records(value: str, keys: set[str]) -> tuple[dict[str, object], ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, dict) or set(item) != keys for item in decoded):
        raise ValueError("DevOps source records are invalid")
    return tuple(decoded)


def _items(value: str, label: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not decoded or any(not isinstance(item, str) or not item for item in decoded):
        raise ValueError(f"DevOps {label} are invalid")
    return tuple(decoded)


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("DevOps source collection is invalid")
    return tuple(value)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
