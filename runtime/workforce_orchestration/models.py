"""Immutable exact-source-bound models for ASCOS Day 30 orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ACTION = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")

PLAN_DEPENDENCIES = "PLAN_DEPENDENCIES"
PLAN_PARALLEL_WORK = "PLAN_PARALLEL_WORK"
SHARE_BOUNDED_CONTEXT = "SHARE_BOUNDED_CONTEXT"
PREPARE_HANDOFFS = "PREPARE_HANDOFFS"
ROUTE_CONFLICTS = "ROUTE_CONFLICTS"
RECORD_ESCALATIONS = "RECORD_ESCALATIONS"
REPORT_ORCHESTRATION_STATUS = "REPORT_ORCHESTRATION_STATUS"

ORCHESTRATION_ACTIONS = (
    PLAN_DEPENDENCIES,
    PLAN_PARALLEL_WORK,
    SHARE_BOUNDED_CONTEXT,
    PREPARE_HANDOFFS,
    ROUTE_CONFLICTS,
    RECORD_ESCALATIONS,
    REPORT_ORCHESTRATION_STATUS,
)
ORCHESTRATION_CAPABILITIES = (
    "dependency-planning",
    "parallel-work-planning",
    "bounded-context-sharing",
    "handoff-coordination",
    "conflict-routing",
    "human-escalation",
    "orchestration-status-reporting",
)

WORK_ORDER_STATUS = "BOUNDED_MULTI_AGENT_ORCHESTRATION_ASSIGNMENT"
ARTIFACT_STATUS = "DRAFT_ORCHESTRATION_PLAN_AWAITING_HUMAN_AUTHORIZATION"
WORK_STATUS = "BOUNDED_ORCHESTRATION_PLAN_COMPLETE"
EXECUTION_STATE = "PLAN_ONLY_NOT_EXECUTED"
HANDOFF_STATE = "DRAFT_HANDOFF_NOT_DISPATCHED"
CONFLICT_STATE = "DRAFT_CONFLICT_POLICY_NOT_INVOKED"
ESCALATION_STATE = "PENDING_ONLY_IF_TRIGGERED"
PILOT_STATUS = "NOT_SELECTED"


class OrchestrationSourceKind(str, Enum):
    CEO = "CEO"
    PRODUCT_MANAGER = "PRODUCT_MANAGER"
    ARCHITECTURE = "ARCHITECTURE"
    BACKEND_ENGINEERING = "BACKEND_ENGINEERING"
    FRONTEND_ENGINEERING = "FRONTEND_ENGINEERING"
    AI_ENGINEERING = "AI_ENGINEERING"
    DATA_ENGINEERING = "DATA_ENGINEERING"
    QA = "QA"
    SECURITY = "SECURITY"
    DEVOPS = "DEVOPS"
    DOCUMENTATION = "DOCUMENTATION"


SOURCE_ORDER = tuple(OrchestrationSourceKind)


@dataclass(frozen=True)
class OrchestrationWorkOrder:
    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    leadership_artifact_digests: tuple[str, ...]
    architecture_artifact_digest: str
    engineering_artifact_digests: tuple[str, ...]
    qa_artifact_digest: str
    security_artifact_digest: str
    devops_artifact_digest: str
    documentation_artifact_digest: str
    objectives: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = WORK_ORDER_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.assignment_id, "assignment"),
        ):
            _identifier(value, f"Orchestration {label} ID")
        _digests(self.leadership_artifact_digests, "leadership sources", 2, 2)
        _digest(self.architecture_artifact_digest, "architecture source")
        _digests(self.engineering_artifact_digests, "Engineering sources", 4, 4)
        for value, label in (
            (self.qa_artifact_digest, "QA source"),
            (self.security_artifact_digest, "Security source"),
            (self.devops_artifact_digest, "DevOps source"),
            (self.documentation_artifact_digest, "Documentation source"),
        ):
            _digest(value, label)
        _items(self.objectives, "objectives", 6, 10, 300)
        _items(self.acceptance_checks, "acceptance checks", 6, 12, 300)
        _items(self.constraints, "constraints", 2, 10, 300)
        _utc(self.issued_at, "work-order issue time")
        if self.status != WORK_ORDER_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Orchestration work-order state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class OrchestrationAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    work_order_digest: str
    source_set_digest: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_parallel_workstreams: int
    max_tool_calls: int = 0
    live_provider_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
        ):
            _identifier(value, f"Orchestration {label} ID")
        _digest(self.work_order_digest, "authority work-order digest")
        _digest(self.source_set_digest, "authority source-set digest")
        _actions(self.allowed_action_ids)
        if self.allowed_action_ids != ORCHESTRATION_ACTIONS:
            raise ValueError("Orchestration authority action profile is invalid")
        if self.allowed_tool_ids != () or self.max_tool_calls != 0:
            raise ValueError("Orchestration authority cannot grant tools")
        _utc(self.issued_at, "authority issue time")
        _utc(self.expires_at, "authority expiry time")
        if self.expires_at <= self.issued_at:
            raise ValueError("Orchestration authority expiry is invalid")
        if (
            not isinstance(self.max_parallel_workstreams, int)
            or isinstance(self.max_parallel_workstreams, bool)
            or not 2 <= self.max_parallel_workstreams <= 8
        ):
            raise ValueError("Orchestration parallel-work limit is invalid")
        if self.live_provider_allowed:
            raise ValueError("Day 30 does not authorize a live provider")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class SourceBinding:
    kind: OrchestrationSourceKind
    artifact_id: str
    artifact_digest: str
    status: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OrchestrationSourceKind):
            raise ValueError("Orchestration source kind is invalid")
        _identifier(self.artifact_id, "source artifact ID")
        _digest(self.artifact_digest, "source artifact digest")
        _text(self.status, "source status", 160)


@dataclass(frozen=True)
class DependencyNode:
    node_id: str
    owner: str
    objective: str
    dependency_node_ids: tuple[str, ...]
    source_artifact_digests: tuple[str, ...]
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.node_id, "dependency node ID")
        _text(self.owner, "dependency owner", 120)
        _text(self.objective, "dependency objective", 500)
        _items(self.dependency_node_ids, "dependency node dependencies", 0, 10, 128, identifiers=True)
        _digests(self.source_artifact_digests, "dependency node sources", 1, 11)
        if self.node_id in self.dependency_node_ids or self.execution_state != EXECUTION_STATE:
            raise ValueError("Dependency node state is invalid")


@dataclass(frozen=True)
class ParallelWave:
    wave_id: str
    sequence: int
    node_ids: tuple[str, ...]
    entry_checks: tuple[str, ...]
    exit_checks: tuple[str, ...]
    max_parallelism: int
    execution_state: str = EXECUTION_STATE

    def __post_init__(self) -> None:
        _identifier(self.wave_id, "parallel wave ID")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("Parallel wave sequence is invalid")
        _items(self.node_ids, "parallel wave nodes", 1, 8, 128, identifiers=True)
        _items(self.entry_checks, "parallel wave entry checks", 1, 6, 240)
        _items(self.exit_checks, "parallel wave exit checks", 1, 6, 240)
        if (
            not isinstance(self.max_parallelism, int)
            or isinstance(self.max_parallelism, bool)
            or not 1 <= self.max_parallelism <= len(self.node_ids)
            or self.execution_state != EXECUTION_STATE
        ):
            raise ValueError("Parallel wave state is invalid")


@dataclass(frozen=True)
class ContextPackage:
    context_id: str
    target_node_id: str
    allowed_source_digests: tuple[str, ...]
    included_fields: tuple[str, ...]
    excluded_data_classes: tuple[str, ...]
    context_digest: str

    def __post_init__(self) -> None:
        _identifier(self.context_id, "context package ID")
        _identifier(self.target_node_id, "context target node ID")
        _digests(self.allowed_source_digests, "context sources", 1, 11)
        _items(self.included_fields, "context included fields", 2, 12, 120)
        _items(self.excluded_data_classes, "context exclusions", 4, 8, 120)
        _digest(self.context_digest, "context package digest")


@dataclass(frozen=True)
class HandoffRecord:
    handoff_id: str
    source_node_ids: tuple[str, ...]
    target_node_ids: tuple[str, ...]
    artifact_digests: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    state: str = HANDOFF_STATE

    def __post_init__(self) -> None:
        _identifier(self.handoff_id, "handoff ID")
        _items(self.source_node_ids, "handoff sources", 1, 8, 128, identifiers=True)
        _items(self.target_node_ids, "handoff targets", 1, 8, 128, identifiers=True)
        _digests(self.artifact_digests, "handoff artifacts", 1, 11)
        _items(self.acceptance_checks, "handoff acceptance checks", 2, 6, 240)
        if set(self.source_node_ids) & set(self.target_node_ids) or self.state != HANDOFF_STATE:
            raise ValueError("Handoff state is invalid")


@dataclass(frozen=True)
class ConflictRoute:
    conflict_id: str
    participant_node_ids: tuple[str, ...]
    subject: str
    detection_rule: str
    resolution_owner: str
    resolution_policy: str
    downstream_blocked: bool
    state: str = CONFLICT_STATE

    def __post_init__(self) -> None:
        _identifier(self.conflict_id, "conflict ID")
        _items(self.participant_node_ids, "conflict participants", 2, 8, 128, identifiers=True)
        for value, label, maximum in (
            (self.subject, "conflict subject", 300),
            (self.detection_rule, "conflict detection rule", 500),
            (self.resolution_owner, "conflict resolution owner", 160),
            (self.resolution_policy, "conflict resolution policy", 600),
        ):
            _text(value, label, maximum)
        if not isinstance(self.downstream_blocked, bool) or self.state != CONFLICT_STATE:
            raise ValueError("Conflict route state is invalid")


@dataclass(frozen=True)
class EscalationRecord:
    escalation_id: str
    trigger: str
    human_owner: str
    required_evidence_digests: tuple[str, ...]
    permitted_decisions: tuple[str, ...]
    state: str = ESCALATION_STATE

    def __post_init__(self) -> None:
        _identifier(self.escalation_id, "escalation ID")
        _text(self.trigger, "escalation trigger", 500)
        _text(self.human_owner, "escalation human owner", 160)
        _digests(self.required_evidence_digests, "escalation evidence", 1, 11)
        _items(self.permitted_decisions, "escalation decisions", 2, 6, 180)
        if self.state != ESCALATION_STATE:
            raise ValueError("Escalation state is invalid")


@dataclass(frozen=True)
class OrchestrationStatusReport:
    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    escalations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("Orchestration status is invalid")
        for values, label in (
            (self.completed_items, "completed items"),
            (self.next_actions, "next actions"),
            (self.blockers, "blockers"),
            (self.escalations, "escalations"),
        ):
            _items(values, f"orchestration {label}", 1, 8, 300)


@dataclass(frozen=True)
class OrchestrationDraft:
    dependency_nodes: tuple[DependencyNode, ...]
    parallel_waves: tuple[ParallelWave, ...]
    context_packages: tuple[ContextPackage, ...]
    handoffs: tuple[HandoffRecord, ...]
    conflicts: tuple[ConflictRoute, ...]
    escalations: tuple[EscalationRecord, ...]
    status_report: OrchestrationStatusReport

    def __post_init__(self) -> None:
        _typed(self.dependency_nodes, DependencyNode, "dependency nodes", 11, 11)
        _typed(self.parallel_waves, ParallelWave, "parallel waves", 9, 9)
        _typed(self.context_packages, ContextPackage, "context packages", 11, 11)
        _typed(self.handoffs, HandoffRecord, "handoffs", 7, 7)
        _typed(self.conflicts, ConflictRoute, "conflicts", 3, 3)
        _typed(self.escalations, EscalationRecord, "escalations", 3, 3)
        if not isinstance(self.status_report, OrchestrationStatusReport):
            raise ValueError("Orchestration draft status is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class MultiAgentOrchestrationArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    provider_id: str
    authority_digest: str
    source_set_digest: str
    source_bindings: tuple[SourceBinding, ...]
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    dependency_nodes: tuple[DependencyNode, ...]
    parallel_waves: tuple[ParallelWave, ...]
    context_packages: tuple[ContextPackage, ...]
    handoffs: tuple[HandoffRecord, ...]
    conflicts: tuple[ConflictRoute, ...]
    escalations: tuple[EscalationRecord, ...]
    status_report: OrchestrationStatusReport
    provider_output_digest: str
    generated_at: datetime
    execution_state: str = EXECUTION_STATE
    status: str = ARTIFACT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.artifact_id, "artifact"),
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.execution_id, "execution"),
            (self.assignment_id, "assignment"),
            (self.provider_id, "provider"),
        ):
            _identifier(value, f"Orchestration {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order digest"),
            (self.authority_digest, "authority digest"),
            (self.source_set_digest, "source-set digest"),
            (self.provider_output_digest, "provider output digest"),
        ):
            _digest(value, label)
        _typed(self.source_bindings, SourceBinding, "source bindings", 11, 11)
        if tuple(item.kind for item in self.source_bindings) != SOURCE_ORDER:
            raise ValueError("Orchestration source order is invalid")
        if self.capability_ids != ORCHESTRATION_CAPABILITIES or self.action_ids != ORCHESTRATION_ACTIONS:
            raise ValueError("Orchestration profile is invalid")
        OrchestrationDraft(
            self.dependency_nodes,
            self.parallel_waves,
            self.context_packages,
            self.handoffs,
            self.conflicts,
            self.escalations,
            self.status_report,
        )
        _utc(self.generated_at, "artifact generation time")
        if (
            self.execution_state != EXECUTION_STATE
            or self.status != ARTIFACT_STATUS
            or self.pilot_status != PILOT_STATUS
        ):
            raise ValueError("Orchestration artifact state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        for record, source in zip(payload["source_bindings"], self.source_bindings, strict=True):
            record["kind"] = source.kind.value
        payload["generated_at"] = self.generated_at.isoformat()
        return canonical_digest(payload)


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "orchestration execution ID")
    return "orchestration-" + hashlib.sha256(execution_id.encode()).hexdigest()[:24]


def source_set_digest(bindings: tuple[SourceBinding, ...]) -> str:
    _typed(bindings, SourceBinding, "source bindings", 11, 11)
    if tuple(item.kind for item in bindings) != SOURCE_ORDER:
        raise ValueError("Orchestration source order is invalid")
    return canonical_digest(
        tuple(
            {
                "kind": item.kind.value,
                "artifact_id": item.artifact_id,
                "artifact_digest": item.artifact_digest,
                "status": item.status,
            }
            for item in bindings
        )
    )


def context_digest(target_node_id: str, source_digests: tuple[str, ...], fields: tuple[str, ...]) -> str:
    return canonical_digest(
        {"target_node_id": target_node_id, "source_digests": source_digests, "fields": fields}
    )


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
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"Orchestration {label} are invalid")
    for value in values:
        _digest(value, f"Orchestration {label}")
    if len(set(values)) != len(values):
        raise ValueError(f"Orchestration {label} contain duplicates")


def _actions(values: object) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError("Orchestration actions are invalid")
    if any(not isinstance(value, str) or not _ACTION.fullmatch(value) for value in values):
        raise ValueError("Orchestration actions are invalid")
    if len(set(values)) != len(values):
        raise ValueError("Orchestration actions contain duplicates")


def _items(
    values: object,
    label: str,
    minimum: int,
    maximum: int,
    item_maximum: int,
    *,
    identifiers: bool = False,
) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"Orchestration {label} are invalid")
    for value in values:
        if identifiers:
            _identifier(value, label)
        else:
            _text(value, label, item_maximum)
    if len(set(values)) != len(values):
        raise ValueError(f"Orchestration {label} contain duplicates")


def _typed(values: object, kind: type, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or any(not isinstance(value, kind) for value in values)
    ):
        raise ValueError(f"Orchestration {label} are invalid")


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
        or "\x7f" in value
    ):
        raise ValueError(f"Orchestration {label} is invalid")


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"Orchestration {label} must be UTC")
