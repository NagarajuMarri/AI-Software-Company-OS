"""Immutable request, context, proposal, and approval models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from runtime.planning.errors import PlanningValidationError

MAX_TEXT = 10_000
MAX_ITEMS = 100


def utc_now():
    return datetime.now(timezone.utc)


def _text(value, name, *, required=True):
    if not isinstance(value, str) or (required and not value.strip()):
        raise PlanningValidationError(f"{name} must be a non-empty string")
    if len(value) > MAX_TEXT:
        raise PlanningValidationError(f"{name} exceeds {MAX_TEXT} characters")


def _items(value, name, *, required=False):
    if not isinstance(value, tuple):
        raise PlanningValidationError(f"{name} must be an immutable tuple")
    if required and not value:
        raise PlanningValidationError(f"{name} must not be empty")
    if len(value) > MAX_ITEMS:
        raise PlanningValidationError(f"{name} exceeds {MAX_ITEMS} items")
    for item in value:
        _text(item, f"{name} item")


class ChangePriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ManagedProductChangeRequest:
    request_id: str
    project_id: str
    title: str
    objective: str
    business_context: str
    requested_capabilities: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    priority: ChangePriority = ChangePriority.NORMAL
    requested_by: str = "unknown"
    created_at: datetime = field(default_factory=utc_now)
    correlation_id: str = ""
    target_milestone_id: str | None = None
    preferred_base_branch: str | None = None

    def __post_init__(self):
        for value, name in ((self.request_id, "request_id"), (self.project_id, "project_id"),
                            (self.title, "title"), (self.objective, "objective"),
                            (self.business_context, "business_context"),
                            (self.requested_by, "requested_by")):
            _text(value, name)
        _items(self.requested_capabilities, "requested_capabilities")
        _items(self.acceptance_criteria, "acceptance_criteria", required=True)
        _items(self.constraints, "constraints")
        _items(self.out_of_scope, "out_of_scope")
        if not isinstance(self.priority, ChangePriority):
            raise PlanningValidationError("priority must be a ChangePriority")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise PlanningValidationError("created_at must be timezone-aware UTC")
        if self.created_at.utcoffset().total_seconds() != 0:
            raise PlanningValidationError("created_at must use UTC")
        if self.correlation_id:
            _text(self.correlation_id, "correlation_id")


@dataclass(frozen=True)
class ContextFile:
    repository_id: str
    path: str
    language: str
    category: str


@dataclass(frozen=True)
class ContextSymbol:
    repository_id: str
    path: str
    name: str
    kind: str
    qualified_name: str


@dataclass(frozen=True)
class ManagedProductPlanningContext:
    project_id: str
    project_name: str
    repository_url: str
    default_branch: str
    request: ManagedProductChangeRequest
    knowledge_scanned_at: datetime
    knowledge_summary: Mapping[str, object]
    relevant_files: tuple[ContextFile, ...]
    relevant_symbols: tuple[ContextSymbol, ...]
    languages: tuple[tuple[str, int], ...]
    dependencies: tuple[str, ...]
    manager_status: str
    active_milestone_id: str | None
    incomplete_tasks: tuple[str, ...]
    decisions: tuple[str, ...]
    risks: tuple[str, ...]
    notes: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "knowledge_summary",
                           MappingProxyType(dict(self.knowledge_summary)))


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ProposedTask:
    task_id: str
    title: str
    description: str
    dependencies: tuple[str, ...]
    role_requirements: tuple[str, ...]
    capability_requirements: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    candidate_files: tuple[str, ...]
    quality_gates: tuple[str, ...]
    risk_level: RiskLevel = RiskLevel.MEDIUM
    requires_human_review: bool = True


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class ProposalDecision:
    status: ProposalStatus
    actor: str
    timestamp: datetime
    reason: str | None = None


@dataclass(frozen=True)
class ProposedProductMilestone:
    proposal_id: str
    version: int
    request_id: str
    project_id: str
    milestone_id: str
    title: str
    objective: str
    scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    architecture_considerations: tuple[str, ...]
    tasks: tuple[ProposedTask, ...]
    acceptance_criteria: tuple[str, ...]
    candidate_impacted_files: tuple[str, ...]
    quality_gates: tuple[str, ...]
    risks: tuple[str, ...]
    assumptions: tuple[str, ...]
    required_human_approvals: tuple[str, ...]
    provider_metadata: tuple[tuple[str, str], ...]
    generated_at: datetime
    status: ProposalStatus = ProposalStatus.PROPOSED
    decisions: tuple[ProposalDecision, ...] = ()
    supersedes: str | None = None
    materialised_at: datetime | None = None
