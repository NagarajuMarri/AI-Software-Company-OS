"""Deterministic execution service for active work assignments."""

from typing import Mapping

from runtime.agents.registry import AgentRegistry
from runtime.exceptions import (
    DuplicateExecutionError,
    ExecutionFailedError,
    ExecutionNotFoundError,
    InvalidAssignmentStateTransitionError,
    InvalidExecutionStateTransitionError,
    ValidationError,
)
from runtime.execution.registry import ExecutorRegistry
from runtime.execution.result import ExecutionResult, ExecutionStatus
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.assignment import AssignmentStatus
from runtime.orchestration.orchestrator import Orchestrator
from runtime.validation import validate_required_string


class ExecutionService:
    """Execute active assignments synchronously through compatible executors."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        executor_registry: ExecutorRegistry,
    ) -> None:
        if not isinstance(orchestrator, Orchestrator):
            raise ValidationError("orchestrator must be an Orchestrator value")
        if not isinstance(executor_registry, ExecutorRegistry):
            raise ValidationError(
                "executor_registry must be an ExecutorRegistry value"
            )
        self.orchestrator = orchestrator
        self.executor_registry = executor_registry
        self._executions: dict[str, ExecutionResult] = {}

    @property
    def agent_registry(self) -> AgentRegistry:
        """Expose the orchestrator's shared agent registry."""
        return self.orchestrator.agent_registry

    def execute_assignment(
        self,
        execution_id: str,
        assignment_id: str,
        context: Mapping[str, object] | None = None,
    ) -> ExecutionResult:
        """Execute an active assignment and record a terminal result."""
        validate_required_string(execution_id, "execution_id")
        validate_required_string(assignment_id, "assignment_id")
        if execution_id in self._executions:
            raise DuplicateExecutionError(
                f"Execution {execution_id!r} already exists"
            )
        assignment = self.orchestrator.get_assignment(assignment_id)
        if assignment.status != AssignmentStatus.ACTIVE:
            raise InvalidAssignmentStateTransitionError(
                "Execution requires an ACTIVE assignment"
            )
        work_item = self.orchestrator.runtime_engine.get_work_item(
            assignment.package_id,
            assignment.work_item_id,
        )
        if work_item.lifecycle_state != LifecycleState.ASSIGNED:
            raise InvalidExecutionStateTransitionError(
                "Execution requires work item ASSIGNED"
            )
        agent = self.agent_registry.get_agent(assignment.agent_id)
        executor = self.executor_registry.select_executor(agent, assignment)
        execution = ExecutionResult(
            id=execution_id,
            assignment_id=assignment.id,
            work_item_id=work_item.id,
            agent_id=agent.id,
        )

        package = self.orchestrator.runtime_engine.get_work_package(
            assignment.package_id
        )
        work_item_state = work_item.lifecycle_state
        package_updated_at = package.updated_at
        try:
            self.orchestrator.runtime_engine.change_work_item_state(
                assignment.package_id,
                assignment.work_item_id,
                LifecycleState.RUNNING,
            )
            execution.mark_running()
            self._executions[execution.id] = execution
        except Exception:
            work_item.lifecycle_state = work_item_state
            package.updated_at = package_updated_at
            self._executions.pop(execution.id, None)
            raise

        execution_context: dict[str, object] = dict(context or {})
        running_package_updated_at = package.updated_at
        execution_context.update(
            {
                "execution_id": execution.id,
                "assignment_id": assignment.id,
                "work_item_id": work_item.id,
                "agent_id": agent.id,
                "started_at": execution.started_at,
                "work_item": work_item,
                "agent": agent,
            }
        )
        try:
            provider_result = executor.execute(execution_context)
            self._validate_provider_result(execution, provider_result)
            if provider_result.status == ExecutionStatus.FAILED:
                execution.mark_failed(
                    provider_result.error or "Executor reported failure"
                )
                raise ExecutionFailedError(execution.error)
            if provider_result.status != ExecutionStatus.SUCCEEDED:
                raise ValidationError(
                    "executor must return SUCCEEDED or FAILED"
                )
            self.orchestrator.runtime_engine.change_work_item_state(
                assignment.package_id,
                assignment.work_item_id,
                LifecycleState.REVIEW,
            )
            execution.mark_succeeded(
                provider_result.output or "Execution succeeded"
            )
            return execution
        except ExecutionFailedError:
            raise
        except Exception as error:
            work_item.lifecycle_state = LifecycleState.RUNNING
            package.updated_at = running_package_updated_at
            if execution.status == ExecutionStatus.RUNNING:
                execution.mark_failed(str(error) or type(error).__name__)
            raise ExecutionFailedError(execution.error) from error

    def cancel_execution(self, execution_id: str) -> ExecutionResult:
        """Cancel a created/running execution without rewinding work."""
        execution = self.get_execution(execution_id)
        execution.cancel()
        return execution

    def get_execution(self, execution_id: str) -> ExecutionResult:
        """Retrieve an execution by identifier."""
        validate_required_string(execution_id, "execution_id")
        if execution_id not in self._executions:
            raise ExecutionNotFoundError(
                f"Execution {execution_id!r} was not found"
            )
        return self._executions[execution_id]

    def list_executions(self) -> list[ExecutionResult]:
        """Return executions in creation order."""
        return list(self._executions.values())

    def list_executions_for_assignment(
        self,
        assignment_id: str,
    ) -> list[ExecutionResult]:
        """Return execution history for an existing assignment."""
        self.orchestrator.get_assignment(assignment_id)
        return [
            execution
            for execution in self._executions.values()
            if execution.assignment_id == assignment_id
        ]

    @staticmethod
    def _validate_provider_result(
        execution: ExecutionResult,
        result: object,
    ) -> None:
        if not isinstance(result, ExecutionResult):
            raise ValidationError(
                "executor must return an ExecutionResult value"
            )
        if (
            result.id != execution.id
            or result.assignment_id != execution.assignment_id
            or result.work_item_id != execution.work_item_id
            or result.agent_id != execution.agent_id
        ):
            raise ValidationError(
                "executor result relationships do not match execution context"
            )
