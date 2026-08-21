"""Immutable source-bound Documentation Engineer models for ASCOS Day 29."""

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

PLAN_DOCUMENTATION_ASSIGNMENT = "PLAN_DOCUMENTATION_ASSIGNMENT"
DRAFT_TECHNICAL_DOCUMENTATION = "DRAFT_TECHNICAL_DOCUMENTATION"
DRAFT_USER_DOCUMENTATION = "DRAFT_USER_DOCUMENTATION"
DRAFT_API_DOCUMENTATION = "DRAFT_API_DOCUMENTATION"
DRAFT_OPERATIONS_DOCUMENTATION = "DRAFT_OPERATIONS_DOCUMENTATION"
DRAFT_RELEASE_DOCUMENTATION = "DRAFT_RELEASE_DOCUMENTATION"
PREPARE_CUSTOMER_HANDOFF = "PREPARE_CUSTOMER_HANDOFF"
VALIDATE_DOCUMENTATION_SOURCES = "VALIDATE_DOCUMENTATION_SOURCES"
REPORT_DOCUMENTATION_STATUS = "REPORT_DOCUMENTATION_STATUS"

DOCUMENTATION_ROLE = AgentRole.DOCUMENTATION_ENGINEER
DOCUMENTATION_CAPABILITIES = (
    "technical-documentation", "user-documentation", "api-documentation",
    "operations-documentation", "release-documentation", "customer-handoff",
    "documentation-validation", "status-reporting",
)
DOCUMENTATION_ACTIONS = (
    EXECUTE_ASSIGNED_WORK, PRODUCE_EXECUTION_EVIDENCE, PLAN_DOCUMENTATION_ASSIGNMENT,
    DRAFT_TECHNICAL_DOCUMENTATION, DRAFT_USER_DOCUMENTATION, DRAFT_API_DOCUMENTATION,
    DRAFT_OPERATIONS_DOCUMENTATION, DRAFT_RELEASE_DOCUMENTATION, PREPARE_CUSTOMER_HANDOFF,
    VALIDATE_DOCUMENTATION_SOURCES, REPORT_DOCUMENTATION_STATUS,
)

ASSIGNMENT_STATUS = "BOUNDED_DOCUMENTATION_ASSIGNMENT"
ARTIFACT_STATUS = "DRAFT_DOCUMENTATION_OUTPUT_AWAITING_HUMAN_REVIEW"
ARCHITECTURE_STATUS = "DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW"
ENGINEERING_STATUS = "DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
QA_STATUS = "DRAFT_QA_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
SECURITY_STATUS = "DRAFT_SECURITY_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
DEVOPS_STATUS = "DRAFT_DEVOPS_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
DOCUMENT_STATUS = "DRAFT_SOURCE_VALIDATED_AWAITING_HUMAN_REVIEW"
VALIDATION_STATE = "VALIDATED_AGAINST_EXACT_SOURCES"
PUBLICATION_STATE = "NOT_PUBLISHED"
PILOT_STATUS = "NOT_SELECTED"
WORK_STATUS = "BOUNDED_DOCUMENTATION_ASSIGNMENT_COMPLETE"


class DocumentationKind(str, Enum):
    TECHNICAL = "TECHNICAL"
    USER = "USER"
    API = "API"
    OPERATIONS = "OPERATIONS"
    RELEASE = "RELEASE"


@dataclass(frozen=True)
class DocumentationWorkOrder:
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
    devops_artifact_digest: str
    acceptance_checks: tuple[str, ...]
    documentation_risks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = ASSIGNMENT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in ((self.work_order_id, "work-order"), (self.tenant_id, "tenant"),
                             (self.opportunity_id, "opportunity"), (self.assignment_id, "assignment")):
            _identifier(value, f"Documentation {label} ID")
        if self.business_role is not DOCUMENTATION_ROLE:
            raise ValueError("Documentation work order requires the Documentation Engineer role")
        _text(self.title, "Documentation work-order title", 240)
        _text(self.objective, "Documentation work-order objective", 1_000)
        _digest(self.architecture_artifact_digest, "Documentation architecture digest")
        _digests(self.engineering_artifact_digests, "Documentation Engineering sources", 4, 4)
        for value, label in ((self.qa_artifact_digest, "QA"), (self.security_artifact_digest, "Security"),
                             (self.devops_artifact_digest, "DevOps")):
            _digest(value, f"Documentation {label} source digest")
        _items(self.acceptance_checks, "Documentation acceptance checks", 3, 10, 300)
        _items(self.documentation_risks, "Documentation risks", 1, 8, 300)
        _items(self.constraints, "Documentation constraints", 1, 8, 300)
        _utc(self.issued_at, "Documentation work-order issue time")
        if self.status != ASSIGNMENT_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Documentation work order state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["business_role"] = self.business_role.value
        payload["issued_at"] = self.issued_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class DocumentationEngineeringSource:
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
        _identifier(self.artifact_id, "Documentation source artifact ID")
        _identifier(self.execution_id, "Documentation source execution ID")
        if self.business_role not in ENGINEERING_ROLES:
            raise ValueError("Documentation source is not an Engineering role")
        _digest(self.artifact_digest, "Documentation source digest")
        _digest(self.architecture_artifact_digest, "Documentation source architecture digest")
        _items(self.target_component_ids, "Documentation source components", 1, 8, 128, identifiers=True)
        _items(self.interface_contract_ids, "Documentation source interfaces", 1, 8, 128, identifiers=True)
        if self.status != ENGINEERING_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Documentation Engineering source state is invalid")


