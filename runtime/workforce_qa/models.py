"""Immutable source-bound QA work models for ASCOS Day 26."""

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

PLAN_QA_ASSIGNMENT = "PLAN_QA_ASSIGNMENT"
SPECIFY_AUTOMATED_TESTS = "SPECIFY_AUTOMATED_TESTS"
SPECIFY_INTEGRATION_TESTS = "SPECIFY_INTEGRATION_TESTS"
REPORT_QA_DEFECTS = "REPORT_QA_DEFECTS"
REPORT_QA_STATUS = "REPORT_QA_STATUS"

QA_ROLE = AgentRole.QA_ENGINEER
QA_CAPABILITIES = (
    "test-strategy-planning",
    "automated-test-specification",
    "integration-test-design",
    "defect-reporting",
    "status-reporting",
)
QA_ACTIONS = (
    EXECUTE_ASSIGNED_WORK,
    PRODUCE_EXECUTION_EVIDENCE,
    PLAN_QA_ASSIGNMENT,
    SPECIFY_AUTOMATED_TESTS,
    SPECIFY_INTEGRATION_TESTS,
    REPORT_QA_DEFECTS,
    REPORT_QA_STATUS,
)

ASSIGNMENT_STATUS = "BOUNDED_QA_ASSIGNMENT"
ARTIFACT_STATUS = "DRAFT_QA_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
ARCHITECTURE_STATUS = "DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW"
ENGINEERING_STATUS = "DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
DEFECT_STATUS = "DRAFT_DEFECT_AWAITING_AUTHORIZED_TEST_EXECUTION"
EXECUTION_STATE = "NOT_EXECUTED"
PILOT_STATUS = "NOT_SELECTED"
WORK_STATUS = "BOUNDED_QA_ASSIGNMENT_COMPLETE"


class QATestLevel(str, Enum):
    UNIT = "UNIT"
    CONTRACT = "CONTRACT"
    INTEGRATION = "INTEGRATION"
    END_TO_END = "END_TO_END"


class QAAutomationKind(str, Enum):
    UNIT = "UNIT"
    CONTRACT = "CONTRACT"
    PROPERTY = "PROPERTY"


class QADefectKind(str, Enum):
    SPECIFICATION_GAP = "SPECIFICATION_GAP"
    INTEGRATION_RISK = "INTEGRATION_RISK"


class QADefectSeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class QAWorkOrder:
    """One exact non-executing QA assignment."""

    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    business_role: AgentRole
    title: str
    objective: str
    architecture_artifact_digest: str
    engineering_artifact_digests: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    quality_risks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = ASSIGNMENT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "QA work-order ID"),
            (self.tenant_id, "QA work-order tenant ID"),
            (self.opportunity_id, "QA work-order opportunity ID"),
            (self.assignment_id, "QA work-order assignment ID"),
        ):
            _identifier(value, label)
        if self.business_role is not QA_ROLE:
            raise ValueError("QA work order requires the QA Engineer role")
        _text(self.title, "QA work-order title", 240)
        _text(self.objective, "QA work-order objective", 1_000)
        _digest(self.architecture_artifact_digest, "QA architecture digest")
        _digests(self.engineering_artifact_digests, "QA Engineering sources", 4, 4)
        _items(self.acceptance_checks, "QA acceptance checks", 2, 10, 300)
        _items(self.quality_risks, "QA quality risks", 1, 8, 300)
        _items(self.constraints, "QA constraints", 1, 8, 300)
        _utc(self.issued_at, "QA work-order issue time")
        if self.status != ASSIGNMENT_STATUS:
            raise ValueError("QA work order is not bounded")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("QA work order cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_work_order_record(self))


@dataclass(frozen=True)
class QAEngineeringSource:
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
        _identifier(self.artifact_id, "QA source artifact ID")
        _identifier(self.execution_id, "QA source execution ID")
        if self.business_role not in ENGINEERING_ROLES:
            raise ValueError("QA source Business Role is not an Engineering role")
        _digest(self.artifact_digest, "QA source artifact digest")
        _digest(self.architecture_artifact_digest, "QA source architecture digest")
        _items(
            self.target_component_ids,
            "QA source target components",
            1,
            6,
            128,
            identifiers=True,
        )
        _items(
            self.interface_contract_ids,
            "QA source interface contracts",
            1,
            5,
            128,
            identifiers=True,
        )
        if self.status != ENGINEERING_STATUS:
            raise ValueError("QA Engineering source status is invalid")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("QA Engineering source selected a pilot product")


@dataclass(frozen=True)
class QATestPlanItem:
    item_id: str
    level: QATestLevel
    source_engineering_artifact_digest: str
    target_component_ids: tuple[str, ...]
    objective: str
    preconditions: tuple[str, ...]
    expected_outcome: str

    def __post_init__(self) -> None:
        _identifier(self.item_id, "QA test-plan item ID")
        if not isinstance(self.level, QATestLevel):
            raise ValueError("QA test level is invalid")
        _digest(self.source_engineering_artifact_digest, "QA test-plan source digest")
        _items(
            self.target_component_ids,
            "QA test-plan target components",
            1,
            6,
            128,
            identifiers=True,
        )
        _text(self.objective, "QA test-plan objective", 700)
        _items(self.preconditions, "QA test-plan preconditions", 1, 8, 250)
        _text(self.expected_outcome, "QA test-plan expected outcome", 500)


@dataclass(frozen=True)
class QAAutomatedTestSpec:
    spec_id: str
    kind: QAAutomationKind
    source_engineering_artifact_digest: str
    target_component_id: str
    scenario: str
    fixture: str
    assertions: tuple[str, ...]
    negative_cases: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.spec_id, "QA automated-test specification ID")
        if not isinstance(self.kind, QAAutomationKind):
            raise ValueError("QA automation kind is invalid")
        _digest(self.source_engineering_artifact_digest, "QA automated-test source digest")
        _identifier(self.target_component_id, "QA automated-test target component")
        _text(self.scenario, "QA automated-test scenario", 700)
        _text(self.fixture, "QA automated-test fixture", 500)
        _items(self.assertions, "QA automated-test assertions", 2, 8, 250)
        _items(self.negative_cases, "QA automated-test negative cases", 1, 8, 250)
        if self.execution_state != EXECUTION_STATE:
            raise ValueError("QA automated-test specification cannot claim execution")


@dataclass(frozen=True)
class QAIntegrationTestSpec:
    spec_id: str
    source_engineering_artifact_digests: tuple[str, ...]
    interface_contract_ids: tuple[str, ...]
    scenario: str
    preconditions: tuple[str, ...]
    steps: tuple[str, ...]
    expected_outcome: str
    failure_behavior: str
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.spec_id, "QA integration-test specification ID")
        _digests(
            self.source_engineering_artifact_digests,
            "QA integration-test sources",
            2,
            4,
        )
        _items(
            self.interface_contract_ids,
            "QA integration-test interface contracts",
            2,
            6,
            128,
            identifiers=True,
        )
        _text(self.scenario, "QA integration-test scenario", 700)
        _items(self.preconditions, "QA integration-test preconditions", 1, 8, 250)
        _items(self.steps, "QA integration-test steps", 2, 10, 250)
        _text(self.expected_outcome, "QA integration-test expected outcome", 500)
        _text(self.failure_behavior, "QA integration-test failure behavior", 500)
        if self.execution_state != EXECUTION_STATE:
            raise ValueError("QA integration-test specification cannot claim execution")


@dataclass(frozen=True)
class QADefectReport:
    defect_id: str
    kind: QADefectKind
    severity: QADefectSeverity
    source_engineering_artifact_digest: str
    title: str
    evidence_basis: str
    expected_behavior: str
    observed_risk: str
    reproduction_conditions: tuple[str, ...]
    status: str = DEFECT_STATUS

    def __post_init__(self) -> None:
        _identifier(self.defect_id, "QA defect ID")
        if not isinstance(self.kind, QADefectKind):
            raise ValueError("QA defect kind is invalid")
        if not isinstance(self.severity, QADefectSeverity):
            raise ValueError("QA defect severity is invalid")
        _digest(self.source_engineering_artifact_digest, "QA defect source digest")
        _text(self.title, "QA defect title", 240)
        _text(self.evidence_basis, "QA defect evidence basis", 700)
        _text(self.expected_behavior, "QA defect expected behavior", 500)
        _text(self.observed_risk, "QA defect observed risk", 500)
        _items(self.reproduction_conditions, "QA defect reproduction conditions", 1, 8, 250)
        if self.status != DEFECT_STATUS:
            raise ValueError("QA defect must await authorized test execution")


