"""Immutable role-bound Engineering work models for ASCOS Day 25."""

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

IMPLEMENT_BACKEND_ASSIGNMENT = "IMPLEMENT_BACKEND_ASSIGNMENT"
IMPLEMENT_FRONTEND_ASSIGNMENT = "IMPLEMENT_FRONTEND_ASSIGNMENT"
IMPLEMENT_AI_ASSIGNMENT = "IMPLEMENT_AI_ASSIGNMENT"
IMPLEMENT_DATA_ASSIGNMENT = "IMPLEMENT_DATA_ASSIGNMENT"
REPORT_ENGINEERING_STATUS = "REPORT_ENGINEERING_STATUS"

ENGINEERING_ROLES = (
    AgentRole.BACKEND_ENGINEER,
    AgentRole.FRONTEND_ENGINEER,
    AgentRole.AI_ENGINEER,
    AgentRole.DATA_ENGINEER,
)

_CAPABILITIES = {
    AgentRole.BACKEND_ENGINEER: (
        "backend-service-implementation",
        "domain-workflow-implementation",
        "backend-contract-definition",
        "status-reporting",
    ),
    AgentRole.FRONTEND_ENGINEER: (
        "frontend-interface-implementation",
        "interaction-behavior-implementation",
        "accessibility-responsive-implementation",
        "status-reporting",
    ),
    AgentRole.AI_ENGINEER: (
        "ai-system-implementation",
        "ai-evaluation-contract",
        "ai-reliability-controls",
        "status-reporting",
    ),
    AgentRole.DATA_ENGINEER: (
        "data-model-implementation",
        "schema-evolution-planning",
        "data-integrity-controls",
        "status-reporting",
    ),
}

_ROLE_ACTION = {
    AgentRole.BACKEND_ENGINEER: IMPLEMENT_BACKEND_ASSIGNMENT,
    AgentRole.FRONTEND_ENGINEER: IMPLEMENT_FRONTEND_ASSIGNMENT,
    AgentRole.AI_ENGINEER: IMPLEMENT_AI_ASSIGNMENT,
    AgentRole.DATA_ENGINEER: IMPLEMENT_DATA_ASSIGNMENT,
}

ASSIGNMENT_STATUS = "BOUNDED_ENGINEERING_ASSIGNMENT"
ARTIFACT_STATUS = "DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE"
ARCHITECTURE_STATUS = "DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW"
PILOT_STATUS = "NOT_SELECTED"
WORK_STATUS = "BOUNDED_ASSIGNMENT_COMPLETE"


class EngineeringDiscipline(str, Enum):
    BACKEND = "BACKEND"
    FRONTEND = "FRONTEND"
    AI = "AI"
    DATA = "DATA"


class EngineeringChangeKind(str, Enum):
    SERVICE_LOGIC = "SERVICE_LOGIC"
    USER_EXPERIENCE = "USER_EXPERIENCE"
    AI_SYSTEM = "AI_SYSTEM"
    DATA_MODEL = "DATA_MODEL"


class EngineeringContractKind(str, Enum):
    SERVICE_INTERFACE = "SERVICE_INTERFACE"
    USER_INTERFACE = "USER_INTERFACE"
    AI_INTERFACE = "AI_INTERFACE"
    DATA_INTERFACE = "DATA_INTERFACE"


_DISCIPLINE = {
    AgentRole.BACKEND_ENGINEER: EngineeringDiscipline.BACKEND,
    AgentRole.FRONTEND_ENGINEER: EngineeringDiscipline.FRONTEND,
    AgentRole.AI_ENGINEER: EngineeringDiscipline.AI,
    AgentRole.DATA_ENGINEER: EngineeringDiscipline.DATA,
}

_CHANGE_KIND = {
    AgentRole.BACKEND_ENGINEER: EngineeringChangeKind.SERVICE_LOGIC,
    AgentRole.FRONTEND_ENGINEER: EngineeringChangeKind.USER_EXPERIENCE,
    AgentRole.AI_ENGINEER: EngineeringChangeKind.AI_SYSTEM,
    AgentRole.DATA_ENGINEER: EngineeringChangeKind.DATA_MODEL,
}

_CONTRACT_KIND = {
    AgentRole.BACKEND_ENGINEER: EngineeringContractKind.SERVICE_INTERFACE,
    AgentRole.FRONTEND_ENGINEER: EngineeringContractKind.USER_INTERFACE,
    AgentRole.AI_ENGINEER: EngineeringContractKind.AI_INTERFACE,
    AgentRole.DATA_ENGINEER: EngineeringContractKind.DATA_INTERFACE,
}


