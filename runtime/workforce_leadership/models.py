"""Immutable inputs and draft artifacts for Day 23 leadership agents."""

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
_ACTION = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")

INTAKE_OPPORTUNITY = "INTAKE_OPPORTUNITY"
CLARIFY_PRODUCT_SCOPE = "CLARIFY_PRODUCT_SCOPE"
PROPOSE_PRODUCT_PLAN = "PROPOSE_PRODUCT_PLAN"
REPORT_WORK_STATUS = "REPORT_WORK_STATUS"

CEO_CAPABILITY_IDS = ("opportunity-intake", "status-reporting")
PRODUCT_MANAGER_CAPABILITY_IDS = (
    "scope-clarification",
    "product-planning",
    "status-reporting",
)
CEO_ACTION_IDS = (
    EXECUTE_ASSIGNED_WORK,
    PRODUCE_EXECUTION_EVIDENCE,
    INTAKE_OPPORTUNITY,
    REPORT_WORK_STATUS,
)
PRODUCT_MANAGER_ACTION_IDS = (
    EXECUTE_ASSIGNED_WORK,
    PRODUCE_EXECUTION_EVIDENCE,
    CLARIFY_PRODUCT_SCOPE,
    PROPOSE_PRODUCT_PLAN,
    REPORT_WORK_STATUS,
)

ARTIFACT_STATUS = "DRAFT_AWAITING_HUMAN_REVIEW"
PILOT_STATUS = "NOT_SELECTED"
WORK_STATUS = "DRAFT_COMPLETE"


class LeadershipArtifactKind(str, Enum):
    """The two exact draft deliverables allowed in Day 23."""

    CEO_OPPORTUNITY_BRIEF = "CEO_OPPORTUNITY_BRIEF"
    PRODUCT_MANAGER_PLAN = "PRODUCT_MANAGER_PLAN"


@dataclass(frozen=True)
class OpportunityIntake:
    """One bounded opportunity input; it is never a pilot selection or approval."""

    opportunity_id: str
    tenant_id: str
    title: str
    problem_statement: str
    target_users: tuple[str, ...]
    desired_outcomes: tuple[str, ...]
    constraints: tuple[str, ...]
    recorded_at: datetime
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        _identifier(self.opportunity_id, "opportunity ID")
        _identifier(self.tenant_id, "opportunity tenant ID")
        _text(self.title, "opportunity title", 240)
        _text(self.problem_statement, "opportunity problem statement", 2_000)
        _items(self.target_users, "opportunity target users", 1, 8, 200)
        _items(self.desired_outcomes, "opportunity desired outcomes", 1, 8, 200)
        _items(self.constraints, "opportunity constraints", 0, 8, 240)
        _utc(self.recorded_at, "opportunity recorded time")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Opportunity intake cannot select an official pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_opportunity_record(self))


@dataclass(frozen=True)
class LeadershipStatusReport:
    """A bounded role status report with explicit human-decision blockers."""

    state: str
    completed_items: tuple[str, ...]
    next_actions: tuple[str, ...]
    blockers: tuple[str, ...]
    human_decisions_required: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state != WORK_STATUS:
            raise ValueError("Leadership status must remain draft-complete")
        _items(self.completed_items, "completed status items", 1, 8, 300)
        _items(self.next_actions, "next status actions", 1, 8, 300)
        _items(self.blockers, "status blockers", 1, 8, 300)
        _items(
            self.human_decisions_required,
            "required human decisions",
            1,
            8,
            300,
        )