@dataclass(frozen=True)
class QAStatusReport:
    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("QA status is not bounded-complete")
        _items(self.completed_items, "QA completed items", 1, 8, 300)
        _items(self.next_actions, "QA next actions", 1, 8, 300)
        _items(self.blockers, "QA blockers", 1, 8, 300)
        _items(self.escalations, "QA escalations", 1, 8, 300)


@dataclass(frozen=True)
class QAWorkArtifact:
    """One validated, write-once QA planning artifact."""

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
    sources: tuple[QAEngineeringSource, ...]
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    title: str
    summary: str
    test_plan_items: tuple[QATestPlanItem, ...]
    automated_test_specs: tuple[QAAutomatedTestSpec, ...]
    integration_test_specs: tuple[QAIntegrationTestSpec, ...]
    defect_reports: tuple[QADefectReport, ...]
    acceptance_checks: tuple[str, ...]
    coverage_requirements: tuple[str, ...]
    handoff_notes: tuple[str, ...]
    status_report: QAStatusReport
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
            (self.artifact_id, "QA artifact ID"),
            (self.work_order_id, "QA work-order ID"),
            (self.tenant_id, "QA tenant ID"),
            (self.opportunity_id, "QA opportunity ID"),
            (self.execution_id, "QA execution ID"),
            (self.assignment_id, "QA assignment ID"),
            (self.twin_id, "QA Digital Twin ID"),
            (self.provider_id, "QA provider ID"),
            (self.architecture_artifact_id, "QA architecture artifact ID"),
        ):
            _identifier(value, label)
        if self.business_role is not QA_ROLE:
            raise ValueError("QA artifact requires the QA Engineer role")
        for value, label in (
            (self.work_order_digest, "QA work-order digest"),
            (self.opportunity_digest, "QA opportunity digest"),
            (self.architecture_artifact_digest, "QA architecture digest"),
            (self.authority_digest, "QA authority digest"),
            (self.assignment_digest, "QA assignment digest"),
            (self.request_digest, "QA provider-request digest"),
            (self.output_digest, "QA provider-output digest"),
            (self.receipt_digest, "QA receipt digest"),
        ):
            _digest(value, label)
        if self.architecture_status != ARCHITECTURE_STATUS:
            raise ValueError("QA source architecture status is invalid")
        _typed_items(self.sources, QAEngineeringSource, "QA Engineering sources", 4, 4)
        if tuple(source.business_role for source in self.sources) != ENGINEERING_ROLES:
            raise ValueError("QA Engineering source role order is invalid")
        if any(
            source.architecture_artifact_digest != self.architecture_artifact_digest
            for source in self.sources
        ):
            raise ValueError("QA Engineering sources crossed architecture boundaries")
        if self.capability_ids != QA_CAPABILITIES:
            raise ValueError("QA artifact capability profile is invalid")
        if self.action_ids != QA_ACTIONS:
            raise ValueError("QA artifact action profile is invalid")
        _text(self.title, "QA artifact title", 240)
        _text(self.summary, "QA artifact summary", 2_000)
        _typed_items(self.test_plan_items, QATestPlanItem, "QA test-plan items", 4, 4)
        _typed_items(
            self.automated_test_specs,
            QAAutomatedTestSpec,
            "QA automated-test specifications",
            4,
            4,
        )
        _typed_items(
            self.integration_test_specs,
            QAIntegrationTestSpec,
            "QA integration-test specifications",
            2,
            2,
        )
        _typed_items(self.defect_reports, QADefectReport, "QA defect reports", 2, 2)
        source_map = {source.artifact_digest: source for source in self.sources}
        source_digests = tuple(source_map)
        if len(source_map) != len(self.sources):
            raise ValueError("QA Engineering source digests are not unique")
        if tuple(
            item.source_engineering_artifact_digest for item in self.test_plan_items
        ) != source_digests:
            raise ValueError("QA test-plan source coverage is invalid")
        if tuple(
            item.source_engineering_artifact_digest
            for item in self.automated_test_specs
        ) != source_digests:
            raise ValueError("QA automated-test source coverage is invalid")
        for plan_item in self.test_plan_items:
            plan_source = source_map.get(plan_item.source_engineering_artifact_digest)
            if plan_source is None or not set(plan_item.target_component_ids) <= set(
                plan_source.target_component_ids
            ):
                raise ValueError("QA test-plan item crossed its source boundary")
        for automated_spec in self.automated_test_specs:
            automated_source = source_map.get(
                automated_spec.source_engineering_artifact_digest
            )
            if (
                automated_source is None
                or automated_spec.target_component_id
                not in automated_source.target_component_ids
            ):
                raise ValueError("QA automated-test specification crossed its source boundary")
        for integration_spec in self.integration_test_specs:
            integration_source_digests = set(
                integration_spec.source_engineering_artifact_digests
            )
            if not integration_source_digests <= set(source_map):
                raise ValueError("QA integration-test specification crossed its source boundary")
            allowed_interfaces = {
                interface_id
                for source_digest in integration_source_digests
                for interface_id in source_map[source_digest].interface_contract_ids
            }
            if not set(integration_spec.interface_contract_ids) <= allowed_interfaces:
                raise ValueError("QA integration-test specification crossed its source boundary")
        if any(
            item.source_engineering_artifact_digest not in source_map
            for item in self.defect_reports
        ):
            raise ValueError("QA defect report crossed its source boundary")
        _items(self.acceptance_checks, "QA acceptance checks", 2, 10, 300)
        _items(self.coverage_requirements, "QA coverage requirements", 2, 10, 300)
        _items(self.handoff_notes, "QA handoff notes", 1, 8, 300)
        if not isinstance(self.status_report, QAStatusReport):
            raise ValueError("QA status report is invalid")
        _utc(self.generated_at, "QA generation time")
        if self.status != ARTIFACT_STATUS:
            raise ValueError("QA output must await an authorized workspace")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("QA output cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_artifact_record(self))


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "QA execution ID")
    value = hashlib.sha256(f"qa-work:{execution_id}".encode()).hexdigest()
    return f"qa-{value[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _work_order_record(value: QAWorkOrder) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["issued_at"] = value.issued_at.isoformat()
    return payload