def capability_ids_for(role: AgentRole) -> tuple[str, ...]:
    """Return the exact ordered Day 25 capability profile for one role."""

    try:
        return _CAPABILITIES[role]
    except (KeyError, TypeError) as error:
        raise ValueError("Engineering Business Role is not supported") from error


def action_ids_for(role: AgentRole) -> tuple[str, ...]:
    """Return the exact ordered Day 25 delegated-action profile for one role."""

    try:
        role_action = _ROLE_ACTION[role]
    except (KeyError, TypeError) as error:
        raise ValueError("Engineering Business Role is not supported") from error
    return (
        EXECUTE_ASSIGNED_WORK,
        PRODUCE_EXECUTION_EVIDENCE,
        role_action,
        REPORT_ENGINEERING_STATUS,
    )


def discipline_for(role: AgentRole) -> EngineeringDiscipline:
    try:
        return _DISCIPLINE[role]
    except (KeyError, TypeError) as error:
        raise ValueError("Engineering Business Role is not supported") from error


def change_kind_for(role: AgentRole) -> EngineeringChangeKind:
    try:
        return _CHANGE_KIND[role]
    except (KeyError, TypeError) as error:
        raise ValueError("Engineering Business Role is not supported") from error


def contract_kind_for(role: AgentRole) -> EngineeringContractKind:
    try:
        return _CONTRACT_KIND[role]
    except (KeyError, TypeError) as error:
        raise ValueError("Engineering Business Role is not supported") from error


@dataclass(frozen=True)
class EngineeringWorkOrder:
    """One exact non-repository Engineering assignment."""

    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    business_role: AgentRole
    title: str
    objective: str
    architecture_artifact_digest: str
    target_component_ids: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = ASSIGNMENT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "Engineering work-order ID"),
            (self.tenant_id, "Engineering work-order tenant ID"),
            (self.opportunity_id, "Engineering work-order opportunity ID"),
            (self.assignment_id, "Engineering work-order assignment ID"),
        ):
            _identifier(value, label)
        capability_ids_for(self.business_role)
        _text(self.title, "Engineering work-order title", 240)
        _text(self.objective, "Engineering work-order objective", 1_000)
        _digest(self.architecture_artifact_digest, "Engineering architecture digest")
        _items(
            self.target_component_ids,
            "Engineering target components",
            1,
            6,
            128,
            identifiers=True,
        )
        _items(self.acceptance_checks, "Engineering acceptance checks", 1, 8, 300)
        _items(self.constraints, "Engineering constraints", 1, 8, 300)
        _utc(self.issued_at, "Engineering work-order issue time")
        if self.status != ASSIGNMENT_STATUS:
            raise ValueError("Engineering work order is not bounded")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Engineering work order cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_work_order_record(self))


@dataclass(frozen=True)
class EngineeringImplementationItem:
    item_id: str
    discipline: EngineeringDiscipline
    target_component_id: str
    change_kind: EngineeringChangeKind
    implementation: str
    expected_outcome: str

    def __post_init__(self) -> None:
        _identifier(self.item_id, "Engineering implementation item ID")
        if not isinstance(self.discipline, EngineeringDiscipline):
            raise ValueError("Engineering implementation discipline is invalid")
        _identifier(self.target_component_id, "Engineering target component ID")
        if not isinstance(self.change_kind, EngineeringChangeKind):
            raise ValueError("Engineering change kind is invalid")
        _text(self.implementation, "Engineering implementation detail", 700)
        _text(self.expected_outcome, "Engineering expected outcome", 500)


@dataclass(frozen=True)
class EngineeringInterfaceContract:
    contract_id: str
    kind: EngineeringContractKind
    name: str
    producer: str
    consumer: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    failure_behavior: str

    def __post_init__(self) -> None:
        _identifier(self.contract_id, "Engineering interface-contract ID")
        if not isinstance(self.kind, EngineeringContractKind):
            raise ValueError("Engineering interface-contract kind is invalid")
        _text(self.name, "Engineering interface-contract name", 200)
        _text(self.producer, "Engineering interface producer", 160)
        _text(self.consumer, "Engineering interface consumer", 160)
        _items(self.inputs, "Engineering interface inputs", 1, 8, 200)
        _items(self.outputs, "Engineering interface outputs", 1, 8, 200)
        _text(self.failure_behavior, "Engineering interface failure behavior", 500)


@dataclass(frozen=True)
class EngineeringStatusReport:
    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("Engineering status is not bounded-complete")
        _items(self.completed_items, "Engineering completed items", 1, 8, 300)
        _items(self.next_actions, "Engineering next actions", 1, 8, 300)
        _items(self.blockers, "Engineering blockers", 1, 8, 300)
        _items(self.escalations, "Engineering escalations", 1, 8, 300)


