"""Immutable values for the managed-product implementation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


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


@dataclass(frozen=True)
class VerificationStep:
    name: str
    command: tuple[str, ...]
    required: bool = True
    timeout_seconds: int = 300


@dataclass(frozen=True)
class VerificationStepResult:
    name: str
    status: VerificationStatus
    command: tuple[str, ...]
    exit_code: int | None
    output: str
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class WorkspaceResult:
    workspace_id: str
    path: str
    repository: str
    branch: str
    commit_sha: str
    remotes_removed: bool
    created_at: datetime


@dataclass(frozen=True)
class ProviderImplementationResult:
    execution_id: str
    summary: str
    changed_files: tuple[str, ...]
    known_risks: tuple[str, ...] = ()
    remaining_work: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class PullRequestResult:
    number: int
    url: str
    draft: bool
    metadata: tuple[tuple[str, str], ...] = ()


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
