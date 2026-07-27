from datetime import datetime, timezone
from typing import Mapping

import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.exceptions import (
    AgentNotFoundError,
    DuplicateExecutionError,
    DuplicateExecutorError,
    ExecutionFailedError,
    ExecutionNotFoundError,
    ExecutorNotFoundError,
    InvalidAssignmentStateTransitionError,
    InvalidExecutionStateTransitionError,
    RuntimeDomainError,
    ValidationError,
)
from runtime.execution.executor import BaseExecutor, DeterministicExecutor
from runtime.execution.registry import ExecutorRegistry
from runtime.execution.result import ExecutionResult, ExecutionStatus
from runtime.execution.service import ExecutionService
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.assignment import AssignmentStatus
from runtime.orchestration.orchestrator import Orchestrator


class ExplodingExecutor(BaseExecutor):
    executor_id = "exploding"
    supported_roles = [AgentRole.BACKEND_ENGINEER]
    supported_capabilities = ["python"]

    def execute(self, context: Mapping[str, object]) -> ExecutionResult:
        raise RuntimeError("provider exploded")


def build_execution_runtime(
    executor: BaseExecutor | None = None,
) -> tuple[
    RuntimeEngine,
    AgentRegistry,
    Orchestrator,
    ExecutorRegistry,
    ExecutionService,
    AgentMetadata,
]:
    engine = RuntimeEngine()
    registry = AgentRegistry()
    orchestrator = Orchestrator(engine, registry)
    executor_registry = ExecutorRegistry()
    service = ExecutionService(orchestrator, executor_registry)
    python = AgentCapability(
        "python",
        "Python",
        "Execute Python work",
        "1.0",
    )
    worker = registry.register_agent(
        AgentMetadata(
            id="agent",
            display_name="Agent",
            role=AgentRole.BACKEND_ENGINEER,
            description="Execution agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=[python],
        )
    )
    engine.create_work_package("wp", "Package", "Description", "owner")
    engine.add_work_item("wp", "wi", "Work", "Execute work")
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    orchestrator.assign_work_item(
        "assignment",
        "wp",
        "wi",
        AgentRole.BACKEND_ENGINEER,
        ["python"],
    )
    if executor is not None:
        executor_registry.register_executor(executor)
    return (
        engine,
        registry,
        orchestrator,
        executor_registry,
        service,
        worker,
    )


def deterministic_executor(
    *,
    should_fail: bool = False,
) -> DeterministicExecutor:
    return DeterministicExecutor(
        executor_id="deterministic",
        supported_roles=[AgentRole.BACKEND_ENGINEER],
        supported_capabilities=["python"],
        deterministic_output="stable output",
        should_fail=should_fail,
        failure_message="stable failure",
    )


def test_executor_registration_lookup_and_defensive_list() -> None:
    registry = ExecutorRegistry()
    executor = registry.register_executor(deterministic_executor())

    assert registry.get_executor("deterministic") is executor
    listed = registry.list_executors()
    listed.clear()
    assert registry.list_executors() == [executor]


def test_duplicate_executor_prevention() -> None:
    registry = ExecutorRegistry()
    registry.register_executor(deterministic_executor())

    with pytest.raises(DuplicateExecutorError):
        registry.register_executor(deterministic_executor())


def test_compatible_executor_selection() -> None:
    _, _, _, registry, _, worker = build_execution_runtime()
    incompatible = DeterministicExecutor(
        "frontend",
        [AgentRole.FRONTEND_ENGINEER],
        ["python"],
    )
    compatible = deterministic_executor()
    registry.register_executor(incompatible)
    registry.register_executor(compatible)

    assert registry.select_executor(worker) is compatible


@pytest.mark.parametrize(
    "executor",
    [
        DeterministicExecutor(
            "wrong-role",
            [AgentRole.QA_ENGINEER],
            ["python"],
        ),
        DeterministicExecutor(
            "wrong-capability",
            [AgentRole.BACKEND_ENGINEER],
            ["javascript"],
        ),
    ],
)
def test_incompatible_executor_rejection(executor: BaseExecutor) -> None:
    engine, _, _, registry, service, _ = build_execution_runtime(executor)

    with pytest.raises(ExecutorNotFoundError):
        service.execute_assignment("execution", "assignment")

    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.ASSIGNED
    assert service.list_executions() == []


def test_successful_execution_is_deterministic_and_stops_at_review() -> None:
    engine, _, orchestrator, _, service, worker = build_execution_runtime(
        deterministic_executor()
    )

    result = service.execute_assignment(
        "execution",
        "assignment",
        {"ignored_provider_detail": "safe"},
    )

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.output == "stable output"
    assert result.error is None
    assert result.started_at is not None
    assert result.completed_at is not None
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.REVIEW
    assert orchestrator.get_assignment("assignment").status == AssignmentStatus.ACTIVE
    assert worker.state == AgentState.BUSY


def test_failed_execution_records_details_and_leaves_work_running() -> None:
    engine, _, orchestrator, _, service, worker = build_execution_runtime(
        deterministic_executor(should_fail=True)
    )

    with pytest.raises(ExecutionFailedError, match="stable failure"):
        service.execute_assignment("execution", "assignment")

    result = service.get_execution("execution")
    assert result.status == ExecutionStatus.FAILED
    assert result.error == "stable failure"
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.RUNNING
    assert orchestrator.get_assignment("assignment").status == AssignmentStatus.ACTIVE
    assert worker.state == AgentState.BUSY


