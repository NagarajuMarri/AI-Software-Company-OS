"""Immutable customer-facing planning and Codex execution values."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
from pathlib import Path
import re

from runtime.coding_providers import CodexAuthenticationMode
from runtime.managed_execution.policy import safe_relative_path


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BRANCH = re.compile(
    r"^(?![-/.])(?!.*(?:\.\.|//|@\{|[~^:?*\[\\]))"
    r"(?!.*(?:/\.|\.lock(?:/|$)))[A-Za-z0-9._/-]{1,200}(?<![/.])$"
)
_FORBIDDEN_PATHS = (
    ".env",
    ".git/",
    ".github/workflows/",
    "credentials",
    "deploy/",
    "infrastructure/",
    "migrations/",
    "payment/",
)


class CustomerExecutionPlanStatus(str, Enum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class CustomerExecutionTaskStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class CustomerExecutionConfiguration:
    """Operator-owned repository policy; never populated from browser fields."""

    workspace_root: Path
    model: str
    authentication_mode: CodexAuthenticationMode
    allowed_paths: tuple[str, ...]
    candidate_files: tuple[str, ...]
    enabled: bool = False
    live_operation_confirmed: bool = False
    provider_id: str = "openai-codex-sdk"

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_root, Path):
            raise ValueError("Execution workspace must be a Path")
        if not isinstance(self.model, str) or not _MODEL.fullmatch(self.model):
            raise ValueError("Execution model is invalid")
        if not isinstance(self.authentication_mode, CodexAuthenticationMode):
            raise ValueError("Execution authentication mode is invalid")
        if self.provider_id != "openai-codex-sdk":
            raise ValueError("Only the governed Codex SDK provider is supported")
        if not self.allowed_paths or len(self.allowed_paths) > 25:
            raise ValueError("At least one bounded execution path is required")
        if not self.candidate_files or len(self.candidate_files) > 20:
            raise ValueError("At least one bounded candidate file is required")
        allowed = tuple(_path(value) for value in self.allowed_paths)
        candidates = tuple(_path(value) for value in self.candidate_files)
        if len(set(allowed)) != len(allowed) or len(set(candidates)) != len(candidates):
            raise ValueError("Execution paths must be unique")
        if any(_matches(value, _FORBIDDEN_PATHS) for value in allowed + candidates):
            raise ValueError("Execution configuration includes a forbidden path")
        if any(not _matches(value, allowed) for value in candidates):
            raise ValueError("Candidate files must be inside the execution allow-list")

    @property
    def billing_source(self) -> str:
        if self.authentication_mode is CodexAuthenticationMode.CHATGPT_SUBSCRIPTION:
            return "chatgpt-plan"
        return "openai-platform"


@dataclass(frozen=True)
class CustomerExecutionTask:
    task_id: str
    requirement_id: str
    title: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    candidate_files: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    status: CustomerExecutionTaskStatus = CustomerExecutionTaskStatus.PENDING
    provider_operation_id: str | None = None
    provider_task_id: str | None = None
    changed_paths: tuple[str, ...] = ()
    additions: int = 0
    deletions: int = 0
    input_units: int | None = None
    output_units: int | None = None
    request_count: int | None = None
    result_summary: str | None = None
    manifest_digest: str | None = None

    def __post_init__(self) -> None:
        _id(self.task_id, "execution task ID")
        if not re.fullmatch(r"REQ-[A-Z0-9][A-Z0-9-]{0,59}", self.requirement_id):
            raise ValueError("Execution requirement ID is invalid")
        _text(self.title, "execution task title", 300)
        _text(self.objective, "execution task objective", 4_000)
        _items(self.acceptance_criteria, "execution acceptance criteria", 1, 10, 500)
        _items(self.candidate_files, "execution candidate files", 1, 20, 500)
        _items(self.allowed_paths, "execution allowed paths", 1, 25, 500)
        _items(self.forbidden_paths, "execution forbidden paths", 1, 25, 500)
        if not isinstance(self.status, CustomerExecutionTaskStatus):
            raise ValueError("Execution task status is invalid")
        for value, label in (
            (self.provider_operation_id, "provider operation ID"),
            (self.provider_task_id, "provider task ID"),
        ):
            if value is not None:
                _id(value, label)
        for path in self.changed_paths:
            _path(path)
        for count, label in ((self.additions, "additions"), (self.deletions, "deletions")):
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(f"Execution {label} are invalid")
        for units in (self.input_units, self.output_units, self.request_count):
            if units is not None and (
                not isinstance(units, int) or isinstance(units, bool) or units < 0
            ):
                raise ValueError("Execution usage is invalid")
        if self.result_summary is not None:
            _text(self.result_summary, "execution result summary", 2_000)
        if self.manifest_digest is not None:
            _digest(self.manifest_digest, "execution manifest digest")

    def scope_record(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "requirement_id": self.requirement_id,
            "title": self.title,
            "objective": self.objective,
            "acceptance_criteria": self.acceptance_criteria,
            "candidate_files": self.candidate_files,
            "allowed_paths": self.allowed_paths,
            "forbidden_paths": self.forbidden_paths,
        }


@dataclass(frozen=True)
class CustomerExecutionPlan:
    plan_id: str
    customer_id: str
    request_id: str
    product_id: str
    progress_digest: str
    requirements_digest: str
    prd_digest: str
    roadmap_digest: str
    roadmap_approval_digest: str
    estimate_digest: str
    workspace_id: str
    workspace_branch: str
    workspace_commit: str
    provider_id: str
    model: str
    authentication_mode: str
    billing_source: str
    tasks: tuple[CustomerExecutionTask, ...]
    created_at: datetime
    updated_at: datetime
    status: CustomerExecutionPlanStatus = CustomerExecutionPlanStatus.AWAITING_APPROVAL
    approved_at: datetime | None = None
    approved_by: str | None = None
    failure_classification: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.plan_id, "execution plan ID"),
            (self.customer_id, "execution customer ID"),
            (self.request_id, "execution request ID"),
            (self.product_id, "execution product ID"),
            (self.workspace_id, "execution workspace ID"),
        ):
            _id(value, label)
        for value, label in (
            (self.progress_digest, "progress digest"),
            (self.requirements_digest, "requirements digest"),
            (self.prd_digest, "PRD digest"),
            (self.roadmap_digest, "roadmap digest"),
            (self.roadmap_approval_digest, "roadmap approval digest"),
            (self.estimate_digest, "estimate digest"),
        ):
            _digest(value, label)
        if not _BRANCH.fullmatch(self.workspace_branch) or not self.workspace_branch.startswith(
            "agent/"
        ):
            raise ValueError("Execution requires an agent/* feature branch")
        if not re.fullmatch(r"[0-9a-f]{40,64}", self.workspace_commit):
            raise ValueError("Execution workspace commit is invalid")
        if self.provider_id != "openai-codex-sdk":
            raise ValueError("Execution provider is invalid")
        if not _MODEL.fullmatch(self.model):
            raise ValueError("Execution model is invalid")
        if self.authentication_mode not in tuple(value.value for value in CodexAuthenticationMode):
            raise ValueError("Execution authentication mode is invalid")
        if self.billing_source not in {"chatgpt-plan", "openai-platform"}:
            raise ValueError("Execution billing source is invalid")
        if (
            not self.tasks
            or len(self.tasks) > 100
            or len({value.task_id for value in self.tasks}) != len(self.tasks)
            or len({value.requirement_id for value in self.tasks}) != len(self.tasks)
        ):
            raise ValueError("Execution tasks are invalid")
        _utc(self.created_at, "execution creation time")
        _utc(self.updated_at, "execution update time")
        if self.updated_at < self.created_at:
            raise ValueError("Execution time regressed")
        if not isinstance(self.status, CustomerExecutionPlanStatus):
            raise ValueError("Execution plan status is invalid")
        if self.approved_at is not None:
            _utc(self.approved_at, "execution approval time")
        if (self.approved_at is None) != (self.approved_by is None):
            raise ValueError("Execution approval identity is incomplete")
        if self.approved_by is not None:
            _id(self.approved_by, "execution approver")
        if self.failure_classification is not None:
            _text(self.failure_classification, "execution failure classification", 200)

    @property
    def scope_digest(self) -> str:
        return _hash(
            {
                "plan_id": self.plan_id,
                "customer_id": self.customer_id,
                "request_id": self.request_id,
                "product_id": self.product_id,
                "progress_digest": self.progress_digest,
                "requirements_digest": self.requirements_digest,
                "prd_digest": self.prd_digest,
                "roadmap_digest": self.roadmap_digest,
                "roadmap_approval_digest": self.roadmap_approval_digest,
                "estimate_digest": self.estimate_digest,
                "workspace_id": self.workspace_id,
                "workspace_branch": self.workspace_branch,
                "workspace_commit": self.workspace_commit,
                "provider_id": self.provider_id,
                "model": self.model,
                "authentication_mode": self.authentication_mode,
                "billing_source": self.billing_source,
                "tasks": tuple(value.scope_record() for value in self.tasks),
            }
        )

    @property
    def digest(self) -> str:
        return _hash(asdict(self))


def plan_id_for(request_id: str) -> str:
    _id(request_id, "execution request ID")
    value = hashlib.sha256(f"customer-execution:{request_id}".encode()).hexdigest()
    return f"customer-execution-{value[:24]}"


def workspace_id_for(path: Path) -> str:
    value = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
    return f"workspace-{value[:24]}"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json).encode("utf-8")
    ).hexdigest()


def _json(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Cannot encode {type(value).__name__}")


def _id(value: object, label: str) -> None:
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
    ):
        raise ValueError(f"{label} is invalid")


def _items(
    values: object, label: str, minimum: int, maximum: int, item_limit: int
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len({value for value in values if isinstance(value, str)}) != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        _text(value, label, item_limit)


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")


def _path(value: str) -> str:
    normalized = safe_relative_path(value).strip("/")
    if not normalized or len(normalized) > 500:
        raise ValueError("Execution path is invalid")
    return normalized


def _matches(value: str, prefixes: tuple[str, ...]) -> bool:
    parts = tuple(part.casefold() for part in value.replace("\\", "/").strip("/").split("/"))
    return any(
        parts[: len(prefix_parts)] == prefix_parts
        for prefix in prefixes
        if (prefix_parts := tuple(
            part.casefold() for part in prefix.replace("\\", "/").strip("/").split("/")
        ))
    )