def _artifact_record(value: QAWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for source_record, engineering_source in zip(
        payload["sources"], value.sources, strict=True
    ):
        source_record["business_role"] = engineering_source.business_role.value
    for plan_record, plan_item in zip(
        payload["test_plan_items"], value.test_plan_items, strict=True
    ):
        plan_record["level"] = plan_item.level.value
    for automation_record, automated_spec in zip(
        payload["automated_test_specs"], value.automated_test_specs, strict=True
    ):
        automation_record["kind"] = automated_spec.kind.value
    for defect_record, defect in zip(
        payload["defect_reports"], value.defect_reports, strict=True
    ):
        defect_record["kind"] = defect.kind.value
        defect_record["severity"] = defect.severity.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digests(values: object, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len(set(values)) != len(values)
    ):
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
        or len({item.casefold() for item in values if isinstance(item, str)})
        != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for item in values:
        if identifiers:
            _identifier(item, label)
        else:
            _text(item, label, item_limit)


def _typed_items(
    values: object,
    expected_type: type,
    label: str,
    minimum: int,
    maximum: int,
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or any(not isinstance(item, expected_type) for item in values)
        or len({getattr(item, next(iter(item.__dataclass_fields__))) for item in values})
        != len(values)
    ):
        raise ValueError(f"{label} are invalid")


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")
