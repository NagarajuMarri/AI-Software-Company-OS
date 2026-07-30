"""Immutable values for durable coding-provider execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderCapability(str, Enum):
    CODE_GENERATION = "CODE_GENERATION"
    CODE_MODIFICATION = "CODE_MODIFICATION"
    TEST_GENERATION = "TEST_GENERATION"
    DOCUMENTATION = "DOCUMENTATION"
    REPOSITORY_ANALYSIS = "REPOSITORY_ANALYSIS"
    STRUCTURED_PROGRESS = "STRUCTURED_PROGRESS"
    IDEMPOTENT_SUBMISSION = "IDEMPOTENT_SUBMISSION"
    CANCELLATION = "CANCELLATION"
    RESULT_ARTIFACTS = "RESULT_ARTIFACTS"


class ProviderOperationState(str, Enum):
    PREPARED = "PREPARED"
    SUBMISSION_IN_PROGRESS = "SUBMISSION_IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    RESULT_AVAILABLE = "RESULT_AVAILABLE"
    RESULT_ACCEPTED = "RESULT_ACCEPTED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLED = "CANCELLED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    TIMED_OUT = "TIMED_OUT"
    UNCERTAIN = "UNCERTAIN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ProviderResultStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class FileOperationKind(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass(frozen=True)
class ProviderConfiguration:
    provider_id: str
    enabled: bool = False
    api_key_environment: str = "OPENAI_API_KEY"
    model: str | None = None
    request_timeout_seconds: int = 120
    maximum_attempts: int = 1
    maximum_prompt_bytes: int = 64_000
    maximum_output_bytes: int = 128_000
    organization_id: str | None = None
    project_id: str | None = None
    live_operation_confirmed: bool = False


@dataclass(frozen=True)
class ContextLimits:
    maximum_files: int = 20
    maximum_bytes_per_file: int = 16_000
    maximum_total_bytes: int = 64_000
    maximum_evidence_items: int = 20
    maximum_prompt_bytes: int = 80_000


@dataclass(frozen=True)
class CodingContextFile:
    path: str
    content: str
    truncated: bool = False


@dataclass(frozen=True)
class CodingContextPackage:
    project_id: str
    execution_plan_id: str
    plan_version: int
    managed_task_id: str
    workspace_id: str
    branch: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    quality_gate_commands: tuple[tuple[str, ...], ...]
    files: tuple[CodingContextFile, ...]
    evidence: tuple[str, ...]
    context_digest: str
    byte_count: int


@dataclass(frozen=True)
class ProviderTaskRequest:
    external_task_id: str
    provider_operation_id: str
    provider_idempotency_key: str
    project_id: str
    execution_plan_id: str
    plan_version: int
    managed_task_id: str
    workspace_id: str
    branch: str
    request_digest: str
    context_digest: str
    context: CodingContextPackage
    timeout_seconds: int
    maximum_output_bytes: int


@dataclass(frozen=True)
class FileOperation:
    kind: FileOperationKind
    path: str
    content: str | None = None


@dataclass(frozen=True)
class ProviderUsage:
    input_units: int | None = None
    output_units: int | None = None
    duration_seconds: float | None = None
    request_count: int = 1
    model: str | None = None
    reported_cost: float | None = None
    currency: str | None = None


@dataclass(frozen=True)
class ProviderTaskResult:
    provider_task_id: str
    external_task_id: str
    workspace_id: str
    branch: str
    status: ProviderResultStatus
    summary: str
    file_operations: tuple[FileOperation, ...]
    executed_activity: tuple[str, ...]
    artifacts: tuple[str, ...]
    warnings: tuple[str, ...]
    unresolved_issues: tuple[str, ...]
    progress_sequences: tuple[int, ...]
    retryable: bool
    usage: ProviderUsage = field(default_factory=ProviderUsage)


@dataclass(frozen=True)
class ProviderProgressEvent:
    provider_operation_id: str
    sequence: int
    event_type: str
    message: str
    timestamp: datetime
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ProviderOperation:
    provider_operation_id: str
    execution_plan_id: str
    plan_version: int
    project_id: str
    managed_task_id: str
    external_task_id: str
    provider_id: str
    provider_idempotency_key: str
    attempt: int
    workspace_id: str
    branch: str
    request_digest: str
    context_digest: str
    state: ProviderOperationState
    provider_task_id: str | None = None
    progress_cursor: int = 0
    result_reference: str | None = None
    retry_count: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    failure_classification: str | None = None
    reconciliation_details: str | None = None
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    schema_version: int = 1
