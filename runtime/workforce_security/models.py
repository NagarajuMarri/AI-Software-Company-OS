"""Immutable source-bound Security Engineer models for ASCOS Day 27."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import re

from runtime.agents import AgentRole
from runtime.digital_twin import EXECUTE_ASSIGNED_WORK, PRODUCE_EXECUTION_EVIDENCE
from runtime.workforce_engineering import ENGINEERING_ROLES


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")

PLAN_SECURITY_ASSIGNMENT = "PLAN_SECURITY_ASSIGNMENT"
MODEL_SECURITY_THREATS = "MODEL_SECURITY_THREATS"
SPECIFY_DEPENDENCY_CHECKS = "SPECIFY_DEPENDENCY_CHECKS"
SPECIFY_SECRET_CHECKS = "SPECIFY_SECRET_CHECKS"
REPORT_SECURITY_FINDINGS = "REPORT_SECURITY_FINDINGS"
REPORT_SECURITY_STATUS = "REPORT_SECURITY_STATUS"

SECURITY_ROLE = AgentRole.SECURITY_ENGINEER
SECURITY_CAPABILITIES = (
    "threat-modeling",
    "dependency-check-specification",
    "secret-check-specification",
    "security-finding-reporting",
    "status-reporting",
)
SECURITY_ACTIONS = (
    EXECUTE_ASSIGNED_WORK,
    PRODUCE_EXECUTION_EVIDENCE,
    PLAN_SECURITY_ASSIGNMENT,
    MODEL_SECURITY_THREATS,
    SPECIFY_DEPENDENCY_CHECKS,
    SPECIFY_SECRET_CHECKS,
    REPORT_SECURITY_FINDINGS,
    REPORT_SECURITY_STATUS,
)

ASSIGNMENT_STATUS = "BOUNDED_SECURITY_ASSIGNMENT"
ARTIFACT_STATUS = "DRAFT_SECURITY_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
ARCHITECTURE_STATUS = "DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW"
ENGINEERING_STATUS = "DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
QA_STATUS = "DRAFT_QA_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
FINDING_STATUS = "DRAFT_FINDING_AWAITING_AUTHORIZED_SECURITY_VALIDATION"
EXECUTION_STATE = "NOT_EXECUTED"
PILOT_STATUS = "NOT_SELECTED"
WORK_STATUS = "BOUNDED_SECURITY_ASSIGNMENT_COMPLETE"


class ThreatCategory(str, Enum):
    SPOOFING = "SPOOFING"
    TAMPERING = "TAMPERING"
    REPUDIATION = "REPUDIATION"
    INFORMATION_DISCLOSURE = "INFORMATION_DISCLOSURE"
    DENIAL_OF_SERVICE = "DENIAL_OF_SERVICE"
    ELEVATION_OF_PRIVILEGE = "ELEVATION_OF_PRIVILEGE"


class DependencyCheckKind(str, Enum):
    MANIFEST_AUDIT = "MANIFEST_AUDIT"
    CLIENT_SUPPLY_CHAIN = "CLIENT_SUPPLY_CHAIN"
    AI_MODEL_PROVENANCE = "AI_MODEL_PROVENANCE"
    DATA_MIGRATION_SUPPLY_CHAIN = "DATA_MIGRATION_SUPPLY_CHAIN"


class SecurityFindingKind(str, Enum):
    THREAT_GAP = "THREAT_GAP"
    DEPENDENCY_RISK = "DEPENDENCY_RISK"
    SECRET_EXPOSURE_RISK = "SECRET_EXPOSURE_RISK"


class SecuritySeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class SecurityWorkOrder:
    """One exact non-executing Security Engineer assignment."""

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
    acceptance_checks: tuple[str, ...]
    security_risks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = ASSIGNMENT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "Security work-order ID"),
            (self.tenant_id, "Security tenant ID"),
            (self.opportunity_id, "Security opportunity ID"),
            (self.assignment_id, "Security assignment ID"),
        ):
            _identifier(value, label)
        if self.business_role is not SECURITY_ROLE:
            raise ValueError("Security work order requires the Security Engineer role")
        _text(self.title, "Security work-order title", 240)
        _text(self.objective, "Security work-order objective", 1_000)
        _digest(self.architecture_artifact_digest, "Security architecture digest")
        _digests(self.engineering_artifact_digests, "Security Engineering sources", 4, 4)
        _digest(self.qa_artifact_digest, "Security QA source digest")
        _items(self.acceptance_checks, "Security acceptance checks", 3, 10, 300)
        _items(self.security_risks, "Security risks", 1, 8, 300)
        _items(self.constraints, "Security constraints", 1, 8, 300)
        _utc(self.issued_at, "Security work-order issue time")
        if self.status != ASSIGNMENT_STATUS:
            raise ValueError("Security work order is not bounded")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Security work order cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_work_order_record(self))


@dataclass(frozen=True)
class SecurityEngineeringSource:
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
        _identifier(self.artifact_id, "Security source artifact ID")
        _identifier(self.execution_id, "Security source execution ID")
        if self.business_role not in ENGINEERING_ROLES:
            raise ValueError("Security source is not an Engineering role")
        _digest(self.artifact_digest, "Security source digest")
        _digest(self.architecture_artifact_digest, "Security source architecture digest")
        _items(self.target_component_ids, "Security source components", 1, 6, 128, identifiers=True)
        _items(self.interface_contract_ids, "Security source interfaces", 1, 5, 128, identifiers=True)
        if self.status != ENGINEERING_STATUS:
            raise ValueError("Security Engineering source status is invalid")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Security Engineering source selected a pilot")


@dataclass(frozen=True)
class SecurityThreat:
    threat_id: str
    category: ThreatCategory
    source_engineering_artifact_digests: tuple[str, ...]
    target_component_ids: tuple[str, ...]
    asset: str
    trust_boundary: str
    scenario: str
    security_properties: tuple[str, ...]
    mitigations: tuple[str, ...]
    residual_risk: str
    validation_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.threat_id, "Security threat ID")
        if not isinstance(self.category, ThreatCategory):
            raise ValueError("Security threat category is invalid")
        _digests(self.source_engineering_artifact_digests, "Security threat sources", 1, 4)
        _items(self.target_component_ids, "Security threat components", 1, 8, 128, identifiers=True)
        _text(self.asset, "Security threat asset", 300)
        _text(self.trust_boundary, "Security trust boundary", 400)
        _text(self.scenario, "Security threat scenario", 800)
        _items(self.security_properties, "Security properties", 1, 6, 200)
        _items(self.mitigations, "Security mitigations", 1, 8, 300)
        _text(self.residual_risk, "Security residual risk", 500)
        if self.validation_state != EXECUTION_STATE:
            raise ValueError("Security threat cannot claim runtime validation")


@dataclass(frozen=True)
class DependencyCheckSpec:
    check_id: str
    kind: DependencyCheckKind
    source_engineering_artifact_digest: str
    target_component_ids: tuple[str, ...]
    manifest_scope: str
    required_checks: tuple[str, ...]
    failure_threshold: SecuritySeverity
    expected_evidence: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.check_id, "Dependency check ID")
        if not isinstance(self.kind, DependencyCheckKind):
            raise ValueError("Dependency check kind is invalid")
        _digest(self.source_engineering_artifact_digest, "Dependency check source")
        _items(self.target_component_ids, "Dependency check components", 1, 6, 128, identifiers=True)
        _text(self.manifest_scope, "Dependency manifest scope", 500)
        _items(self.required_checks, "Dependency required checks", 2, 8, 300)
        if not isinstance(self.failure_threshold, SecuritySeverity):
            raise ValueError("Dependency failure threshold is invalid")
        _items(self.expected_evidence, "Dependency evidence", 2, 8, 250)
        if self.execution_state != EXECUTION_STATE:
            raise ValueError("Dependency check cannot claim execution")


@dataclass(frozen=True)
class SecretCheckSpec:
    check_id: str
    source_engineering_artifact_digest: str
    target_component_ids: tuple[str, ...]
    search_scopes: tuple[str, ...]
    detector_classes: tuple[str, ...]
    allowlist_policy: str
    incident_response: str
    expected_evidence: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.check_id, "Secret check ID")
        _digest(self.source_engineering_artifact_digest, "Secret check source")
        _items(self.target_component_ids, "Secret check components", 1, 6, 128, identifiers=True)
        _items(self.search_scopes, "Secret search scopes", 1, 8, 250)
        _items(self.detector_classes, "Secret detector classes", 2, 10, 200)
        _text(self.allowlist_policy, "Secret allowlist policy", 500)
        _text(self.incident_response, "Secret incident response", 500)
        _items(self.expected_evidence, "Secret check evidence", 2, 8, 250)
        if self.execution_state != EXECUTION_STATE:
            raise ValueError("Secret check cannot claim execution")


@dataclass(frozen=True)
class SecurityFinding:
    finding_id: str
    kind: SecurityFindingKind
    severity: SecuritySeverity
    source_engineering_artifact_digests: tuple[str, ...]
    qa_artifact_digest: str
    title: str
    evidence_basis: str
    risk: str
    recommendation: str
    verification_requirements: tuple[str, ...]
    status: str = FINDING_STATUS

    def __post_init__(self) -> None:
        _identifier(self.finding_id, "Security finding ID")
        if not isinstance(self.kind, SecurityFindingKind):
            raise ValueError("Security finding kind is invalid")
        if not isinstance(self.severity, SecuritySeverity):
            raise ValueError("Security finding severity is invalid")
        _digests(self.source_engineering_artifact_digests, "Security finding sources", 1, 4)
        _digest(self.qa_artifact_digest, "Security finding QA digest")
        _text(self.title, "Security finding title", 240)
        _text(self.evidence_basis, "Security finding evidence basis", 800)
        _text(self.risk, "Security finding risk", 500)
        _text(self.recommendation, "Security finding recommendation", 500)
        _items(self.verification_requirements, "Security verification requirements", 1, 8, 300)
        if self.status != FINDING_STATUS:
            raise ValueError("Security finding must await authorized validation")


@dataclass(frozen=True)
class SecurityStatusReport:
    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("Security status is not bounded-complete")
        _items(self.completed_items, "Security completed items", 1, 8, 300)
        _items(self.next_actions, "Security next actions", 1, 8, 300)
        _items(self.blockers, "Security blockers", 1, 8, 300)
        _items(self.escalations, "Security escalations", 1, 8, 300)


@dataclass(frozen=True)
class SecurityWorkArtifact:
    """One validated, write-once Security planning artifact."""

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
    sources: tuple[SecurityEngineeringSource, ...]
    qa_artifact_id: str
    qa_execution_id: str
    qa_artifact_digest: str
    qa_status: str
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    title: str
    summary: str
    threats: tuple[SecurityThreat, ...]
    dependency_checks: tuple[DependencyCheckSpec, ...]
    secret_checks: tuple[SecretCheckSpec, ...]
    findings: tuple[SecurityFinding, ...]
    acceptance_checks: tuple[str, ...]
    coverage_requirements: tuple[str, ...]
    handoff_notes: tuple[str, ...]
    status_report: SecurityStatusReport
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
            (self.artifact_id, "Security artifact ID"),
            (self.work_order_id, "Security work-order ID"),
            (self.tenant_id, "Security tenant ID"),
            (self.opportunity_id, "Security opportunity ID"),
            (self.execution_id, "Security execution ID"),
            (self.assignment_id, "Security assignment ID"),
            (self.twin_id, "Security Twin ID"),
            (self.provider_id, "Security provider ID"),
            (self.architecture_artifact_id, "Security architecture artifact ID"),
            (self.qa_artifact_id, "Security QA artifact ID"),
            (self.qa_execution_id, "Security QA execution ID"),
        ):
            _identifier(value, label)
        if self.business_role is not SECURITY_ROLE:
            raise ValueError("Security artifact requires the Security Engineer role")
        for value, label in (
            (self.work_order_digest, "Security work-order digest"),
            (self.opportunity_digest, "Security opportunity digest"),
            (self.architecture_artifact_digest, "Security architecture digest"),
            (self.qa_artifact_digest, "Security QA digest"),
            (self.authority_digest, "Security authority digest"),
            (self.assignment_digest, "Security assignment digest"),
            (self.request_digest, "Security request digest"),
            (self.output_digest, "Security output digest"),
            (self.receipt_digest, "Security receipt digest"),
        ):
            _digest(value, label)
        if self.architecture_status != ARCHITECTURE_STATUS or self.qa_status != QA_STATUS:
            raise ValueError("Security source status is invalid")
        _typed_items(self.sources, SecurityEngineeringSource, "Security sources", 4, 4)
        if tuple(item.business_role for item in self.sources) != ENGINEERING_ROLES:
            raise ValueError("Security Engineering source order is invalid")
        if any(item.architecture_artifact_digest != self.architecture_artifact_digest for item in self.sources):
            raise ValueError("Security source architecture binding is invalid")
        if self.capability_ids != SECURITY_CAPABILITIES or self.action_ids != SECURITY_ACTIONS:
            raise ValueError("Security profile is invalid")
        _text(self.title, "Security title", 240)
        _text(self.summary, "Security summary", 2_000)
        _typed_items(self.threats, SecurityThreat, "Security threats", 6, 6)
        if tuple(item.category for item in self.threats) != tuple(ThreatCategory):
            raise ValueError("Security threat category coverage is invalid")
        _typed_items(self.dependency_checks, DependencyCheckSpec, "Dependency checks", 4, 4)
        _typed_items(self.secret_checks, SecretCheckSpec, "Secret checks", 4, 4)
        _typed_items(self.findings, SecurityFinding, "Security findings", 3, 3)
        source_map = {item.artifact_digest: item for item in self.sources}
        ordered_digests = tuple(source_map)
        if len(source_map) != 4:
            raise ValueError("Security source digests are not unique")
        if tuple(item.source_engineering_artifact_digest for item in self.dependency_checks) != ordered_digests:
            raise ValueError("Dependency source coverage is invalid")
        if tuple(item.source_engineering_artifact_digest for item in self.secret_checks) != ordered_digests:
            raise ValueError("Secret source coverage is invalid")
        for check in self.dependency_checks + self.secret_checks:
            source = source_map.get(check.source_engineering_artifact_digest)
            if source is None or not set(check.target_component_ids) <= set(source.target_component_ids):
                raise ValueError("Security check crossed its source boundary")
        for threat in self.threats:
            if not set(threat.source_engineering_artifact_digests) <= set(source_map):
                raise ValueError("Security threat crossed its source boundary")
            allowed = {
                component
                for digest in threat.source_engineering_artifact_digests
                for component in source_map[digest].target_component_ids
            }
            if not set(threat.target_component_ids) <= allowed:
                raise ValueError("Security threat crossed its component boundary")
        for finding in self.findings:
            if not set(finding.source_engineering_artifact_digests) <= set(source_map):
                raise ValueError("Security finding crossed its source boundary")
            if finding.qa_artifact_digest != self.qa_artifact_digest:
                raise ValueError("Security finding crossed its QA boundary")
        _items(self.acceptance_checks, "Security acceptance checks", 3, 10, 300)
        _items(self.coverage_requirements, "Security coverage", 3, 10, 300)
        _items(self.handoff_notes, "Security handoff notes", 1, 8, 300)
        if not isinstance(self.status_report, SecurityStatusReport):
            raise ValueError("Security status report is invalid")
        _utc(self.generated_at, "Security generation time")
        if self.status != ARTIFACT_STATUS:
            raise ValueError("Security output must await an authorized workspace")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Security output cannot select a pilot")

    @property
    def digest(self) -> str:
        return canonical_digest(_artifact_record(self))


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "Security execution ID")
    return f"security-{hashlib.sha256(f'security-work:{execution_id}'.encode()).hexdigest()[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _work_order_record(value: SecurityWorkOrder) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["issued_at"] = value.issued_at.isoformat()
    return payload


def _artifact_record(value: SecurityWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for record, source in zip(payload["sources"], value.sources, strict=True):
        record["business_role"] = source.business_role.value
    for record, threat in zip(payload["threats"], value.threats, strict=True):
        record["category"] = threat.category.value
    for record, check in zip(payload["dependency_checks"], value.dependency_checks, strict=True):
        record["kind"] = check.kind.value
        record["failure_threshold"] = check.failure_threshold.value
    for record, finding in zip(payload["findings"], value.findings, strict=True):
        record["kind"] = finding.kind.value
        record["severity"] = finding.severity.value
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
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
        or "\x7f" in value
    ):
        raise ValueError(f"{label} is invalid")


def _items(
    values: object,
    label: str,
    minimum: int,
    maximum: int,
    item_limit: int,
    *,
    identifiers: bool = False,
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len({item.casefold() for item in values if isinstance(item, str)}) != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for item in values:
        _identifier(item, label) if identifiers else _text(item, label, item_limit)


def _typed_items(values: object, expected_type: type, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or any(not isinstance(item, expected_type) for item in values)
        or len({getattr(item, next(iter(item.__dataclass_fields__))) for item in values}) != len(values)
    ):
        raise ValueError(f"{label} are invalid")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
