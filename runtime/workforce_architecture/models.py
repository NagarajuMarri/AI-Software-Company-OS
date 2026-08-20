"""Immutable draft architecture, technology, ADR, and risk models for Day 24."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import re

from runtime.agents import AgentRole
from runtime.digital_twin import EXECUTE_ASSIGNED_WORK, PRODUCE_EXECUTION_EVIDENCE


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")

PROPOSE_SOFTWARE_ARCHITECTURE = "PROPOSE_SOFTWARE_ARCHITECTURE"
RECOMMEND_TECHNOLOGY = "RECOMMEND_TECHNOLOGY"
DRAFT_ARCHITECTURE_DECISIONS = "DRAFT_ARCHITECTURE_DECISIONS"
IDENTIFY_TECHNICAL_RISKS = "IDENTIFY_TECHNICAL_RISKS"
REPORT_ARCHITECTURE_STATUS = "REPORT_ARCHITECTURE_STATUS"

ARCHITECT_CAPABILITY_IDS = (
    "architecture-proposal",
    "technology-selection",
    "adr-drafting",
    "technical-risk-identification",
    "status-reporting",
)
ARCHITECT_ACTION_IDS = (
    EXECUTE_ASSIGNED_WORK,
    PRODUCE_EXECUTION_EVIDENCE,
    PROPOSE_SOFTWARE_ARCHITECTURE,
    RECOMMEND_TECHNOLOGY,
    DRAFT_ARCHITECTURE_DECISIONS,
    IDENTIFY_TECHNICAL_RISKS,
    REPORT_ARCHITECTURE_STATUS,
)

ARTIFACT_STATUS = "DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW"
ADR_STATUS = "PROPOSED"
RECOMMENDATION_STATUS = "PROPOSED"
PILOT_STATUS = "NOT_SELECTED"
WORK_STATUS = "DRAFT_COMPLETE"


class RiskSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskLikelihood(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ArchitectureComponent:
    component_id: str
    name: str
    responsibility: str
    interfaces: tuple[str, ...]
    data_responsibility: str

    def __post_init__(self) -> None:
        _identifier(self.component_id, "architecture component ID")
        _text(self.name, "architecture component name", 160)
        _text(self.responsibility, "architecture component responsibility", 500)
        _items(self.interfaces, "architecture component interfaces", 1, 8, 160)
        _text(self.data_responsibility, "component data responsibility", 300)


@dataclass(frozen=True)
class TechnologyRecommendation:
    recommendation_id: str
    area: str
    technology: str
    rationale: str
    alternatives_considered: tuple[str, ...]
    status: str = RECOMMENDATION_STATUS

    def __post_init__(self) -> None:
        _identifier(self.recommendation_id, "technology recommendation ID")
        _text(self.area, "technology area", 120)
        _text(self.technology, "recommended technology", 200)
        _text(self.rationale, "technology rationale", 500)
        _items(
            self.alternatives_considered,
            "technology alternatives",
            1,
            4,
            160,
        )
        if self.status != RECOMMENDATION_STATUS:
            raise ValueError("Technology recommendation must remain proposed")


@dataclass(frozen=True)
class ArchitectureDecisionDraft:
    adr_id: str
    title: str
    context: str
    decision: str
    consequences: tuple[str, ...]
    status: str = ADR_STATUS
    human_approval_required: bool = True

    def __post_init__(self) -> None:
        _identifier(self.adr_id, "architecture decision ID")
        _text(self.title, "architecture decision title", 200)
        _text(self.context, "architecture decision context", 700)
        _text(self.decision, "architecture decision", 700)
        _items(self.consequences, "architecture decision consequences", 1, 6, 300)
        if self.status != ADR_STATUS or self.human_approval_required is not True:
            raise ValueError("Architecture decisions must remain proposed for human review")


@dataclass(frozen=True)
class TechnicalRisk:
    risk_id: str
    title: str
    severity: RiskSeverity
    likelihood: RiskLikelihood
    impact: str
    mitigation: str
    escalation: str

    def __post_init__(self) -> None:
        _identifier(self.risk_id, "technical risk ID")
        _text(self.title, "technical risk title", 200)
        if not isinstance(self.severity, RiskSeverity) or not isinstance(
            self.likelihood, RiskLikelihood
        ):
            raise ValueError("Technical risk rating is invalid")
        _text(self.impact, "technical risk impact", 500)
        _text(self.mitigation, "technical risk mitigation", 500)
        _text(self.escalation, "technical risk escalation", 300)


@dataclass(frozen=True)
class ArchitectureStatusReport:
    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    human_decisions_required: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("Architecture status must remain draft-complete")
        _items(self.completed_items, "architecture completed items", 1, 8, 300)
        _items(self.next_actions, "architecture next actions", 1, 8, 300)
        _items(self.blockers, "architecture blockers", 1, 8, 300)
        _items(
            self.human_decisions_required,
            "architecture human decisions",
            1,
            8,
            300,
        )


@dataclass(frozen=True)
class ArchitectureProposalArtifact:
    """One validated write-once Software Architect proposal."""

    artifact_id: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    twin_id: str
    business_role: AgentRole
    provider_id: str
    opportunity_digest: str
    product_manager_artifact_digest: str
    title: str
    summary: str
    domain_boundary: str
    principles: tuple[str, ...]
    components: tuple[ArchitectureComponent, ...]
    integration_points: tuple[str, ...]
    data_lifecycle: tuple[str, ...]
    security_controls: tuple[str, ...]
    quality_strategy: tuple[str, ...]
    technology_recommendations: tuple[TechnologyRecommendation, ...]
    adr_drafts: tuple[ArchitectureDecisionDraft, ...]
    technical_risks: tuple[TechnicalRisk, ...]
    status_report: ArchitectureStatusReport
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
            (self.artifact_id, "architecture artifact ID"),
            (self.tenant_id, "architecture tenant ID"),
            (self.opportunity_id, "architecture opportunity ID"),
            (self.execution_id, "architecture execution ID"),
            (self.assignment_id, "architecture assignment ID"),
            (self.twin_id, "architecture Digital Twin ID"),
            (self.provider_id, "architecture provider ID"),
        ):
            _identifier(value, label)
        if self.business_role is not AgentRole.SOFTWARE_ARCHITECT:
            raise ValueError("Architecture artifact requires the Software Architect role")
        for value, label in (
            (self.opportunity_digest, "architecture opportunity digest"),
            (
                self.product_manager_artifact_digest,
                "Product Manager artifact digest",
            ),
            (self.authority_digest, "architecture authority digest"),
            (self.assignment_digest, "architecture assignment digest"),
            (self.request_digest, "architecture provider request digest"),
            (self.output_digest, "architecture provider output digest"),
            (self.receipt_digest, "architecture receipt digest"),
        ):
            _digest(value, label)
        _text(self.title, "architecture proposal title", 240)
        _text(self.summary, "architecture proposal summary", 2_000)
        _text(self.domain_boundary, "architecture domain boundary", 1_000)
        _items(self.principles, "architecture principles", 2, 8, 300)
        _typed_items(
            self.components,
            ArchitectureComponent,
            "architecture components",
            3,
            10,
            lambda item: item.component_id,
        )
        _items(self.integration_points, "architecture integration points", 1, 8, 300)
        _items(self.data_lifecycle, "architecture data lifecycle", 2, 8, 300)
        _items(self.security_controls, "architecture security controls", 2, 8, 300)
        _items(self.quality_strategy, "architecture quality strategy", 2, 8, 300)
        _typed_items(
            self.technology_recommendations,
            TechnologyRecommendation,
            "technology recommendations",
            2,
            8,
            lambda item: item.recommendation_id,
        )
        _typed_items(
            self.adr_drafts,
            ArchitectureDecisionDraft,
            "architecture decision drafts",
            1,
            8,
            lambda item: item.adr_id,
        )
        _typed_items(
            self.technical_risks,
            TechnicalRisk,
            "technical risks",
            1,
            8,
            lambda item: item.risk_id,
        )
        if not isinstance(self.status_report, ArchitectureStatusReport):
            raise ValueError("Architecture status report is invalid")
        _utc(self.generated_at, "architecture generation time")
        if self.status != ARTIFACT_STATUS:
            raise ValueError("Architecture proposal must await human review")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Architecture proposal cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_artifact_record(self))


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "architecture execution ID")
    value = hashlib.sha256(f"architecture-proposal:{execution_id}".encode()).hexdigest()
    return f"architecture-{value[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _artifact_record(value: ArchitectureProposalArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for risk, source in zip(payload["technical_risks"], value.technical_risks, strict=True):
        risk["severity"] = source.severity.value
        risk["likelihood"] = source.likelihood.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} is invalid")


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
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len({item.casefold() for item in values if isinstance(item, str)})
        != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for item in values:
        _text(item, label, item_limit)


def _typed_items(
    values: object,
    expected_type: type,
    label: str,
    minimum: int,
    maximum: int,
    identity,
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or any(not isinstance(item, expected_type) for item in values)
        or len({identity(item) for item in values}) != len(values)
    ):
        raise ValueError(f"{label} are invalid")


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")