@dataclass(frozen=True)
class EngineeringWorkArtifact:
    """One validated, write-once role-specific Engineering execution artifact."""

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
    target_component_ids: tuple[str, ...]
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    title: str
    summary: str
    implementation_items: tuple[EngineeringImplementationItem, ...]
    interface_contracts: tuple[EngineeringInterfaceContract, ...]
    acceptance_checks: tuple[str, ...]
    validation_checks: tuple[str, ...]
    handoff_notes: tuple[str, ...]
    status_report: EngineeringStatusReport
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
            (self.artifact_id, "Engineering artifact ID"),
            (self.work_order_id, "Engineering work-order ID"),
            (self.tenant_id, "Engineering tenant ID"),
            (self.opportunity_id, "Engineering opportunity ID"),
            (self.execution_id, "Engineering execution ID"),
            (self.assignment_id, "Engineering assignment ID"),
            (self.twin_id, "Engineering Digital Twin ID"),
            (self.provider_id, "Engineering provider ID"),
            (self.architecture_artifact_id, "Engineering architecture artifact ID"),
        ):
            _identifier(value, label)
        expected_capabilities = capability_ids_for(self.business_role)
        expected_actions = action_ids_for(self.business_role)
        expected_discipline = discipline_for(self.business_role)
        expected_change_kind = change_kind_for(self.business_role)
        expected_contract_kind = contract_kind_for(self.business_role)
        for value, label in (
            (self.work_order_digest, "Engineering work-order digest"),
            (self.opportunity_digest, "Engineering opportunity digest"),
            (self.architecture_artifact_digest, "Engineering architecture digest"),
            (self.authority_digest, "Engineering authority digest"),
            (self.assignment_digest, "Engineering assignment digest"),
            (self.request_digest, "Engineering provider-request digest"),
            (self.output_digest, "Engineering provider-output digest"),
            (self.receipt_digest, "Engineering receipt digest"),
        ):
            _digest(value, label)
        if self.architecture_status != ARCHITECTURE_STATUS:
            raise ValueError("Engineering source architecture status is invalid")
        _items(
            self.target_component_ids,
            "Engineering target components",
            1,
            6,
            128,
            identifiers=True,
        )
        if self.capability_ids != expected_capabilities:
            raise ValueError("Engineering artifact capability profile is invalid")
        if self.action_ids != expected_actions:
            raise ValueError("Engineering artifact action profile is invalid")
        _text(self.title, "Engineering artifact title", 240)
        _text(self.summary, "Engineering artifact summary", 2_000)
        _typed_items(
            self.implementation_items,
            EngineeringImplementationItem,
            "Engineering implementation items",
            2,
            8,
            lambda item: item.item_id,
        )
        if any(
            item.discipline is not expected_discipline
            or item.change_kind is not expected_change_kind
            or item.target_component_id not in self.target_component_ids
            for item in self.implementation_items
        ):
            raise ValueError("Engineering implementation item crossed its role boundary")
        _typed_items(
            self.interface_contracts,
            EngineeringInterfaceContract,
            "Engineering interface contracts",
            1,
            5,
            lambda item: item.contract_id,
        )
        if any(item.kind is not expected_contract_kind for item in self.interface_contracts):
            raise ValueError("Engineering interface contract crossed its role boundary")
        _items(self.acceptance_checks, "Engineering acceptance checks", 1, 8, 300)
        _items(self.validation_checks, "Engineering validation checks", 2, 8, 300)
        _items(self.handoff_notes, "Engineering handoff notes", 1, 8, 300)
        if not isinstance(self.status_report, EngineeringStatusReport):
            raise ValueError("Engineering status report is invalid")
        _utc(self.generated_at, "Engineering generation time")
        if self.status != ARTIFACT_STATUS:
            raise ValueError("Engineering output must await an authorized workspace")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Engineering output cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_artifact_record(self))


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "Engineering execution ID")
    value = hashlib.sha256(f"engineering-work:{execution_id}".encode()).hexdigest()
    return f"engineering-{value[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _work_order_record(value: EngineeringWorkOrder) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["issued_at"] = value.issued_at.isoformat()
    return payload


def _artifact_record(value: EngineeringWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for item, source in zip(
        payload["implementation_items"], value.implementation_items, strict=True
    ):
        item["discipline"] = source.discipline.value
        item["change_kind"] = source.change_kind.value
    for contract, contract_source in zip(
        payload["interface_contracts"], value.interface_contracts, strict=True
    ):
        contract["kind"] = contract_source.kind.value
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