@dataclass(frozen=True)
class DocumentationSection:
    section_id: str
    heading: str
    content: str

    def __post_init__(self) -> None:
        _identifier(self.section_id, "Documentation section ID")
        _text(self.heading, "Documentation section heading", 180)
        _text(self.content, "Documentation section content", 2_000)


@dataclass(frozen=True)
class DocumentationRecord:
    document_id: str
    kind: DocumentationKind
    title: str
    audience: tuple[str, ...]
    purpose: str
    source_artifact_digests: tuple[str, ...]
    sections: tuple[DocumentationSection, ...]
    validation_checks: tuple[str, ...]
    validation_state: str = VALIDATION_STATE
    publication_state: str = PUBLICATION_STATE
    status: str = DOCUMENT_STATUS

    def __post_init__(self) -> None:
        _identifier(self.document_id, "Documentation document ID")
        if not isinstance(self.kind, DocumentationKind):
            raise ValueError("Documentation kind is invalid")
        _text(self.title, "Documentation title", 240)
        _items(self.audience, "Documentation audience", 1, 5, 120)
        _text(self.purpose, "Documentation purpose", 500)
        _digests(self.source_artifact_digests, "Documentation record sources", 2, 8)
        _typed_items(self.sections, DocumentationSection, "Documentation sections", 3, 8)
        _items(self.validation_checks, "Documentation validation checks", 3, 8, 300)
        if self.validation_state != VALIDATION_STATE:
            raise ValueError("Documentation cannot claim unsupported validation")
        if self.publication_state != PUBLICATION_STATE:
            raise ValueError("Documentation cannot claim publication")
        if self.status != DOCUMENT_STATUS:
            raise ValueError("Documentation must remain draft")


@dataclass(frozen=True)
class CustomerHandoff:
    handoff_id: str
    audience: tuple[str, ...]
    readiness_summary: str
    deliverable_document_ids: tuple[str, ...]
    review_checklist: tuple[str, ...]
    known_limitations: tuple[str, ...]
    next_actions: tuple[str, ...]
    publication_state: str = PUBLICATION_STATE

    def __post_init__(self) -> None:
        _identifier(self.handoff_id, "Customer handoff ID")
        _items(self.audience, "Customer handoff audience", 1, 5, 120)
        _text(self.readiness_summary, "Customer handoff readiness", 800)
        _items(self.deliverable_document_ids, "Customer handoff documents", 5, 5, 128, identifiers=True)
        _items(self.review_checklist, "Customer handoff checklist", 3, 10, 300)
        _items(self.known_limitations, "Customer handoff limitations", 1, 8, 300)
        _items(self.next_actions, "Customer handoff next actions", 1, 8, 300)
        if self.publication_state != PUBLICATION_STATE:
            raise ValueError("Customer handoff cannot claim publication")


@dataclass(frozen=True)
class DocumentationStatusReport:
    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("Documentation status is invalid")
        for values, label in ((self.completed_items, "completed items"), (self.next_actions, "next actions"),
                              (self.blockers, "blockers"), (self.escalations, "escalations")):
            _items(values, f"Documentation {label}", 1, 8, 300)


