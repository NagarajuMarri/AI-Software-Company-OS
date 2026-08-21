"""Immutable source-bound DevOps Engineer models for ASCOS Day 28."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re

from runtime.agents import AgentRole
from runtime.digital_twin import EXECUTE_ASSIGNED_WORK, PRODUCE_EXECUTION_EVIDENCE
from runtime.workforce_engineering import ENGINEERING_ROLES


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")

PLAN_DEVOPS_ASSIGNMENT = "PLAN_DEVOPS_ASSIGNMENT"
PLAN_CI_PIPELINE = "PLAN_CI_PIPELINE"
PLAN_PREVIEW_ENVIRONMENT = "PLAN_PREVIEW_ENVIRONMENT"
PLAN_MIGRATIONS = "PLAN_MIGRATIONS"
PLAN_DEPLOYMENT = "PLAN_DEPLOYMENT"
PLAN_MONITORING = "PLAN_MONITORING"
PLAN_ROLLBACK = "PLAN_ROLLBACK"
REPORT_DEVOPS_STATUS = "REPORT_DEVOPS_STATUS"

DEVOPS_ROLE = AgentRole.DEVOPS_ENGINEER
DEVOPS_CAPABILITIES = (
    "ci-pipeline-planning",
    "preview-environment-planning",
    "migration-planning",
    "deployment-planning",
    "monitoring-planning",
    "rollback-planning",
    "status-reporting",
)
DEVOPS_ACTIONS = (
    EXECUTE_ASSIGNED_WORK,
    PRODUCE_EXECUTION_EVIDENCE,
    PLAN_DEVOPS_ASSIGNMENT,
    PLAN_CI_PIPELINE,
    PLAN_PREVIEW_ENVIRONMENT,
    PLAN_MIGRATIONS,
    PLAN_DEPLOYMENT,
    PLAN_MONITORING,
    PLAN_ROLLBACK,
    REPORT_DEVOPS_STATUS,
)

ASSIGNMENT_STATUS = "BOUNDED_DEVOPS_ASSIGNMENT"
ARTIFACT_STATUS = "DRAFT_DEVOPS_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
ARCHITECTURE_STATUS = "DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW"
ENGINEERING_STATUS = "DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
QA_STATUS = "DRAFT_QA_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
SECURITY_STATUS = "DRAFT_SECURITY_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
EXECUTION_STATE = "NOT_EXECUTED"
PILOT_STATUS = "NOT_SELECTED"
WORK_STATUS = "BOUNDED_DEVOPS_ASSIGNMENT_COMPLETE"
PREVIEW_ENVIRONMENT_CLASS = "ISOLATED_NON_PRODUCTION_PREVIEW"


@dataclass(frozen=True)
class DevOpsWorkOrder:
    """One exact, non-executing DevOps Engineer assignment."""

    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    business_role: AgentRole
    title: str
    objective: str
    architecture_artifact_digest: str
    engineering_artifact_digests: tuple[str, ...]
    qa_artifact_digest: str
    security_artifact_digest: str
    acceptance_checks: tuple[str, ...]
    operational_risks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = ASSIGNMENT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "DevOps work-order ID"),
            (self.tenant_id, "DevOps tenant ID"),
            (self.opportunity_id, "DevOps opportunity ID"),
            (self.assignment_id, "DevOps assignment ID"),
        ):
            _identifier(value, label)
        if self.business_role is not DEVOPS_ROLE:
            raise ValueError("DevOps work order requires the DevOps Engineer role")
        _text(self.title, "DevOps work-order title", 240)
        _text(self.objective, "DevOps work-order objective", 1_000)
        _digest(self.architecture_artifact_digest, "DevOps architecture digest")
        _digests(self.engineering_artifact_digests, "DevOps Engineering sources", 4, 4)
        _digest(self.qa_artifact_digest, "DevOps QA source digest")
        _digest(self.security_artifact_digest, "DevOps Security source digest")
        _items(self.acceptance_checks, "DevOps acceptance checks", 3, 10, 300)
        _items(self.operational_risks, "DevOps operational risks", 1, 8, 300)
        _items(self.constraints, "DevOps constraints", 1, 8, 300)
        _utc(self.issued_at, "DevOps work-order issue time")
        if self.status != ASSIGNMENT_STATUS:
            raise ValueError("DevOps work order is not bounded")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("DevOps work order cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_work_order_record(self))


@dataclass(frozen=True)
class DevOpsEngineeringSource:
    artifact_id: str
    execution_id: str
    business_role: AgentRole
    artifact_digest: str
    architecture_artifact_digest: str
    target_component_ids: tuple[str, ...]
    interface_contract_ids: tuple[str, ...]
    status: str = ENGINEERING_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "DevOps source artifact ID")
        _identifier(self.execution_id, "DevOps source execution ID")
        if self.business_role not in ENGINEERING_ROLES:
            raise ValueError("DevOps source is not an Engineering role")
        _digest(self.artifact_digest, "DevOps source digest")
        _digest(self.architecture_artifact_digest, "DevOps source architecture digest")
        _items(self.target_component_ids, "DevOps source components", 1, 6, 128, identifiers=True)
        _items(self.interface_contract_ids, "DevOps source interfaces", 1, 5, 128, identifiers=True)
        if self.status != ENGINEERING_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("DevOps Engineering source state is invalid")


@dataclass(frozen=True)
class CIPipelinePlan:
    plan_id: str
    source_engineering_artifact_digests: tuple[str, ...]
    qa_artifact_digest: str
    security_artifact_digest: str
    stages: tuple[str, ...]
    required_gates: tuple[str, ...]
    artifact_requirements: tuple[str, ...]
    failure_policy: str
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.plan_id, "CI plan ID")
        _digests(self.source_engineering_artifact_digests, "CI sources", 4, 4)
        _digest(self.qa_artifact_digest, "CI QA digest")
        _digest(self.security_artifact_digest, "CI Security digest")
        _items(self.stages, "CI stages", 4, 10, 200)
        _items(self.required_gates, "CI gates", 3, 10, 300)
        _items(self.artifact_requirements, "CI evidence", 2, 8, 300)
        _text(self.failure_policy, "CI failure policy", 500)
        _not_executed(self.execution_state, "CI pipeline")


@dataclass(frozen=True)
class PreviewEnvironmentPlan:
    plan_id: str
    environment_class: str
    target_component_ids: tuple[str, ...]
    isolation_controls: tuple[str, ...]
    configuration_contract: tuple[str, ...]
    secret_reference_policy: str
    health_checks: tuple[str, ...]
    lifecycle_steps: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.plan_id, "Preview plan ID")
        if self.environment_class != PREVIEW_ENVIRONMENT_CLASS:
            raise ValueError("Preview plan cannot target a live environment")
        _items(self.target_component_ids, "Preview components", 1, 20, 128, identifiers=True)
        _items(self.isolation_controls, "Preview isolation controls", 3, 10, 300)
        _items(self.configuration_contract, "Preview configuration", 2, 8, 300)
        _text(self.secret_reference_policy, "Preview secret policy", 500)
        _items(self.health_checks, "Preview health checks", 2, 8, 300)
        _items(self.lifecycle_steps, "Preview lifecycle", 3, 10, 300)
        _not_executed(self.execution_state, "Preview environment")


@dataclass(frozen=True)
class MigrationPlan:
    plan_id: str
    data_engineering_artifact_digest: str
    target_component_ids: tuple[str, ...]
    migration_scopes: tuple[str, ...]
    preflight_checks: tuple[str, ...]
    apply_steps: tuple[str, ...]
    verification_steps: tuple[str, ...]
    rollback_steps: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.plan_id, "Migration plan ID")
        _digest(self.data_engineering_artifact_digest, "Migration Data source")
        _items(self.target_component_ids, "Migration components", 1, 6, 128, identifiers=True)
        _items(self.migration_scopes, "Migration scopes", 1, 6, 300)
        _items(self.preflight_checks, "Migration preflight checks", 3, 10, 300)
        _items(self.apply_steps, "Migration apply steps", 2, 10, 300)
        _items(self.verification_steps, "Migration verification", 2, 10, 300)
        _items(self.rollback_steps, "Migration rollback", 2, 10, 300)
        _not_executed(self.execution_state, "Migration")


@dataclass(frozen=True)
class DeploymentPlan:
    plan_id: str
    target_environment: str
    source_engineering_artifact_digests: tuple[str, ...]
    qa_artifact_digest: str
    security_artifact_digest: str
    prerequisites: tuple[str, ...]
    deployment_steps: tuple[str, ...]
    approval_gates: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    success_criteria: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.plan_id, "Deployment plan ID")
        if self.target_environment != PREVIEW_ENVIRONMENT_CLASS:
            raise ValueError("Deployment plan cannot target production")
        _digests(self.source_engineering_artifact_digests, "Deployment sources", 4, 4)
        _digest(self.qa_artifact_digest, "Deployment QA digest")
        _digest(self.security_artifact_digest, "Deployment Security digest")
        _items(self.prerequisites, "Deployment prerequisites", 3, 10, 300)
        _items(self.deployment_steps, "Deployment steps", 3, 12, 300)
        _items(self.approval_gates, "Deployment gates", 2, 8, 300)
        _items(self.evidence_requirements, "Deployment evidence", 2, 8, 300)
        _items(self.success_criteria, "Deployment success criteria", 2, 8, 300)
        _not_executed(self.execution_state, "Deployment")


@dataclass(frozen=True)
class MonitoringPlan:
    plan_id: str
    target_environment: str
    signals: tuple[str, ...]
    alert_conditions: tuple[str, ...]
    dashboard_requirements: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.plan_id, "Monitoring plan ID")
        if self.target_environment != PREVIEW_ENVIRONMENT_CLASS:
            raise ValueError("Monitoring plan cannot target production")
        _items(self.signals, "Monitoring signals", 4, 12, 300)
        _items(self.alert_conditions, "Monitoring alerts", 3, 10, 300)
        _items(self.dashboard_requirements, "Monitoring dashboards", 2, 8, 300)
        _items(self.evidence_requirements, "Monitoring evidence", 2, 8, 300)
        _not_executed(self.execution_state, "Monitoring")


@dataclass(frozen=True)
class RollbackPlan:
    plan_id: str
    target_environment: str
    deployment_plan_id: str
    migration_plan_id: str
    triggers: tuple[str, ...]
    rollback_steps: tuple[str, ...]
    data_safety_controls: tuple[str, ...]
    verification_steps: tuple[str, ...]
    escalation_policy: str
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        for value, label in (
            (self.plan_id, "Rollback plan ID"),
            (self.deployment_plan_id, "Rollback deployment plan ID"),
            (self.migration_plan_id, "Rollback migration plan ID"),
        ):
            _identifier(value, label)
        if self.target_environment != PREVIEW_ENVIRONMENT_CLASS:
            raise ValueError("Rollback plan cannot target production")
        _items(self.triggers, "Rollback triggers", 3, 10, 300)
        _items(self.rollback_steps, "Rollback steps", 3, 12, 300)
        _items(self.data_safety_controls, "Rollback data controls", 2, 8, 300)
        _items(self.verification_steps, "Rollback verification", 2, 8, 300)
        _text(self.escalation_policy, "Rollback escalation policy", 500)
        _not_executed(self.execution_state, "Rollback")


@dataclass(frozen=True)
class DevOpsStatusReport:
    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("DevOps status is not bounded-complete")
        _items(self.completed_items, "DevOps completed items", 1, 8, 300)
        _items(self.next_actions, "DevOps next actions", 1, 8, 300)
        _items(self.blockers, "DevOps blockers", 1, 8, 300)
        _items(self.escalations, "DevOps escalations", 1, 8, 300)


@dataclass(frozen=True)
class DevOpsWorkArtifact:
    """One validated, write-once DevOps preparation artifact."""

    artifact_id: str
    work_order_id: str
    work_order_digest: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    twin_id: str
    business_role: AgentRole
    provider_id: str
    opportunity_digest: str
    architecture_artifact_id: str
    architecture_artifact_digest: str
    architecture_status: str
    sources: tuple[DevOpsEngineeringSource, ...]
    qa_artifact_id: str
    qa_execution_id: str
    qa_artifact_digest: str
    qa_status: str
    security_artifact_id: str
    security_execution_id: str
    security_artifact_digest: str
    security_status: str
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    title: str
    summary: str
    ci_pipeline: CIPipelinePlan
    preview_environment: PreviewEnvironmentPlan
    migration_plan: MigrationPlan
    deployment_plan: DeploymentPlan
    monitoring_plan: MonitoringPlan
    rollback_plan: RollbackPlan
    acceptance_checks: tuple[str, ...]
    coverage_requirements: tuple[str, ...]
    handoff_notes: tuple[str, ...]
    status_report: DevOpsStatusReport
    authority_digest: str
    assignment_digest: str
    request_digest: str
    output_digest: str
    receipt_digest: str
    generated_at: datetime
    status: str = ARTIFACT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.artifact_id, "DevOps artifact ID"), (self.work_order_id, "DevOps work-order ID"),
            (self.tenant_id, "DevOps tenant ID"), (self.opportunity_id, "DevOps opportunity ID"),
            (self.execution_id, "DevOps execution ID"), (self.assignment_id, "DevOps assignment ID"),
            (self.twin_id, "DevOps Twin ID"), (self.provider_id, "DevOps provider ID"),
            (self.architecture_artifact_id, "DevOps architecture ID"),
            (self.qa_artifact_id, "DevOps QA ID"), (self.qa_execution_id, "DevOps QA execution ID"),
            (self.security_artifact_id, "DevOps Security ID"),
            (self.security_execution_id, "DevOps Security execution ID"),
        ):
            _identifier(value, label)
        if self.business_role is not DEVOPS_ROLE:
            raise ValueError("DevOps artifact requires the DevOps Engineer role")
        for value, label in (
            (self.work_order_digest, "work order"), (self.opportunity_digest, "opportunity"),
            (self.architecture_artifact_digest, "architecture"), (self.qa_artifact_digest, "QA"),
            (self.security_artifact_digest, "Security"), (self.authority_digest, "authority"),
            (self.assignment_digest, "assignment"), (self.request_digest, "request"),
            (self.output_digest, "output"), (self.receipt_digest, "receipt"),
        ):
            _digest(value, f"DevOps {label} digest")
        if not (
            self.architecture_status == ARCHITECTURE_STATUS
            and self.qa_status == QA_STATUS
            and self.security_status == SECURITY_STATUS
        ):
            raise ValueError("DevOps upstream source state is invalid")
        _typed_items(self.sources, DevOpsEngineeringSource, "DevOps sources", 4, 4)
        if tuple(item.business_role for item in self.sources) != ENGINEERING_ROLES:
            raise ValueError("DevOps Engineering source order is invalid")
        source_digests = tuple(item.artifact_digest for item in self.sources)
        if len(set(source_digests)) != 4 or any(
            item.architecture_artifact_digest != self.architecture_artifact_digest for item in self.sources
        ):
            raise ValueError("DevOps Engineering binding is invalid")
        if self.capability_ids != DEVOPS_CAPABILITIES or self.action_ids != DEVOPS_ACTIONS:
            raise ValueError("DevOps profile is invalid")
        _text(self.title, "DevOps title", 240)
        _text(self.summary, "DevOps summary", 2_000)
        for plan, expected, label in (
            (self.ci_pipeline, CIPipelinePlan, "CI plan"),
            (self.preview_environment, PreviewEnvironmentPlan, "preview plan"),
            (self.migration_plan, MigrationPlan, "migration plan"),
            (self.deployment_plan, DeploymentPlan, "deployment plan"),
            (self.monitoring_plan, MonitoringPlan, "monitoring plan"),
            (self.rollback_plan, RollbackPlan, "rollback plan"),
        ):
            if not isinstance(plan, expected):
                raise ValueError(f"DevOps {label} is invalid")
        if not (
            self.ci_pipeline.source_engineering_artifact_digests == source_digests
            == self.deployment_plan.source_engineering_artifact_digests
            and self.ci_pipeline.qa_artifact_digest == self.qa_artifact_digest
            == self.deployment_plan.qa_artifact_digest
            and self.ci_pipeline.security_artifact_digest == self.security_artifact_digest
            == self.deployment_plan.security_artifact_digest
            and self.migration_plan.data_engineering_artifact_digest == source_digests[-1]
            and self.rollback_plan.deployment_plan_id == self.deployment_plan.plan_id
            and self.rollback_plan.migration_plan_id == self.migration_plan.plan_id
        ):
            raise ValueError("DevOps plan source binding is invalid")
        allowed_components = {component for item in self.sources for component in item.target_component_ids}
        if not set(self.preview_environment.target_component_ids) <= allowed_components:
            raise ValueError("Preview plan crossed its component boundary")
        data_components = set(self.sources[-1].target_component_ids)
        if not set(self.migration_plan.target_component_ids) <= data_components:
            raise ValueError("Migration plan crossed the Data source boundary")
        _items(self.acceptance_checks, "DevOps acceptance checks", 3, 10, 300)
        _items(self.coverage_requirements, "DevOps coverage", 3, 10, 300)
        _items(self.handoff_notes, "DevOps handoff notes", 1, 8, 300)
        if not isinstance(self.status_report, DevOpsStatusReport):
            raise ValueError("DevOps status report is invalid")
        _utc(self.generated_at, "DevOps generation time")
        if self.status != ARTIFACT_STATUS:
            raise ValueError("DevOps output must await an authorized workspace")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("DevOps output cannot select a pilot")

    @property
    def digest(self) -> str:
        return canonical_digest(_artifact_record(self))


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "DevOps execution ID")
    return f"devops-{hashlib.sha256(f'devops-work:{execution_id}'.encode()).hexdigest()[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _work_order_record(value: DevOpsWorkOrder) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["issued_at"] = value.issued_at.isoformat()
    return payload


def _artifact_record(value: DevOpsWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for record, source in zip(payload["sources"], value.sources, strict=True):
        record["business_role"] = source.business_role.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digests(values: object, label: str, minimum: int, maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum or len(set(values)) != len(values):
        raise ValueError(f"{label} are invalid")
    for item in values:
        _digest(item, label)


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str) or value != value.strip() or not value or len(value) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
        or "\x7f" in value
    ):
        raise ValueError(f"{label} is invalid")


def _items(values: object, label: str, minimum: int, maximum: int, item_limit: int, *, identifiers: bool = False) -> None:
    if (
        not isinstance(values, tuple) or not minimum <= len(values) <= maximum
        or len({item.casefold() for item in values if isinstance(item, str)}) != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for item in values:
        _identifier(item, label) if identifiers else _text(item, label, item_limit)


def _typed_items(values: object, expected_type: type, label: str, minimum: int, maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum or any(
        not isinstance(item, expected_type) for item in values
    ):
        raise ValueError(f"{label} are invalid")


def _not_executed(value: object, label: str) -> None:
    if value != EXECUTION_STATE:
        raise ValueError(f"{label} cannot claim execution")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
