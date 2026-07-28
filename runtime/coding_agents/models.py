from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CodingAgentResultStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class CodingAgentTaskRequest:
    task_id: str
    project_id: str
    repository_reference: str
    workspace_reference: str
    branch: str
    objective: str
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    correlation_id: str
    timeout_seconds: int
    provider_configuration_reference: str | None = None


@dataclass(frozen=True)
class CodingAgentProgress:
    task_id: str
    sequence: int
    stage: str
    message: str
    timestamp: datetime
    artifact_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodingAgentTaskResult:
    task_id: str
    provider_task_id: str
    status: CodingAgentResultStatus
    summary: str
    changed_paths: tuple[str, ...]
    commit_sha: str | None
    test_results: tuple[str, ...]
    generated_artifacts: tuple[str, ...]
    failure_code: str | None
    started_at: datetime
    completed_at: datetime
