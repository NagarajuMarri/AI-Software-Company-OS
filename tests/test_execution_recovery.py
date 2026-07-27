import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.exceptions import (
    DuplicateRecoveryError,
    ExecutionFailedError,
    ExecutionNotFoundError,
    ExecutionNotRecoverableError,
    ExecutorNotFoundError,
    RecoveryNotFoundError,
    RuntimeDomainError,
    InvalidLifecycleTransitionError,
    ValidationError,
)
from runtime.execution.executor import DeterministicExecutor
from runtime.execution.recovery import (
    ExecutionRecoveryRecord,
    ExecutionRecoveryService,
    RecoveryAction,
)
from runtime.execution.registry import ExecutorRegistry
from runtime.execution.result import ExecutionStatus
from runtime.execution.service import ExecutionService
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.assignment import AssignmentStatus
from runtime.orchestration.orchestrator import Orchestrator
from runtime.models.work_item import WorkItem


def build_recovery_runtime(
    *,
    unrelated_agent_capability: bool = False,
) -> tuple[
    RuntimeEngine,
    AgentRegistry,
    Orchestrator,
    ExecutorRegistry,
    ExecutionService,
    ExecutionRecoveryService,
]:
    engine = RuntimeEngine()
    agents = AgentRegistry()
    orchestrator = Orchestrator(engine, agents)
    executors = ExecutorRegistry()
    executions = ExecutionService(orchestrator, executors)
    recovery = ExecutionRecoveryService(executions)
    capabilities = [
        AgentCapability("python", "Python", "Python execution", "1.0")
    ]
    if unrelated_agent_capability:
        capabilities.append(
            AgentCapability(
                "kubernetes",
                "Kubernetes",
                "Cluster operations",
                "1.0",
            )
        )
    agents.register_agent(
        AgentMetadata(
            id="agent",
            display_name="Agent",
            role=AgentRole.BACKEND_ENGINEER,
            description="Recovery agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=capabilities,
            priority=7,
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
    return engine, agents, orchestrator, executors, executions, recovery


def failing_executor() -> DeterministicExecutor:
    return DeterministicExecutor(
        "executor",
        [AgentRole.BACKEND_ENGINEER],
        ["python"],
        should_fail=True,
        failure_message="original failure",
    )


def successful_executor() -> DeterministicExecutor:
    return DeterministicExecutor(
        "executor",
        [AgentRole.BACKEND_ENGINEER],
        ["python"],
        deterministic_output="recovered output",
    )


def create_failed_execution(
    executors: ExecutorRegistry,
    executions: ExecutionService,
) -> None:
    executors.register_executor(failing_executor())
    with pytest.raises(ExecutionFailedError):
        executions.execute_assignment("failed", "assignment")


def test_assignment_requirement_snapshot_is_exact_and_immutable() -> None:
    engine = RuntimeEngine()
    agents = AgentRegistry()
    orchestrator = Orchestrator(engine, agents)
    agents.register_agent(
        AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            "Snapshot agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=[
                AgentCapability("python", "Python", "Python", "1"),
                AgentCapability("extra", "Extra", "Unrelated", "1"),
            ],
            priority=11,
        )
    )
    engine.create_work_package("wp", "Package", "Description", "owner")
    engine.add_work_item("wp", "wi", "Work", "Description")
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    requirements = ["python"]

    assignment = orchestrator.assign_work_item(
        "assignment",
        "wp",
        "wi",
        AgentRole.BACKEND_ENGINEER,
        requirements,
    )
    requirements.append("extra")

    assert assignment.required_role == AgentRole.BACKEND_ENGINEER
    assert assignment.required_capabilities == ("python",)
    assert assignment.selection_reason
    assert assignment.selected_agent_priority == 11
    assert assignment.selected_agent_active_assignment_count == 0
    with pytest.raises(AttributeError):
        assignment.required_capabilities = ("extra",)
    with pytest.raises(AttributeError):
        assignment.selection_reason = "changed"


def test_normal_work_item_transition_rejects_recovery_transition() -> None:
    item = WorkItem(
        "wi",
        "Work",
        "Description",
        lifecycle_state=LifecycleState.RUNNING,
    )

    with pytest.raises(InvalidLifecycleTransitionError):
        item.change_state(LifecycleState.ASSIGNED)


def test_runtime_normal_transition_rejects_recovery_transition() -> None:
    engine = RuntimeEngine()
    engine.create_work_package("wp", "Package", "Description", "owner")
    engine.add_work_item("wp", "wi", "Work", "Description")
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    engine.change_work_item_state("wp", "wi", LifecycleState.ASSIGNED)
    engine.change_work_item_state("wp", "wi", LifecycleState.RUNNING)

    with pytest.raises(InvalidLifecycleTransitionError):
        engine.change_work_item_state("wp", "wi", LifecycleState.ASSIGNED)


