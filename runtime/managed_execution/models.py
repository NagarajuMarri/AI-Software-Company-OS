"""Immutable managed-product execution values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping

from runtime.managed_execution.errors import ExecutionValidationError

MAX_ITEMS = 100
MAX_CHANGED_FILES = 500
MAX_CHANGED_LINES = 100_000
MAX_TIMEOUT_SECONDS = 86_400


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 10_000:
        raise ExecutionValidationError(f"{name} must be a bounded non-empty string")


def _tuple(value: tuple, name: str, *, required: bool = False) -> None:
    if not isinstance(value, tuple):
        raise ExecutionValidationError(f"{name} must be an immutable tuple")
    if required and not value:
        raise ExecutionValidationError(f"{name} must not be empty")
    if len(value) > MAX_ITEMS:
        raise ExecutionValidationError(f"{name} exceeds {MAX_ITEMS} items")


def _utc(value: datetime, name: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise ExecutionValidationError(f"{name} must be timezone-aware UTC")
    if offset.total_seconds() != 0:
        raise ExecutionValidationError(f"{name} must use UTC")


class ExecutionMode(str, Enum):
    PLAN_ONLY = "PLAN_ONLY"
    DRY_RUN = "DRY_RUN"
    SIMULATED = "SIMULATED"
    CONTROLLED_WRITE = "CONTROLLED_WRITE"


class ExecutionPlanStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ExecutionOperationPhase(str, Enum):
    PREPARED = "PREPARED"
    WORKSPACE_READY = "WORKSPACE_READY"
    BRANCH_READY = "BRANCH_READY"
    RUNTIME_CREATED = "RUNTIME_CREATED"
    CODING_SUBMITTED = "CODING_SUBMITTED"
    CODING_COMPLETED = "CODING_COMPLETED"
    QUALITY_GATES_COMPLETED = "QUALITY_GATES_COMPLETED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    COMMIT_CREATED = "COMMIT_CREATED"
    PUSH_COMPLETED = "PUSH_COMPLETED"
    PR_CREATED = "PR_CREATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class WorkspaceLifecycle(str, Enum):
    REQUESTED = "REQUESTED"
    PREPARING = "PREPARING"
    READY = "READY"
    IN_USE = "IN_USE"
    DIRTY = "DIRTY"
    ARCHIVED = "ARCHIVED"
    CLEANED = "CLEANED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class GateStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    NOT_RUN = "NOT_RUN"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class ReviewDecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED"


@dataclass(frozen=True)
class ManagedProductExecutionRequest:
    execution_request_id: str
    project_id: str
    proposal_id: str
    milestone_id: str
    selected_task_ids: tuple[str, ...]
    requested_by: str
    requested_at: datetime
    correlation_id: str
    base_branch: str
    requested_branch_name: str
    execution_mode: ExecutionMode
    quality_gate_profile_id: str
    coding_provider_capability: str
    workspace_policy_id: str
    human_approval_policy_id: str
    maximum_changed_files: int | None = None
    maximum_changed_lines: int | None = None
    timeout_seconds: int | None = None
    cost_limit_metadata: tuple[tuple[str, str], ...] = ()
    execution_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.execution_request_id, "execution_request_id"),
            (self.project_id, "project_id"),
            (self.proposal_id, "proposal_id"),
            (self.milestone_id, "milestone_id"),
            (self.requested_by, "requested_by"),
            (self.correlation_id, "correlation_id"),
            (self.base_branch, "base_branch"),
            (self.requested_branch_name, "requested_branch_name"),
            (self.quality_gate_profile_id, "quality_gate_profile_id"),
            (self.coding_provider_capability, "coding_provider_capability"),
            (self.workspace_policy_id, "workspace_policy_id"),
            (self.human_approval_policy_id, "human_approval_policy_id"),
        ):
            _required(value, name)
        _tuple(self.selected_task_ids, "selected_task_ids", required=True)
        _tuple(self.cost_limit_metadata, "cost_limit_metadata")
        _tuple(self.execution_notes, "execution_notes")
        _utc(self.requested_at, "requested_at")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise ExecutionValidationError("execution_mode must be an ExecutionMode")
        for limit_value, maximum, limit_name in (
            (self.maximum_changed_files, MAX_CHANGED_FILES, "maximum_changed_files"),
            (self.maximum_changed_lines, MAX_CHANGED_LINES, "maximum_changed_lines"),
            (self.timeout_seconds, MAX_TIMEOUT_SECONDS, "timeout_seconds"),
        ):
            if limit_value is not None and (
                not isinstance(limit_value, int) or not 0 < limit_value <= maximum
            ):
                raise ExecutionValidationError(
                    f"{limit_name} must be positive and bounded")


@dataclass(frozen=True)
class TaskExecution:
    project_task_id: str
    runtime_work_item_id: str
    title: str
    objective: str
    dependencies: tuple[str, ...]
    role_requirements: tuple[str, ...]
    capability_requirements: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    candidate_files: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    allowed_commands: tuple[tuple[str, ...], ...]
    quality_gates: tuple[str, ...]
    maximum_changed_files: int
    maximum_changed_lines: int
    timeout_seconds: int
    requires_human_review: bool
    expected_artifacts: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionDecision:
    decision_id: str
    plan_id: str
    plan_version: int
    status: ReviewDecisionStatus
    actor: str
    decided_at: datetime
    reason: str | None = None


@dataclass(frozen=True)
class ManagedProductExecutionPlan:
    execution_plan_id: str
    version: int
    execution_request_id: str
    project_id: str
    proposal_id: str
    milestone_id: str
    ordered_task_executions: tuple[TaskExecution, ...]
    dependency_graph: tuple[tuple[str, tuple[str, ...]], ...]
    runtime_work_package_id: str
    expected_runtime_work_item_ids: tuple[str, ...]
    role_requirements: tuple[str, ...]
    capability_requirements: tuple[str, ...]
    repository_identity: str
    base_branch: str
    feature_branch: str
    workspace_identity: str
    coding_provider_requirement: str
    quality_gates: tuple[str, ...]
    limits: tuple[tuple[str, int], ...]
    required_approvals: tuple[str, ...]
    generated_at: datetime
    status: ExecutionPlanStatus = ExecutionPlanStatus.AWAITING_APPROVAL
    planning_evidence_references: tuple[str, ...] = ()
    decisions: tuple[ExecutionDecision, ...] = ()


@dataclass(frozen=True)
class ChangePolicy:
    policy_id: str
    allowed_path_prefixes: tuple[str, ...]
    forbidden_path_prefixes: tuple[str, ...]
    maximum_changed_files: int = 25
    maximum_additions: int = 2_000
    maximum_deletions: int = 1_000
    forbidden_file_types: tuple[str, ...] = (".pem", ".key", ".p12", ".env")
    protected_configuration_files: tuple[str, ...] = (
        ".github/workflows/",
        "deploy",
        "infrastructure",
        "payment",
        "migrations/",
    )
    secret_patterns: tuple[str, ...] = ("SECRET", "TOKEN", "PASSWORD", "PRIVATE KEY")
    allow_dependency_files: bool = False
    allow_migrations: bool = False
    allow_ci_workflows: bool = False
    allow_generated_files: bool = False
    allow_binary_files: bool = False


@dataclass(frozen=True)
class QualityGate:
    gate_id: str
    command: tuple[str, ...]
    timeout_seconds: int
    required: bool = True
    expected_exit_codes: tuple[int, ...] = (0,)


@dataclass(frozen=True)
class QualityGateProfile:
    profile_id: str
    project_id: str
    ordered_gates: tuple[QualityGate, ...]
    allowed_executables: tuple[str, ...]
    environment_allow_list: tuple[str, ...] = ()
    artifact_capture_policy: str = "bounded-output"
    redaction_rules: tuple[str, ...] = ()
    failure_policy: str = "stop-required"


@dataclass(frozen=True)
class QualityGateResult:
    gate_execution_id: str
    gate_id: str
    status: GateStatus
    exit_code: int | None
    stdout: str
    stderr: str
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class ManagedCodingRequest:
    external_task_id: str
    project_id: str
    workspace_id: str
    branch: str
    objective: str
    acceptance_criteria: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    candidate_files: tuple[str, ...]
    allowed_commands: tuple[tuple[str, ...], ...]
    quality_gates: tuple[str, ...]
    timeout_seconds: int
    maximum_changed_files: int
    maximum_changed_lines: int
    expected_artifacts: tuple[str, ...]
    correlation_id: str
    provider_idempotency_key: str


@dataclass(frozen=True)
class ValidatedCodingResult:
    external_task_id: str
    workspace_id: str
    status: str
    changed_files: tuple[str, ...]
    additions: int
    deletions: int
    executed_gates: tuple[str, ...]
    artifacts: tuple[str, ...]
    summary: str
    provider_task_id: str
    progress_sequences: tuple[int, ...]


@dataclass(frozen=True)
class WorkspaceRecord:
    workspace_id: str
    project_id: str
    local_path: str
    repository_identity: str
    base_branch: str
    lifecycle: WorkspaceLifecycle
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RuntimeTaskMapping:
    project_task_id: str
    runtime_work_item_id: str
    runtime_work_package_id: str
    correlation_id: str
    causation_id: str


@dataclass(frozen=True)
class ReviewEvidence:
    evidence_id: str
    execution_plan_id: str
    project_id: str
    task_ids: tuple[str, ...]
    workspace_id: str
    branch: str
    base_commit: str
    resulting_commit: str | None
    changed_files: tuple[str, ...]
    additions: int
    deletions: int
    provider_result_reference: str
    quality_gate_results: tuple[QualityGateResult, ...]
    acceptance_criteria_mapping: tuple[tuple[str, tuple[str, ...]], ...]
    unresolved_risks: tuple[str, ...]
    warnings: tuple[str, ...]
    policy_exceptions: tuple[str, ...]
    reviewer_required_flags: tuple[str, ...]
    generated_at: datetime
    integrity_digest: str


@dataclass(frozen=True)
class ManagedExecutionOperation:
    operation_id: str
    project_id: str
    proposal_id: str
    milestone_id: str
    task_ids: tuple[str, ...]
    runtime_ids: tuple[str, ...]
    workspace_id: str
    branch: str
    phase: ExecutionOperationPhase
    external_coding_task_ids: tuple[str, ...] = ()
    provider_operation_ids: tuple[str, ...] = ()
    gate_execution_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    approval_ids: tuple[str, ...] = ()
    commit_sha: str | None = None
    push_state: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    failure_details: str | None = None
    schema_version: int = 1


@dataclass(frozen=True)
class EligibilityReason:
    code: str
    message: str


@dataclass(frozen=True)
class TaskEligibility:
    task_id: str
    eligible: bool
    reasons: tuple[EligibilityReason, ...]
