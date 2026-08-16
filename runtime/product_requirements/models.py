"""Immutable Product Requirements Management domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RequirementStatus(str, Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    REVIEW = "UNDER_REVIEW"  # Backward-compatible API alias.
    APPROVED = "APPROVED"
    LOCKED = "LOCKED"
    IMPLEMENTED = "IMPLEMENTED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class RequirementCategory(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"
    NON_FUNCTIONAL = "NON_FUNCTIONAL"
    SECURITY = "SECURITY"
    PRIVACY = "PRIVACY"
    ACCESSIBILITY = "ACCESSIBILITY"
    PERFORMANCE = "PERFORMANCE"
    ARCHITECTURE = "ARCHITECTURE"
    COMMERCIAL = "COMMERCIAL"
    DEPLOYMENT = "DEPLOYMENT"
    FUTURE_ROADMAP = "FUTURE_ROADMAP"


class RequirementPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DecisionType(str, Enum):
    PRODUCT = "PRODUCT"
    ARCHITECTURE = "ARCHITECTURE"
    SECURITY = "SECURITY"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REVIEW = "HUMAN_REVIEW"  # Backward-compatible API alias.
    COMMERCIAL = "COMMERCIAL"


@dataclass(frozen=True)
class RevisionRecord:
    version: str
    actor: str
    action: str
    reason: str
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ProductRequirement:
    requirement_id: str
    title: str
    description: str
    rationale: str
    acceptance_criteria: tuple[str, ...]
    priority: RequirementPriority
    milestone: str
    status: RequirementStatus
    version: str
    author: str
    approver: str | None
    created_at: datetime
    updated_at: datetime
    affected_products: tuple[str, ...]
    tags: tuple[str, ...]
    category: RequirementCategory
    product_id: str = ""
    locked_at: datetime | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    conflicts_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in ((self.requirement_id, "requirement ID"), (self.title, "title"),
                            (self.description, "description"), (self.version, "version"),
                            (self.author, "author")):
            _text(value, name)
        _utc(self.created_at); _utc(self.updated_at)
        if self.locked_at is not None: _utc(self.locked_at)
        if self.product_id: _text(self.product_id, "product ID")
        for values, name in ((self.acceptance_criteria, "acceptance criteria"),
                             (self.affected_products, "affected products"),
                             (self.tags, "tags"), (self.conflicts_with, "conflicts")):
            _tuple(values, name)


@dataclass(frozen=True)
class ProductRequirementsDocument:
    prd_id: str
    product_id: str
    title: str
    version: str
    status: RequirementStatus
    author: str
    approver: str | None
    requirements: tuple[ProductRequirement, ...]
    explicit_exclusions: tuple[str, ...]
    future_roadmap: tuple[str, ...]
    revision_history: tuple[RevisionRecord, ...]
    created_at: datetime
    updated_at: datetime
    supersedes_version: str | None = None
    locked_at: datetime | None = None
    requirement_groups: tuple["RequirementGroup", ...] = ()
    approval_history: tuple["RequirementApproval", ...] = ()

    def __post_init__(self) -> None:
        for value in (self.prd_id, self.product_id, self.title, self.version, self.author):
            _text(value, "PRD field")
        _utc(self.created_at); _utc(self.updated_at)
        if self.locked_at is not None: _utc(self.locked_at)
        if not self.requirements:
            raise ValueError("PRD requires at least one requirement")
        ids = [item.requirement_id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("PRD requirement IDs must be unique")
        if self.status is RequirementStatus.LOCKED and (not self.approver or not self.locked_at):
            raise ValueError("Locked PRD requires approver and lock timestamp")
        grouped = {item for group in self.requirement_groups for item in group.requirement_ids}
        if grouped - set(ids):
            raise ValueError("Requirement groups must reference requirements in the PRD")


@dataclass(frozen=True)
class RequirementGroup:
    group_id: str
    title: str
    requirement_ids: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class RequirementVersion:
    requirement_id: str
    version: str
    previous_version: str | None
    changed_by: str
    rationale: str
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RequirementApproval:
    approval_id: str
    requirement_ids: tuple[str, ...]
    approver: str
    decision: str
    rationale: str
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RequirementLock:
    lock_id: str
    prd_id: str
    version: str
    locked_by: str
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RequirementChangeRequest:
    change_request_id: str
    product_id: str
    requirement_ids: tuple[str, ...]
    requested_by: str
    rationale: str
    proposed_changes: str
    status: str = "OPEN"
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RequirementDiff:
    prd_id: str
    from_version: str
    to_version: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    requirement_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoadmapMilestone:
    milestone: str
    requirement_ids: tuple[str, ...]
    priorities: tuple[RequirementPriority, ...]


@dataclass(frozen=True)
class RoadmapItem:
    roadmap_item_id: str
    product_id: str
    milestone: str
    requirement_ids: tuple[str, ...]
    status: str = "PLANNED"


@dataclass(frozen=True)
class ImplementationTrace:
    trace_id: str
    requirement_id: str
    implementation_task_id: str
    commit_sha: str
    pull_request_url: str
    release_id: str
    recorded_at: datetime = field(default_factory=utc_now)
    implementation_id: str = ""

    def __post_init__(self) -> None:
        for value in (self.trace_id, self.requirement_id, self.implementation_task_id,
                      self.pull_request_url, self.release_id):
            _text(value, "trace field")
        if len(self.commit_sha) != 40 or any(c not in "0123456789abcdef" for c in self.commit_sha.lower()):
            raise ValueError("Trace commit must be a full hexadecimal SHA")
        _utc(self.recorded_at)


@dataclass(frozen=True)
class DecisionLogEntry:
    decision_id: str
    decision_type: DecisionType
    title: str
    decision: str
    rationale: str
    actor: str
    affected_requirements: tuple[str, ...]
    timestamp: datetime = field(default_factory=utc_now)
    product_id: str = ""
    approver: str = ""

    def __post_init__(self) -> None:
        for value in (self.decision_id, self.title, self.decision, self.rationale, self.actor):
            _text(value, "decision field")
        _tuple(self.affected_requirements, "affected requirements")
        _utc(self.timestamp)


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 20_000 or "\0" in value:
        raise ValueError(f"{name} must be bounded non-empty text")


def _tuple(values: tuple[str, ...], name: str) -> None:
    if not isinstance(values, tuple) or len(values) > 1_000:
        raise ValueError(f"{name} must be a bounded tuple")
    for value in values: _text(value, name)


def _utc(value: datetime) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError("Timestamps must be timezone-aware UTC")
