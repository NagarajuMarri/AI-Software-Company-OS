from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ExternalTaskStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ApprovalStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class ExternalOperationStatus(str, Enum):
    PLANNED = "PLANNED"
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass
class ExternalTask:
    task_id: str
    project_id: str
    work_item_id: str
    task_type: str
    title: str
    description: str
    provider_id: str | None
    workspace_id: str | None
    repository_reference: str
    base_branch: str
    working_branch: str
    status: ExternalTaskStatus
    requested_capabilities: tuple[str, ...]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    retry_count: int = 0
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUESTED
    correlation_id: str | None = None
    causation_id: str | None = None
    result_reference: str | None = None


@dataclass(frozen=True)
class ApprovalDecision:
    task_id: str
    decision: ApprovalStatus
    approver_id: str
    reason: str
    decided_at: datetime


@dataclass
class ExternalOperation:
    operation_id: str
    task_id: str
    operation_type: str
    status: ExternalOperationStatus
    created_at: datetime
    updated_at: datetime
    attempt: int = 1
    failure_code: str | None = None
