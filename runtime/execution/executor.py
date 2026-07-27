"""Provider-neutral executor interfaces and deterministic implementation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from runtime.agents.role import AgentRole, validate_agent_role
from runtime.exceptions import ValidationError
from runtime.execution.result import ExecutionResult, ExecutionStatus
from runtime.validation import validate_required_string


class BaseExecutor(ABC):
    """Provider-neutral synchronous executor contract."""

    executor_id: str
    supported_roles: list[AgentRole]
    supported_capabilities: list[str]

    @abstractmethod
    def execute(self, context: Mapping[str, object]) -> ExecutionResult:
        """Execute a validated runtime context and return a terminal result."""


@dataclass
class DeterministicExecutor(BaseExecutor):
    """Predictable local executor for tests and runtime validation."""

    executor_id: str
    supported_roles: list[AgentRole] = field(default_factory=list)
    supported_capabilities: list[str] = field(default_factory=list)
    deterministic_output: str = "deterministic execution completed"
    should_fail: bool = False
    failure_message: str = "deterministic execution failed"

    def __post_init__(self) -> None:
        validate_required_string(self.executor_id, "executor_id")
        for role in self.supported_roles:
            validate_agent_role(role)
        if len(self.supported_roles) != len(set(self.supported_roles)):
            raise ValidationError("supported_roles must not contain duplicates")
        for capability_id in self.supported_capabilities:
            validate_required_string(
                capability_id,
                "supported_capabilities",
            )
        if len(self.supported_capabilities) != len(
            set(self.supported_capabilities)
        ):
            raise ValidationError(
                "supported_capabilities must not contain duplicates"
            )
        validate_required_string(
            self.deterministic_output,
            "deterministic_output",
        )
        validate_required_string(self.failure_message, "failure_message")
        if not isinstance(self.should_fail, bool):
            raise ValidationError("should_fail must be a boolean")

    def execute(self, context: Mapping[str, object]) -> ExecutionResult:
        """Return the configured deterministic terminal result."""
        execution_id = context.get("execution_id")
        assignment_id = context.get("assignment_id")
        work_item_id = context.get("work_item_id")
        agent_id = context.get("agent_id")
        started_at = context.get("started_at")
        validate_required_string(execution_id, "context.execution_id")
        validate_required_string(assignment_id, "context.assignment_id")
        validate_required_string(work_item_id, "context.work_item_id")
        validate_required_string(agent_id, "context.agent_id")
        if not isinstance(started_at, datetime):
            raise ValidationError("context.started_at must be a datetime")

        now = datetime.now(timezone.utc)
        if self.should_fail:
            return ExecutionResult(
                id=execution_id,
                assignment_id=assignment_id,
                work_item_id=work_item_id,
                agent_id=agent_id,
                status=ExecutionStatus.FAILED,
                error=self.failure_message,
                started_at=started_at,
                completed_at=now,
            )
        return ExecutionResult(
            id=execution_id,
            assignment_id=assignment_id,
            work_item_id=work_item_id,
            agent_id=agent_id,
            status=ExecutionStatus.SUCCEEDED,
            output=self.deterministic_output,
            started_at=started_at,
            completed_at=now,
        )