def test_explicit_recovery_transition_requires_reason_and_updates_timestamp() -> None:
    engine = RuntimeEngine()
    package = engine.create_work_package(
        "wp",
        "Package",
        "Description",
        "owner",
    )
    engine.add_work_item("wp", "wi", "Work", "Description")
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    engine.change_work_item_state("wp", "wi", LifecycleState.ASSIGNED)
    engine.change_work_item_state("wp", "wi", LifecycleState.RUNNING)
    item = engine.get_work_item("wp", "wi")
    before = package.updated_at

    engine.recover_work_item_state(
        "wp",
        "wi",
        LifecycleState.ASSIGNED,
        "Retry failed execution",
    )

    assert item.lifecycle_state == LifecycleState.ASSIGNED
    assert package.updated_at > before


def test_explicit_recovery_requires_non_empty_reason() -> None:
    engine = RuntimeEngine()
    engine.create_work_package("wp", "Package", "Description", "owner")
    engine.add_work_item("wp", "wi", "Work", "Description")
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    engine.change_work_item_state("wp", "wi", LifecycleState.ASSIGNED)
    engine.change_work_item_state("wp", "wi", LifecycleState.RUNNING)
    item = engine.get_work_item("wp", "wi")

    with pytest.raises(ValidationError):
        engine.recover_work_item_state(
            "wp",
            "wi",
            LifecycleState.ASSIGNED,
            " ",
        )
    assert item.lifecycle_state == LifecycleState.RUNNING


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (LifecycleState.REVIEW, LifecycleState.ASSIGNED),
        (LifecycleState.RUNNING, LifecycleState.READY),
        (LifecycleState.COMPLETED, LifecycleState.RUNNING),
    ],
)
def test_explicit_recovery_rejects_unrelated_transitions(
    current: LifecycleState,
    target: LifecycleState,
) -> None:
    item = WorkItem(
        "wi",
        "Work",
        "Description",
        lifecycle_state=current,
    )

    with pytest.raises(InvalidLifecycleTransitionError):
        item.recover_state(target, "Invalid recovery")
    assert item.lifecycle_state == current


def test_executor_uses_assignment_requirements_not_all_agent_capabilities() -> None:
    engine, _, orchestrator, executors, executions, _ = build_recovery_runtime(
        unrelated_agent_capability=True
    )
    executors.register_executor(successful_executor())

    result = executions.execute_assignment("execution", "assignment")

    assert result.status == ExecutionStatus.SUCCEEDED
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.REVIEW
    assert orchestrator.get_assignment(
        "assignment"
    ).required_capabilities == ("python",)


def test_retry_failed_execution_preserves_history_and_requirements() -> None:
    engine, _, orchestrator, executors, executions, recovery = (
        build_recovery_runtime()
    )
    create_failed_execution(executors, executions)
    original = executions.get_execution("failed")
    executors.remove_executor("executor")
    executors.register_executor(successful_executor())

    retried = recovery.retry_failed_execution(
        "recovery",
        "failed",
        "retry",
        "Retry with deterministic executor",
    )

    assert retried.id == "retry"
    assert retried.status == ExecutionStatus.SUCCEEDED
    assert executions.get_execution("failed") is original
    assert original.status == ExecutionStatus.FAILED
    assert executions.list_executions_for_assignment("assignment") == [
        original,
        retried,
    ]
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.REVIEW
    assert orchestrator.get_assignment("assignment").status == AssignmentStatus.ACTIVE
    assert recovery.get_recovery_record(
        "recovery"
    ).action == RecoveryAction.RETRY


def test_reset_failed_execution_to_assigned_is_audited() -> None:
    engine, agents, orchestrator, executors, executions, recovery = (
        build_recovery_runtime()
    )
    create_failed_execution(executors, executions)

    record = recovery.reset_failed_execution(
        "recovery",
        "failed",
        "Reset for manual retry",
    )

    assert record.action == RecoveryAction.RESET_TO_ASSIGNED
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.ASSIGNED
    assert orchestrator.get_assignment("assignment").status == AssignmentStatus.ACTIVE
    assert agents.get_agent("agent").state == AgentState.BUSY


def test_cancel_failed_assignment_releases_capacity_and_is_audited() -> None:
    engine, agents, orchestrator, executors, executions, recovery = (
        build_recovery_runtime()
    )
    create_failed_execution(executors, executions)

    record = recovery.cancel_failed_assignment(
        "recovery",
        "failed",
        "Cancel failed work",
    )

    work_item = engine.get_work_item("wp", "wi")
    assignment = orchestrator.get_assignment("assignment")
    assert record.action == RecoveryAction.CANCEL_ASSIGNMENT
    assert work_item.lifecycle_state == LifecycleState.READY
    assert work_item.assigned_to is None
    assert assignment.status == AssignmentStatus.CANCELLED
    assert agents.get_agent("agent").state == AgentState.AVAILABLE
    assert orchestrator.get_active_assignment_count("agent") == 0


