"""Immutable values for the managed-product implementation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath

MAX_TEXT = 20_000
MAX_ITEMS = 500


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImplementationState(str, Enum):
    REQUESTED = "REQUESTED"
    PREPARING_WORKSPACE = "PREPARING_WORKSPACE"
    IMPLEMENTING = "IMPLEMENTING"
    VERIFYING = "VERIFYING"
    COMMITTING = "COMMITTING"
    PUSHING = "PUSHING"
    CREATING_PR = "CREATING_PR"
    WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    PR_FAILED = "PR_FAILED"

    @property
    def terminal(self) -> bool:
        return self is self.COMPLETED


class VerificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


class CleanupPolicy(str, Enum):
    KEEP = "KEEP"
    ON_SUCCESS = "ON_SUCCESS"
    ALWAYS = "ALWAYS"


class WorkspaceDisposition(str, Enum):
    ACTIVE = "ACTIVE"
    RETAINED_FOR_RECONCILIATION = "RETAINED_FOR_RECONCILIATION"
    CLEANED = "CLEANED"


@dataclass(frozen=True)
class VerificationStep:
    name: str
    command: tuple[str, ...]
    required: bool = True
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        _text(self.name, "verification step name")
        if not self.command or len(self.command) > 100 or self.timeout_seconds <= 0:
            raise ValueError("Verification step command and timeout must be bounded")


@dataclass(frozen=True)
class VerificationStepResult:
    name: str
    status: VerificationStatus
    command: tuple[str, ...]
    exit_code: int | None
    output: str
    started_at: datetime
    completed_at: datetime
    workspace_commit_sha: str = ""
    diff_digest: str = ""


@dataclass(frozen=True)
class WorkspaceResult:
    workspace_id: str
    path: str
    repository: str
    branch: str
    commit_sha: str
    remotes_removed: bool
    created_at: datetime
    disposition: WorkspaceDisposition = WorkspaceDisposition.ACTIVE


@dataclass(frozen=True)
class ProviderImplementationResult:
    execution_id: str
    summary: str
    changed_files: tuple[str, ...]
    known_risks: tuple[str, ...] = ()
    remaining_work: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.execution_id, "execution ID")
        _text(self.summary, "provider summary")
        _paths(self.changed_files, "provider changed files")
        _bounded_tuple(self.known_risks, "known risks")
        _bounded_tuple(self.remaining_work, "remaining work")


@dataclass(frozen=True)
class CommitResult:
    commit_sha: str
    message: str
    changed_files: tuple[str, ...]


@dataclass(frozen=True)
class PushResult:
    success: bool
    branch: str
    remote: str | None
    tracking_branch: str | None
    error_code: str | None = None
    details: str = ""
    remote_head_sha: str | None = None
    reconciliation_required: bool = False


@dataclass(frozen=True)
class PullRequestResult:
    number: int
    url: str
    draft: bool
    metadata: tuple[tuple[str, str], ...] = ()
    base_branch: str | None = None
    head_branch: str | None = None
    head_sha: str | None = None


@dataclass(frozen=True)
class ReviewPackage:
    summary: str
    verification_report: tuple[VerificationStepResult, ...]
    test_report: str
    changed_files: tuple[str, ...]
    commit_sha: str
    pull_request_url: str
    known_risks: tuple[str, ...]
    remaining_work: tuple[str, ...]


class HumanReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    REJECT = "REJECT"


@dataclass(frozen=True)
class HumanReviewDecisionPackage:
    package_id: str
    product_name: str
    milestone: str
    base_sha: str
    head_sha: str
    changed_path_count: int
    additions: int
    deletions: int
    architecture_summary: tuple[str, ...]
    verification_summary: tuple[str, ...]
    security_summary: tuple[str, ...]
    known_limitations: tuple[str, ...]
    review_checklist: tuple[str, ...]
    available_decisions: tuple[HumanReviewDecision, ...]
    state: ImplementationState
    reviewer: str
    approval_recorded: bool
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for value, name in (
            (self.package_id, "package ID"),
            (self.product_name, "product name"),
            (self.milestone, "milestone"),
            (self.reviewer, "reviewer"),
        ):
            _text(value, name)
        for value, name in ((self.base_sha, "base SHA"), (self.head_sha, "head SHA")):
            if len(value) != 40 or any(
                character not in "0123456789abcdef" for character in value.lower()
            ):
                raise ValueError(f"{name} must be a full hexadecimal SHA")
        for values, name in (
            (self.architecture_summary, "architecture summary"),
            (self.verification_summary, "verification summary"),
            (self.security_summary, "security summary"),
            (self.known_limitations, "known limitations"),
            (self.review_checklist, "review checklist"),
        ):
            _bounded_tuple(values, name)
        if self.available_decisions != tuple(HumanReviewDecision):
            raise ValueError("Decision package must expose all controlled decisions")
        if self.state is not ImplementationState.WAITING_FOR_HUMAN_REVIEW:
            raise ValueError("Decision package must stop at human review")
        if self.approval_recorded:
            raise ValueError("Decision package cannot pre-record approval")
        _utc(self.created_at, "created_at")


@dataclass(frozen=True)
class ManagedProductTask:
    task_id: str
    project_id: str
    repository: str
    branch: str
    expected_commit_sha: str
    milestone: str
    implementation_request: str
    provider: str
    requirement_ids: tuple[str, ...] = ()
    roadmap_item_id: str | None = None
    base_branch: str = "main"
    allowed_paths: tuple[str, ...] = ()
    implementation_actor: str | None = None
    workspace_id: str | None = None
    execution_id: str | None = None
    review_status: str = "NOT_REQUESTED"
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    commit_sha: str | None = None
    pull_request_id: int | None = None
    pull_request_url: str | None = None
    state: ImplementationState = ImplementationState.REQUESTED
    workspace: WorkspaceResult | None = None
    verification: tuple[VerificationStepResult, ...] = ()
    provider_result: ProviderImplementationResult | None = None
    commit_result: CommitResult | None = None
    push_result: PushResult | None = None
    pull_request: PullRequestResult | None = None
    review_package: ReviewPackage | None = None
    failure: str | None = None
    resume_from: ImplementationState | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    reviewer: str | None = None
    reviewed_commit_sha: str | None = None
    pending_actions: tuple[str, ...] = ("prepare workspace",)

    def __post_init__(self) -> None:
        for value, name in (
            (self.task_id, "task ID"),
            (self.project_id, "project ID"),
            (self.repository, "repository"),
            (self.branch, "branch"),
            (self.base_branch, "base branch"),
            (self.milestone, "milestone"),
            (self.implementation_request, "implementation request"),
            (self.provider, "provider"),
        ):
            _text(value, name)
        for value, name in ((self.task_id, "task ID"), (self.project_id, "project ID")):
            path = PurePosixPath(value.replace("\\", "/"))
            if path.is_absolute() or len(path.parts) != 1 or value in {".", ".."}:
                raise ValueError(f"{name} must be a safe single component")
        if len(self.expected_commit_sha) != 40 or any(
            character not in "0123456789abcdef" for character in self.expected_commit_sha.lower()
        ):
            raise ValueError("Expected commit SHA must be a 40-character hexadecimal SHA")
        _paths(self.allowed_paths, "allowed paths")
        _bounded_tuple(self.requirement_ids, "requirement IDs")
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")
        if self.completed_at is not None:
            _utc(self.completed_at, "completed_at")


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT or "\0" in value:
        raise ValueError(f"{name} must be a bounded non-empty string")


def _bounded_tuple(values: tuple[str, ...], name: str) -> None:
    if not isinstance(values, tuple) or len(values) > MAX_ITEMS:
        raise ValueError(f"{name} must be a bounded immutable tuple")
    for value in values:
        _text(value, name)


def _paths(values: tuple[str, ...], name: str) -> None:
    _bounded_tuple(values, name)
    for value in values:
        path = PurePosixPath(value.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
            raise ValueError(f"Unsafe path in {name}: {value}")


def _utc(value: datetime, name: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{name} must use timezone-aware UTC")
