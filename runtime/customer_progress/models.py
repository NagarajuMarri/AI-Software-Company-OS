"""Immutable customer-visible projection of governed project progress."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REQUIREMENT_ID = re.compile(r"^REQ-[A-Z0-9][A-Z0-9-]{0,59}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
GENERATION_PROFILE = "ascos-customer-project-progress-v1"
PROJECT_STATUS = "AWAITING_EXECUTION_AUTHORITY"
MILESTONE_STATUS = "NOT_STARTED"
TASK_STATUS = "NOT_STARTED"
BLOCKER_STATUS = "OPEN"


@dataclass(frozen=True)
class CustomerProgressTask:
    """One read-only planned task derived from an exact locked requirement."""

    task_id: str
    requirement_id: str
    milestone_id: str
    title: str
    priority: str
    assigned_agent_id: str | None = None
    progress_percentage: int = 0
    status: str = TASK_STATUS

    def __post_init__(self) -> None:
        _identifier(self.task_id, "progress task ID")
        if not isinstance(self.requirement_id, str) or not _REQUIREMENT_ID.fullmatch(
            self.requirement_id
        ):
            raise ValueError("Progress requirement ID is invalid")
        _identifier(self.milestone_id, "progress task milestone ID")
        _text(self.title, "progress task title", 300)
        if self.priority not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            raise ValueError("Progress task priority is invalid")
        if self.assigned_agent_id is not None:
            _identifier(self.assigned_agent_id, "progress assigned agent ID")
        if self.progress_percentage != 0 or self.status != TASK_STATUS:
            raise ValueError("Day 20 tasks must remain not started")


@dataclass(frozen=True)
class CustomerProgressMilestone:
    """One exact governed roadmap item and its visible planned tasks."""

    milestone_id: str
    title: str
    sequence: int
    requirement_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    minimum_effort_days: int
    maximum_effort_days: int
    assigned_agent_ids: tuple[str, ...] = ()
    progress_percentage: int = 0
    status: str = MILESTONE_STATUS

    def __post_init__(self) -> None:
        _identifier(self.milestone_id, "progress milestone ID")
        _text(self.title, "progress milestone title", 300)
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("Progress milestone sequence is invalid")
        if (
            not isinstance(self.requirement_ids, tuple)
            or not self.requirement_ids
            or len(set(self.requirement_ids)) != len(self.requirement_ids)
            or any(
                not isinstance(value, str) or not _REQUIREMENT_ID.fullmatch(value)
                for value in self.requirement_ids
            )
        ):
            raise ValueError("Progress milestone requirements are invalid")
        if (
            not isinstance(self.task_ids, tuple)
            or len(self.task_ids) != len(self.requirement_ids)
            or len(set(self.task_ids)) != len(self.task_ids)
        ):
            raise ValueError("Progress milestone tasks are invalid")
        for task_id in self.task_ids:
            _identifier(task_id, "progress milestone task ID")
        for value, label in (
            (self.minimum_effort_days, "minimum effort"),
            (self.maximum_effort_days, "maximum effort"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Progress milestone {label} is invalid")
        if self.maximum_effort_days < self.minimum_effort_days:
            raise ValueError("Progress milestone effort range is invalid")
        if self.assigned_agent_ids:
            raise ValueError("Day 20 cannot assign operational agents")
        if self.progress_percentage != 0 or self.status != MILESTONE_STATUS:
            raise ValueError("Day 20 milestones must remain not started")


@dataclass(frozen=True)
class CustomerProgressBlocker:
    """Visible policy or authority condition preventing execution."""

    blocker_id: str
    title: str
    detail: str
    status: str = BLOCKER_STATUS

    def __post_init__(self) -> None:
        _identifier(self.blocker_id, "progress blocker ID")
        _text(self.title, "progress blocker title", 200)
        _text(self.detail, "progress blocker detail", 500)
        if self.status != BLOCKER_STATUS:
            raise ValueError("Day 20 blockers must remain open")


@dataclass(frozen=True)
class CustomerProgressDecision:
    """Visible governed decision or policy outcome with exact authority."""

    decision_id: str
    title: str
    outcome: str
    rationale: str
    authority_digest: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.decision_id, "progress decision ID")
        _text(self.title, "progress decision title", 200)
        if self.outcome not in {"APPROVED_AND_LOCKED", "DRAFT_RECORDED"}:
            raise ValueError("Progress decision outcome is invalid")
        _text(self.rationale, "progress decision rationale", 500)
        _digest(self.authority_digest, "progress decision authority digest")
        _utc(self.recorded_at, "progress decision time")


@dataclass(frozen=True)
class CustomerProjectProgressSnapshot:
    """Deterministic Day 20 dashboard projection with no execution authority."""

    progress_id: str
    customer_id: str
    request_id: str
    product_id: str
    prd_id: str
    roadmap_id: str
    roadmap_approval_id: str
    estimate_id: str
    source_request_digest: str
    requirements_digest: str
    requirements_approval_digest: str
    prd_digest: str
    prd_approval_digest: str
    roadmap_digest: str
    roadmap_approval_digest: str
    estimate_digest: str
    generation_profile: str
    title: str
    milestones: tuple[CustomerProgressMilestone, ...]
    tasks: tuple[CustomerProgressTask, ...]
    assigned_agent_ids: tuple[str, ...]
    blockers: tuple[CustomerProgressBlocker, ...]
    decisions: tuple[CustomerProgressDecision, ...]
    total_tasks: int
    completed_tasks: int
    blocked_tasks: int
    in_progress_tasks: int
    progress_percentage: int
    projected_at: datetime
    status: str = PROJECT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.progress_id, "progress ID"),
            (self.customer_id, "progress customer ID"),
            (self.request_id, "progress request ID"),
            (self.product_id, "progress product ID"),
            (self.prd_id, "progress PRD ID"),
            (self.roadmap_id, "progress roadmap ID"),
            (self.roadmap_approval_id, "progress roadmap approval ID"),
            (self.estimate_id, "progress estimate ID"),
        ):
            _identifier(value, label)
        for value, label in (
            (self.source_request_digest, "source request digest"),
            (self.requirements_digest, "requirements digest"),
            (self.requirements_approval_digest, "requirements approval digest"),
            (self.prd_digest, "PRD digest"),
            (self.prd_approval_digest, "PRD approval digest"),
            (self.roadmap_digest, "roadmap digest"),
            (self.roadmap_approval_digest, "roadmap approval digest"),
            (self.estimate_digest, "estimate digest"),
        ):
            _digest(value, f"progress {label}")
        if self.generation_profile != GENERATION_PROFILE:
            raise ValueError("Progress generation profile is invalid")
        _text(self.title, "progress title", 300)
        if (
            not isinstance(self.milestones, tuple)
            or not self.milestones
            or any(not isinstance(value, CustomerProgressMilestone) for value in self.milestones)
            or tuple(value.sequence for value in self.milestones)
            != tuple(range(1, len(self.milestones) + 1))
            or len({value.milestone_id for value in self.milestones}) != len(self.milestones)
        ):
            raise ValueError("Progress milestones are invalid")
        if (
            not isinstance(self.tasks, tuple)
            or not self.tasks
            or any(not isinstance(value, CustomerProgressTask) for value in self.tasks)
            or len({value.task_id for value in self.tasks}) != len(self.tasks)
            or len({value.requirement_id for value in self.tasks}) != len(self.tasks)
        ):
            raise ValueError("Progress tasks are invalid")
        mapped_task_ids = tuple(task_id for item in self.milestones for task_id in item.task_ids)
        mapped_requirement_ids = tuple(
            requirement_id for item in self.milestones for requirement_id in item.requirement_ids
        )
        if mapped_task_ids != tuple(value.task_id for value in self.tasks):
            raise ValueError("Progress tasks must map exactly once in milestone order")
        if mapped_requirement_ids != tuple(value.requirement_id for value in self.tasks):
            raise ValueError("Progress requirements must map exactly once in milestone order")
        if any(
            task.milestone_id != milestone.milestone_id
            for milestone in self.milestones
            for task in self.tasks
            if task.task_id in milestone.task_ids
        ):
            raise ValueError("Progress task milestone binding is invalid")
        if self.assigned_agent_ids:
            raise ValueError("Day 20 cannot expose assigned operational agents")
        if (
            not isinstance(self.blockers, tuple)
            or not self.blockers
            or any(not isinstance(value, CustomerProgressBlocker) for value in self.blockers)
            or len({value.blocker_id for value in self.blockers}) != len(self.blockers)
        ):
            raise ValueError("Progress blockers are invalid")
        if (
            not isinstance(self.decisions, tuple)
            or not self.decisions
            or any(not isinstance(value, CustomerProgressDecision) for value in self.decisions)
            or len({value.decision_id for value in self.decisions}) != len(self.decisions)
        ):
            raise ValueError("Progress decisions are invalid")
        if (
            self.total_tasks != len(self.tasks)
            or self.completed_tasks != 0
            or self.blocked_tasks != 0
            or self.in_progress_tasks != 0
            or self.progress_percentage != 0
        ):
            raise ValueError("Day 20 progress totals are invalid")
        _utc(self.projected_at, "progress projection time")
        if self.status != PROJECT_STATUS:
            raise ValueError("Day 20 project status is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["projected_at"] = self.projected_at.isoformat()
        for decision, source in zip(payload["decisions"], self.decisions, strict=True):
            decision["recorded_at"] = source.recorded_at.isoformat()
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()


def progress_id_for(request_id: str) -> str:
    """Derive one bounded non-secret progress identity."""

    _identifier(request_id, "progress request ID")
    digest = hashlib.sha256(f"customer-project-progress:{request_id}".encode()).hexdigest()
    return f"customer-progress-{digest[:24]}"


def task_id_for(request_id: str, requirement_id: str) -> str:
    """Derive a stable task-view identity without creating executable work."""

    _identifier(request_id, "progress task request ID")
    if not isinstance(requirement_id, str) or not _REQUIREMENT_ID.fullmatch(requirement_id):
        raise ValueError("Progress task requirement ID is invalid")
    digest = hashlib.sha256(f"customer-progress-task:{request_id}:{requirement_id}".encode()).hexdigest()
    return f"progress-task-{digest[:24]}"


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


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")