def test_succeeded_execution_is_not_recoverable() -> None:
    _, _, _, executors, executions, recovery = build_recovery_runtime()
    executors.register_executor(successful_executor())
    executions.execute_assignment("succeeded", "assignment")

    with pytest.raises(ExecutionNotRecoverableError):
        recovery.reset_failed_execution(
            "recovery",
            "succeeded",
            "Invalid reset",
        )


def test_missing_execution_uses_execution_not_found() -> None:
    _, _, _, _, _, recovery = build_recovery_runtime()

    with pytest.raises(ExecutionNotFoundError):
        recovery.reset_failed_execution(
            "recovery",
            "missing",
            "Missing execution",
        )


def test_duplicate_recovery_id_is_rejected() -> None:
    _, _, _, executors, executions, recovery = build_recovery_runtime()
    create_failed_execution(executors, executions)
    recovery.reset_failed_execution("recovery", "failed", "First reset")

    with pytest.raises(DuplicateRecoveryError):
        recovery.reset_failed_execution("recovery", "failed", "Duplicate")


def test_recovery_retrieval_listing_and_defensive_copies() -> None:
    _, _, _, executors, executions, recovery = build_recovery_runtime()
    create_failed_execution(executors, executions)
    record = recovery.reset_failed_execution(
        "recovery",
        "failed",
        "Audited reset",
    )

    assert recovery.get_recovery_record("recovery") is record
    assert recovery.list_recovery_records_for_execution("failed") == [record]
    listed = recovery.list_recovery_records()
    listed.clear()
    assert recovery.list_recovery_records() == [record]
    with pytest.raises(RecoveryNotFoundError):
        recovery.get_recovery_record("missing")


def test_reset_failure_rolls_back_and_does_not_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _, _, executors, executions, recovery = build_recovery_runtime()
    create_failed_execution(executors, executions)

    def fail_store(*args: object, **kwargs: object) -> ExecutionRecoveryRecord:
        raise RuntimeError("injected recovery storage failure")

    monkeypatch.setattr(recovery, "_store_record", fail_store)
    with pytest.raises(RuntimeError, match="injected"):
        recovery.reset_failed_execution(
            "recovery",
            "failed",
            "Atomic reset",
        )

    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.RUNNING
    assert recovery.list_recovery_records() == []


def test_retry_preflight_failure_restores_running_state() -> None:
    engine, _, _, executors, executions, recovery = build_recovery_runtime()
    create_failed_execution(executors, executions)
    executors.remove_executor("executor")

    with pytest.raises(ExecutorNotFoundError):
        recovery.retry_failed_execution(
            "recovery",
            "failed",
            "retry",
            "No compatible executor",
        )

    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.RUNNING
    assert executions.list_executions() == [executions.get_execution("failed")]
    assert recovery.list_recovery_records() == []


def test_cancellation_record_failure_rolls_back_every_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, agents, orchestrator, executors, executions, recovery = (
        build_recovery_runtime()
    )
    create_failed_execution(executors, executions)
    work_item = engine.get_work_item("wp", "wi")
    assignment = orchestrator.get_assignment("assignment")

    def fail_store(*args: object, **kwargs: object) -> ExecutionRecoveryRecord:
        raise RuntimeError("injected recovery storage failure")

    monkeypatch.setattr(recovery, "_store_record", fail_store)
    with pytest.raises(RuntimeError, match="injected"):
        recovery.cancel_failed_assignment(
            "recovery",
            "failed",
            "Atomic cancellation",
        )

    assert work_item.lifecycle_state == LifecycleState.RUNNING
    assert work_item.assigned_to == "agent"
    assert assignment.status == AssignmentStatus.ACTIVE
    assert agents.get_agent("agent").state == AgentState.BUSY
    assert orchestrator.get_active_assignment_count("agent") == 1
    assert recovery.list_recovery_records() == []


def test_recovery_record_rejects_invalid_action() -> None:
    from runtime.exceptions import InvalidRecoveryActionError

    with pytest.raises(InvalidRecoveryActionError):
        ExecutionRecoveryRecord(
            "recovery",
            "execution",
            "assignment",
            "RETRY",  # type: ignore[arg-type]
            "Invalid action",
        )


def test_recovery_exception_hierarchy() -> None:
    from runtime.exceptions import (
        DuplicateRecoveryError,
        ExecutionNotRecoverableError,
        InvalidRecoveryActionError,
        RecoveryNotFoundError,
    )

    for error in (
        RecoveryNotFoundError,
        DuplicateRecoveryError,
        InvalidRecoveryActionError,
        ExecutionNotRecoverableError,
    ):
        assert issubclass(error, RuntimeDomainError)