@dataclass(frozen=True)
class LeadershipArtifact:
    """One validated write-once draft bound to a Digital Twin receipt."""

    artifact_id: str
    kind: LeadershipArtifactKind
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    twin_id: str
    business_role: AgentRole
    provider_id: str
    opportunity_digest: str
    upstream_artifact_digest: str | None
    summary: str
    goals: tuple[str, ...]
    scope_in: tuple[str, ...]
    scope_out: tuple[str, ...]
    clarification_questions: tuple[str, ...]
    plan_items: tuple[str, ...]
    status_report: LeadershipStatusReport
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
            (self.artifact_id, "leadership artifact ID"),
            (self.tenant_id, "leadership tenant ID"),
            (self.opportunity_id, "leadership opportunity ID"),
            (self.execution_id, "leadership execution ID"),
            (self.assignment_id, "leadership assignment ID"),
            (self.twin_id, "leadership Digital Twin ID"),
            (self.provider_id, "leadership provider ID"),
        ):
            _identifier(value, label)
        if not isinstance(self.kind, LeadershipArtifactKind):
            raise ValueError("Leadership artifact kind is invalid")
        if not isinstance(self.business_role, AgentRole):
            raise ValueError("Leadership Business Role is invalid")
        for value, label in (
            (self.opportunity_digest, "opportunity digest"),
            (self.authority_digest, "authority digest"),
            (self.assignment_digest, "assignment digest"),
            (self.request_digest, "provider request digest"),
            (self.output_digest, "provider output digest"),
            (self.receipt_digest, "execution receipt digest"),
        ):
            _digest(value, label)
        if self.upstream_artifact_digest is not None:
            _digest(self.upstream_artifact_digest, "upstream artifact digest")
        _text(self.summary, "leadership artifact summary", 2_000)
        _items(self.goals, "leadership goals", 1, 8, 300)
        _items(self.clarification_questions, "clarification questions", 1, 8, 500)
        if not isinstance(self.status_report, LeadershipStatusReport):
            raise ValueError("Leadership status report is invalid")
        if self.kind is LeadershipArtifactKind.CEO_OPPORTUNITY_BRIEF:
            if self.business_role is not AgentRole.CEO:
                raise ValueError("CEO opportunity brief requires the CEO Business Role")
            if self.upstream_artifact_digest is not None:
                raise ValueError("CEO opportunity brief cannot have an upstream artifact")
            if self.scope_in or self.scope_out or self.plan_items:
                raise ValueError("CEO opportunity brief cannot produce a product plan")
        elif self.kind is LeadershipArtifactKind.PRODUCT_MANAGER_PLAN:
            if self.business_role is not AgentRole.PROJECT_MANAGER:
                raise ValueError(
                    "Product Manager plan requires the PROJECT_MANAGER Business Role"
                )
            if self.upstream_artifact_digest is None:
                raise ValueError("Product Manager plan requires the exact CEO brief")
            _items(self.scope_in, "product scope-in items", 1, 12, 300)
            _items(self.scope_out, "product scope-out items", 1, 12, 300)
            _items(self.plan_items, "product plan items", 1, 12, 300)
        _utc(self.generated_at, "leadership artifact generation time")
        if self.status != ARTIFACT_STATUS:
            raise ValueError("Leadership artifacts must await human review")
        if self.pilot_status != PILOT_STATUS:
            raise ValueError("Leadership artifacts cannot select a pilot product")

    @property
    def digest(self) -> str:
        return canonical_digest(_artifact_record(self))


def artifact_id_for(kind: LeadershipArtifactKind, execution_id: str) -> str:
    """Derive a stable non-secret artifact ID from its execution identity."""

    if not isinstance(kind, LeadershipArtifactKind):
        raise ValueError("Leadership artifact kind is invalid")
    _identifier(execution_id, "leadership execution ID")
    value = hashlib.sha256(f"{kind.value}:{execution_id}".encode()).hexdigest()
    return f"leadership-{value[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _opportunity_record(value: OpportunityIntake) -> dict[str, object]:
    payload = asdict(value)
    payload["recorded_at"] = value.recorded_at.isoformat()
    return payload


def _status_record(value: LeadershipStatusReport) -> dict[str, object]:
    return asdict(value)


def _artifact_record(value: LeadershipArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["kind"] = value.kind.value
    payload["business_role"] = value.business_role.value
    payload["status_report"] = _status_record(value.status_report)
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


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")


def validate_action_profile(values: tuple[str, ...], expected: tuple[str, ...]) -> None:
    """Require an exact, ordered role authority profile."""

    if (
        not isinstance(values, tuple)
        or values != expected
        or len(set(values)) != len(values)
        or any(not _ACTION.fullmatch(value) for value in values)
    ):
        raise ValueError("Leadership delegated-action profile is invalid")
