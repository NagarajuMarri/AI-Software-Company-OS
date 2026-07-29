"""Strongly typed project-management state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from runtime.exceptions import ValidationError
from runtime.validation import validate_required_string


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class MilestoneStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class ProjectManagementStatus(str, Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    dependencies: tuple[str, ...] = ()
    owner: str | None = None
    estimated_effort: str | None = None
    actual_effort: str | None = None
    blocker_reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_required_string(self.task_id, "Task.task_id")
        validate_required_string(self.title, "Task.title")
        if self.task_id in self.dependencies:
            raise ValidationError("A task cannot depend on itself")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValidationError("Task dependencies must be unique")
        if self.status == TaskStatus.BLOCKED and not self.blocker_reason:
            raise ValidationError("A blocked task requires a blocker reason")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValidationError("Task timestamps must be timezone-aware")


@dataclass(frozen=True)
class Milestone:
    milestone_id: str
    title: str
    goal: str | None = None
    status: MilestoneStatus = MilestoneStatus.NOT_STARTED
    task_ids: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_required_string(self.milestone_id, "Milestone.milestone_id")
        validate_required_string(self.title, "Milestone.title")
        if self.milestone_id in self.dependencies:
            raise ValidationError("A milestone cannot depend on itself")
        if len(self.task_ids) != len(set(self.task_ids)):
            raise ValidationError("Milestone task IDs must be unique")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValidationError("Milestone dependencies must be unique")


@dataclass(frozen=True)
class Decision:
    decision_id: str
    title: str
    rationale: str
    timestamp: datetime = field(default_factory=utc_now)
    author: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Note:
    note_id: str
    content: str
    timestamp: datetime = field(default_factory=utc_now)
    author: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RiskSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskStatus(str, Enum):
    OPEN = "OPEN"
    MITIGATED = "MITIGATED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class Risk:
    risk_id: str
    title: str
    description: str
    severity: RiskSeverity
    status: RiskStatus = RiskStatus.OPEN
    mitigation: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectManagerState:
    project_id: str
    schema_version: int = 1
    status: ProjectManagementStatus = ProjectManagementStatus.PLANNED
    milestones: tuple[Milestone, ...] = ()
    tasks: tuple[Task, ...] = ()
    active_milestone_id: str | None = None
    decisions: tuple[Decision, ...] = ()
    notes: tuple[Note, ...] = ()
    risks: tuple[Risk, ...] = ()
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def task(self, task_id: str) -> Task:
        from runtime.project_manager.errors import UnknownTaskError
        try:
            return next(item for item in self.tasks if item.task_id == task_id)
        except StopIteration as error:
            raise UnknownTaskError(f"Task {task_id!r} does not exist") from error

    def milestone(self, milestone_id: str) -> Milestone:
        from runtime.project_manager.errors import UnknownMilestoneError
        try:
            return next(item for item in self.milestones if item.milestone_id == milestone_id)
        except StopIteration as error:
            raise UnknownMilestoneError(f"Milestone {milestone_id!r} does not exist") from error

    def with_task(self, task: Task, now: datetime) -> ProjectManagerState:
        return replace(self, tasks=tuple(task if x.task_id == task.task_id else x for x in self.tasks), updated_at=now)