@dataclass(frozen=True)
class DocumentationWorkArtifact:
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
    sources: tuple[DocumentationEngineeringSource, ...]
    qa_artifact_id: str
    qa_artifact_digest: str
    qa_status: str
    security_artifact_id: str
    security_artifact_digest: str
    security_status: str
    devops_artifact_id: str
    devops_artifact_digest: str
    devops_status: str
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    title: str
    summary: str
    documents: tuple[DocumentationRecord, ...]
    customer_handoff: CustomerHandoff
    acceptance_checks: tuple[str, ...]
    coverage_requirements: tuple[str, ...]
    status_report: DocumentationStatusReport
    authority_digest: str
    assignment_digest: str
    request_digest: str
    output_digest: str
    receipt_digest: str
    generated_at: datetime
    status: str = ARTIFACT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in ((self.artifact_id, "artifact"), (self.work_order_id, "work-order"),
                             (self.tenant_id, "tenant"), (self.opportunity_id, "opportunity"),
                             (self.execution_id, "execution"), (self.assignment_id, "assignment"),
                             (self.twin_id, "Twin"), (self.provider_id, "provider"),
                             (self.architecture_artifact_id, "architecture"), (self.qa_artifact_id, "QA"),
                             (self.security_artifact_id, "Security"), (self.devops_artifact_id, "DevOps")):
            _identifier(value, f"Documentation {label} ID")
        if self.business_role is not DOCUMENTATION_ROLE:
            raise ValueError("Documentation artifact requires the Documentation Engineer role")
        for value, label in ((self.work_order_digest, "work order"), (self.opportunity_digest, "opportunity"),
                             (self.architecture_artifact_digest, "architecture"), (self.qa_artifact_digest, "QA"),
                             (self.security_artifact_digest, "Security"), (self.devops_artifact_digest, "DevOps"),
                             (self.authority_digest, "authority"), (self.assignment_digest, "assignment"),
                             (self.request_digest, "request"), (self.output_digest, "output"),
                             (self.receipt_digest, "receipt")):
            _digest(value, f"Documentation {label} digest")
        if (self.architecture_status, self.qa_status, self.security_status, self.devops_status) != (
            ARCHITECTURE_STATUS, QA_STATUS, SECURITY_STATUS, DEVOPS_STATUS
        ):
            raise ValueError("Documentation upstream state is invalid")
        _typed_items(self.sources, DocumentationEngineeringSource, "Documentation sources", 4, 4)
        if tuple(item.business_role for item in self.sources) != ENGINEERING_ROLES:
            raise ValueError("Documentation Engineering source order is invalid")
        if any(item.architecture_artifact_digest != self.architecture_artifact_digest for item in self.sources):
            raise ValueError("Documentation source architecture binding is invalid")
        if self.capability_ids != DOCUMENTATION_CAPABILITIES or self.action_ids != DOCUMENTATION_ACTIONS:
            raise ValueError("Documentation profile is invalid")
        _text(self.title, "Documentation artifact title", 240)
        _text(self.summary, "Documentation artifact summary", 2_000)
        _typed_items(self.documents, DocumentationRecord, "Documentation records", 5, 5)
        if tuple(item.kind for item in self.documents) != tuple(DocumentationKind):
            raise ValueError("Documentation kind coverage is invalid")
        allowed = {self.architecture_artifact_digest, self.qa_artifact_digest,
                   self.security_artifact_digest, self.devops_artifact_digest,
                   *(item.artifact_digest for item in self.sources)}
        if any(not set(item.source_artifact_digests) <= allowed for item in self.documents):
            raise ValueError("Documentation crossed its source boundary")
        if not isinstance(self.customer_handoff, CustomerHandoff):
            raise ValueError("Customer handoff is invalid")
        if self.customer_handoff.deliverable_document_ids != tuple(item.document_id for item in self.documents):
            raise ValueError("Customer handoff document coverage is invalid")
        _items(self.acceptance_checks, "Documentation acceptance checks", 3, 10, 300)
        _items(self.coverage_requirements, "Documentation coverage", 3, 10, 300)
        if not isinstance(self.status_report, DocumentationStatusReport):
            raise ValueError("Documentation status report is invalid")
        _utc(self.generated_at, "Documentation generation time")
        if self.status != ARTIFACT_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Documentation artifact or pilot state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["business_role"] = self.business_role.value
        for record, source in zip(payload["sources"], self.sources, strict=True):
            record["business_role"] = source.business_role.value
        for record, document in zip(payload["documents"], self.documents, strict=True):
            record["kind"] = document.kind.value
        payload["generated_at"] = self.generated_at.isoformat()
        return canonical_digest(payload)


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "Documentation execution ID")
    return f"documentation-{hashlib.sha256(f'documentation-work:{execution_id}'.encode()).hexdigest()[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


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
    if not isinstance(value, str) or value != value.strip() or not value or len(value) > maximum or any(
        ord(character) < 32 and character not in "\n\t" for character in value
    ) or "\x7f" in value:
        raise ValueError(f"{label} is invalid")


def _items(values: object, label: str, minimum: int, maximum: int, item_limit: int, *, identifiers: bool = False) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum or len(
        {item.casefold() for item in values if isinstance(item, str)}
    ) != len(values):
        raise ValueError(f"{label} are invalid")
    for item in values:
        _identifier(item, label) if identifiers else _text(item, label, item_limit)


def _typed_items(values: object, expected_type: type, label: str, minimum: int, maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum or any(
        not isinstance(item, expected_type) for item in values
    ):
        raise ValueError(f"{label} are invalid")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
