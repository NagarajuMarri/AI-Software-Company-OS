"""In-memory registry and deterministic selection for executors."""

from runtime.agents.metadata import AgentMetadata
from runtime.exceptions import (
    DuplicateExecutorError,
    ExecutorNotFoundError,
    ValidationError,
)
from runtime.execution.executor import BaseExecutor
from runtime.validation import validate_required_string


class ExecutorRegistry:
    """Register and select provider-neutral executors."""

    def __init__(self) -> None:
        self._executors: dict[str, BaseExecutor] = {}

    def register_executor(self, executor: BaseExecutor) -> BaseExecutor:
        """Register an executor without overwriting its identifier."""
        if not isinstance(executor, BaseExecutor):
            raise ValidationError("executor must implement BaseExecutor")
        validate_required_string(executor.executor_id, "executor_id")
        if executor.executor_id in self._executors:
            raise DuplicateExecutorError(
                f"Executor {executor.executor_id!r} is already registered"
            )
        self._executors[executor.executor_id] = executor
        return executor

    def remove_executor(self, executor_id: str) -> BaseExecutor:
        """Remove and return an executor."""
        executor = self.get_executor(executor_id)
        del self._executors[executor_id]
        return executor

    def get_executor(self, executor_id: str) -> BaseExecutor:
        """Retrieve an executor by identifier."""
        validate_required_string(executor_id, "executor_id")
        if executor_id not in self._executors:
            raise ExecutorNotFoundError(
                f"Executor {executor_id!r} is not registered"
            )
        return self._executors[executor_id]

    def list_executors(self) -> list[BaseExecutor]:
        """Return executors in registration order."""
        return list(self._executors.values())

    def select_executor(self, agent: AgentMetadata) -> BaseExecutor:
        """Select the first executor compatible with an assigned agent."""
        if not isinstance(agent, AgentMetadata):
            raise ValidationError("agent must be an AgentMetadata value")
        required_capabilities = {
            capability.id for capability in agent.supported_capabilities
        }
        for executor in self._executors.values():
            if agent.role not in executor.supported_roles:
                continue
            if not required_capabilities.issubset(
                set(executor.supported_capabilities)
            ):
                continue
            return executor
        raise ExecutorNotFoundError(
            f"No compatible executor is registered for agent {agent.id!r}"
        )