def test_provider_exception_has_explicit_failure_policy() -> None:
    engine, _, orchestrator, _, service, worker = build_execution_runtime(
        ExplodingExecutor()
    )

    with pytest.raises(ExecutionFailedError, match="provider exploded"):
        service.execute_assignment("execution", "assignment")

    result = service.get_execution("execution")
    assert result.status == ExecutionStatus.FAILED
    assert result.error == "provider exploded"
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.RUNNING
    assert orchestrator.get_assignment("assignment").status == AssignmentStatus.ACTIVE
    assert worker.state == AgentState.BUSY


def test_assignment_must_be_active() -> None:
    engine, _, orchestrator, _, service, _ = build_execution_runtime(
        deterministic_executor()
    )
    orchestrator.cancel_assignment("assignment")

    with pytest.raises(InvalidAssignmentStateTransitionError):
        service.execute_assignment("execution", "assignment")

    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.READY
    assert service.list_executions() == []


def test_work_item_must_be_assigned() -> None:
    engine, _, _, _, service, _ = build_execution_runtime(
        deterministic_executor()
    )
    engine.get_work_item("wp", "wi").lifecycle_state = LifecycleState.RUNNING

    with pytest.raises(InvalidExecutionStateTransitionError):
        service.execute_assignment("execution", "assignment")

    assert service.list_executions() == []


def test_assigned_agent_must_exist() -> None:
    engine, registry, _, _, service, worker = build_execution_runtime(
        deterministic_executor()
    )
    registry.remove_agent(worker.id)

    with pytest.raises(AgentNotFoundError):
        service.execute_assignment("execution", "assignment")

    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.ASSIGNED
    assert service.list_executions() == []


def test_duplicate_execution_is_rejected_before_mutation() -> None:
    engine, _, _, _, service, _ = build_execution_runtime(
        deterministic_executor()
    )
    service.execute_assignment("execution", "assignment")
    state = engine.get_work_item("wp", "wi").lifecycle_state

    with pytest.raises(DuplicateExecutionError):
        service.execute_assignment("execution", "assignment")

    assert engine.get_work_item("wp", "wi").lifecycle_state == state
    assert len(service.list_executions()) == 1


def test_execution_retrieval_listing_and_defensive_copies() -> None:
    _, _, _, _, service, _ = build_execution_runtime(
        deterministic_executor()
    )
    result = service.execute_assignment("execution", "assignment")

    assert service.get_execution("execution") is result
    assert service.list_executions_for_assignment("assignment") == [result]
    listed = service.list_executions()
    listed.clear()
    assert service.list_executions() == [result]
    with pytest.raises(ExecutionNotFoundError):
        service.get_execution("missing")


def test_cancel_execution_preserves_running_work_and_assignment() -> None:
    engine, _, orchestrator, _, service, worker = build_execution_runtime()
    execution = ExecutionResult(
        "execution",
        "assignment",
        "wi",
        worker.id,
    )
    execution.mark_running()
    service._executions[execution.id] = execution
    engine.change_work_item_state("wp", "wi", LifecycleState.RUNNING)

    cancelled = service.cancel_execution(execution.id)

    assert cancelled.status == ExecutionStatus.CANCELLED
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.RUNNING
    assert orchestrator.get_assignment("assignment").status == AssignmentStatus.ACTIVE
    assert worker.state == AgentState.BUSY


def test_pre_execution_failure_is_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _, orchestrator, _, service, worker = build_execution_runtime(
        deterministic_executor()
    )
    work_item = engine.get_work_item("wp", "wi")

    def fail_mark_running(result: ExecutionResult) -> None:
        raise RuntimeError("injected start failure")

    monkeypatch.setattr(ExecutionResult, "mark_running", fail_mark_running)
    with pytest.raises(RuntimeError, match="injected"):
        service.execute_assignment("execution", "assignment")

    assert work_item.lifecycle_state == LifecycleState.ASSIGNED
    assert service.list_executions() == []
    assert orchestrator.get_assignment("assignment").status == AssignmentStatus.ACTIVE
    assert worker.state == AgentState.BUSY


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DeterministicExecutor("", [], []),
        lambda: DeterministicExecutor(
            "executor",
            ["BACKEND_ENGINEER"],  # type: ignore[list-item]
            [],
        ),
        lambda: DeterministicExecutor("executor", [], [""]),
        lambda: ExecutionResult("", "a", "wi", "agent"),
        lambda: ExecutionResult(
            "e",
            "a",
            "wi",
            "agent",
            status="RUNNING",  # type: ignore[arg-type]
        ),
        lambda: ExecutionResult(
            "e",
            "a",
            "wi",
            "agent",
            status=ExecutionStatus.RUNNING,
        ),
        lambda: ExecutionResult(
            "e",
            "a",
            "wi",
            "agent",
            status=ExecutionStatus.SUCCEEDED,
            output="output",
            started_at=datetime.now(timezone.utc),
        ),
    ],
)
def test_execution_models_validate_invalid_values(factory: object) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_execution_exception_hierarchy() -> None:
    for error in (
        ExecutorNotFoundError,
        DuplicateExecutorError,
        ExecutionNotFoundError,
        DuplicateExecutionError,
        InvalidExecutionStateTransitionError,
        ExecutionFailedError,
    ):
        assert issubclass(error, RuntimeDomainError)
