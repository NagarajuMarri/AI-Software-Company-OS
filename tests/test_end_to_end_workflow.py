import subprocess
import sys
from pathlib import Path

import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.composition import create_runtime_container
from runtime.events.types import EventType
from runtime.exceptions import (
    DuplicateWorkflowError,
    InvalidWorkflowTransitionError,
    TransactionCommitError,
    WorkflowApprovalError,
    WorkflowExecutionError,
    WorkflowReleaseError,
)
from runtime.execution.executor import DeterministicExecutor
from runtime.execution.result import ExecutionStatus
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.assignment import AssignmentStatus
from runtime.workflows import (
    SoftwareDeliveryRequest,
    WorkflowStage,
)


def request(
    request_id: str = "delivery",
    *,
    correlation_id: str | None = "correlation",
) -> SoftwareDeliveryRequest:
    return SoftwareDeliveryRequest(
        request_id,
        "Health check",
        "Build a Python health-check endpoint",
        "platform",
        AgentRole.BACKEND_ENGINEER,
        ["python"],
        ["Returns HTTP 200", "Includes service status"],
        correlation_id=correlation_id,
    )


def configured_container(
    *,
    should_fail: bool = False,
    agents: int = 1,
):
    container = create_runtime_container()
    capability = AgentCapability(
        "python",
        "Python",
        "Python backend development",
        "1",
    )
    for index in range(agents):
        container.agent_registry.register_agent(
            AgentMetadata(
                f"agent-{index}",
                f"Agent {index}",
                AgentRole.BACKEND_ENGINEER,
                "Delivery agent",
                state=AgentState.AVAILABLE,
                supported_capabilities=[capability],
                priority=agents - index,
            )
        )
    container.executor_registry.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
            should_fail=should_fail,
            failure_message="deterministic failure",
            deterministic_output="health endpoint implemented",
        )
    )
    return container


def assigned_workflow(container, request_id: str = "delivery"):
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(request(request_id))
    service.plan_request(workflow.id)
    service.prepare_work(workflow.id)
    service.assign_work(workflow.id)
    return workflow


def reviewed_workflow(container, request_id: str = "delivery"):
    workflow = assigned_workflow(container, request_id)
    container.software_delivery_workflow_service.execute_work(workflow.id)
    return workflow


def test_happy_path_complete_workflow_and_event_ordering() -> None:
    container = configured_container()
    service = container.software_delivery_workflow_service
    workflow = reviewed_workflow(container)

    assert workflow.current_stage == WorkflowStage.REVIEW
    assert (
        container.runtime_engine.get_work_item(
            workflow.work_package_id,
            workflow.work_item_id,
        ).lifecycle_state
        == LifecycleState.REVIEW
    )
    service.submit_for_review(workflow.id)
    service.approve_work(workflow.id)
    service.complete_work(workflow.id)
    service.release_work(workflow.id)

    assert workflow.current_stage == WorkflowStage.RELEASED
    assert (
        container.orchestrator.get_assignment(
            workflow.assignment_id
        ).status
        == AssignmentStatus.COMPLETED
    )
    assert (
        container.agent_registry.get_agent("agent-0").state
        == AgentState.AVAILABLE
    )
    workflow_event_types = [
        event.event_type
        for event in service.get_workflow_events(workflow.id)
        if event.aggregate_type == "SOFTWARE_DELIVERY_WORKFLOW"
    ]
    assert workflow_event_types == [
        EventType.SOFTWARE_REQUEST_SUBMITTED,
        EventType.SOFTWARE_REQUEST_PLANNED,
        EventType.SOFTWARE_WORK_ASSIGNED,
        EventType.SOFTWARE_EXECUTION_STARTED,
        EventType.SOFTWARE_EXECUTION_SUCCEEDED,
        EventType.SOFTWARE_REVIEW_SUBMITTED,
        EventType.SOFTWARE_WORK_APPROVED,
        EventType.SOFTWARE_WORK_COMPLETED,
        EventType.SOFTWARE_WORK_RELEASED,
    ]


def test_container_integration_and_deterministic_agent_selection() -> None:
    container = configured_container(agents=2)
    service = container.software_delivery_workflow_service
    workflow = assigned_workflow(container)

    assert service.runtime_engine is container.runtime_engine
    assert service.execution_service is container.execution_service
    assert service.event_publisher is container.event_publisher
    assert (
        container.orchestrator.get_assignment(
            workflow.assignment_id
        ).agent_id
        == "agent-0"
    )


def test_workflow_event_correlation_and_causation() -> None:
    container = configured_container()
    workflow = reviewed_workflow(container)
    events = container.software_delivery_workflow_service.get_workflow_events(
        workflow.id
    )

    assert events
    assert {event.correlation_id for event in events} == {"correlation"}
    workflow_events = [
        event
        for event in events
        if event.aggregate_type == "SOFTWARE_DELIVERY_WORKFLOW"
    ]
    assert workflow_events[0].causation_id is None
    assert all(event.causation_id for event in workflow_events[1:])


def test_approval_is_explicit_and_release_requires_completion() -> None:
    container = configured_container()
    service = container.software_delivery_workflow_service
    workflow = assigned_workflow(container)

    with pytest.raises(WorkflowApprovalError):
        service.approve_work(workflow.id)
    with pytest.raises(WorkflowReleaseError):
        service.release_work(workflow.id)
    assert workflow.current_stage == WorkflowStage.ASSIGNED

    service.execute_work(workflow.id)
    assert workflow.current_stage == WorkflowStage.REVIEW
    assert (
        container.orchestrator.get_assignment(
            workflow.assignment_id
        ).status
        == AssignmentStatus.ACTIVE
    )


def test_rejection_enters_correction_and_can_be_reexecuted() -> None:
    container = configured_container()
    service = container.software_delivery_workflow_service
    workflow = reviewed_workflow(container)

    service.reject_work(workflow.id)
    assert workflow.current_stage == WorkflowStage.EXECUTING
    item = container.runtime_engine.get_work_item(
        workflow.work_package_id,
        workflow.work_item_id,
    )
    assert item.lifecycle_state == LifecycleState.REJECTED

    service.execute_work(workflow.id, "corrected-execution")
    assert workflow.current_stage == WorkflowStage.REVIEW
    assert workflow.execution_ids == [
        "delivery:execution:1",
        "corrected-execution",
    ]


def test_failed_execution_is_recorded_and_recoverable() -> None:
    container = configured_container(should_fail=True)
    service = container.software_delivery_workflow_service
    workflow = assigned_workflow(container)

    with pytest.raises(WorkflowExecutionError):
        service.execute_work(workflow.id)

    assert workflow.current_stage == WorkflowStage.FAILED
    execution = container.execution_service.get_execution(
        workflow.execution_ids[0]
    )
    assert execution.status == ExecutionStatus.FAILED
    assert (
        container.runtime_engine.get_work_item(
            workflow.work_package_id,
            workflow.work_item_id,
        ).lifecycle_state
        == LifecycleState.RUNNING
    )


def test_retry_recovery_preserves_history_and_reaches_review() -> None:
    container = configured_container(should_fail=True)
    service = container.software_delivery_workflow_service
    workflow = assigned_workflow(container)
    with pytest.raises(WorkflowExecutionError):
        service.execute_work(workflow.id)
    container.executor_registry.remove_executor("executor")
    container.executor_registry.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
            deterministic_output="recovered",
        )
    )

    service.recover_failed_execution(
        workflow.id,
        "recovery",
        "Retry corrected implementation",
        new_execution_id="retry-execution",
    )

    assert workflow.current_stage == WorkflowStage.REVIEW
    assert workflow.execution_ids == [
        "delivery:execution:1",
        "retry-execution",
    ]
    assert len(
        container.execution_service.list_executions_for_assignment(
            workflow.assignment_id
        )
    ) == 2


def test_reset_recovery_returns_to_assigned() -> None:
    container = configured_container(should_fail=True)
    service = container.software_delivery_workflow_service
    workflow = assigned_workflow(container)
    with pytest.raises(WorkflowExecutionError):
        service.execute_work(workflow.id)

    service.recover_failed_execution(
        workflow.id,
        "reset",
        "Reset for manual retry",
        action="reset",
    )

    assert workflow.current_stage == WorkflowStage.ASSIGNED
    assert (
        container.runtime_engine.get_work_item(
            workflow.work_package_id,
            workflow.work_item_id,
        ).lifecycle_state
        == LifecycleState.ASSIGNED
    )


def test_cancel_recovery_cancels_assignment_and_releases_agent() -> None:
    container = configured_container(should_fail=True)
    service = container.software_delivery_workflow_service
    workflow = assigned_workflow(container)
    with pytest.raises(WorkflowExecutionError):
        service.execute_work(workflow.id)

    service.recover_failed_execution(
        workflow.id,
        "cancel-recovery",
        "Cancel failed delivery",
        action="cancel",
    )

    assert workflow.current_stage == WorkflowStage.CANCELLED
    assert (
        container.orchestrator.get_assignment(
            workflow.assignment_id
        ).status
        == AssignmentStatus.CANCELLED
    )
    assert (
        container.agent_registry.get_agent("agent-0").state
        == AgentState.AVAILABLE
    )
    assert (
        EventType.SOFTWARE_WORKFLOW_CANCELLED
        in {
            event.event_type
            for event in service.get_workflow_events(workflow.id)
        }
    )


@pytest.mark.parametrize("stage", ["intake", "assigned", "failed"])
def test_cancellation_paths_release_capacity(stage: str) -> None:
    container = configured_container(should_fail=stage == "failed")
    service = container.software_delivery_workflow_service
    if stage == "intake":
        workflow = service.submit_request(request())
    else:
        workflow = assigned_workflow(container)
        if stage == "failed":
            with pytest.raises(WorkflowExecutionError):
                service.execute_work(workflow.id)

    service.cancel_workflow(workflow.id, "No longer required")

    assert workflow.current_stage == WorkflowStage.CANCELLED
    if stage != "intake":
        assert (
            container.agent_registry.get_agent("agent-0").state
            == AgentState.AVAILABLE
        )


def test_duplicate_and_invalid_transitions_store_no_events() -> None:
    container = configured_container()
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(request())
    before = list(container.event_store.list_events())

    with pytest.raises(DuplicateWorkflowError):
        service.submit_request(request())
    with pytest.raises(InvalidWorkflowTransitionError):
        service.assign_work(workflow.id)

    assert container.event_store.list_events() == before


def test_atomic_event_failure_rolls_back_workflow_and_runtime() -> None:
    container = configured_container()
    service = container.software_delivery_workflow_service
    workflow = reviewed_workflow(container)
    item = container.runtime_engine.get_work_item(
        workflow.work_package_id,
        workflow.work_item_id,
    )
    package = container.runtime_engine.get_work_package(
        workflow.work_package_id
    )
    before_updated_at = package.updated_at
    before_events = list(container.event_store.list_events())

    def fail_events(events):
        raise RuntimeError("storage failed")

    container.event_store.add_events = fail_events
    with pytest.raises(TransactionCommitError):
        service.approve_work(workflow.id)

    assert workflow.current_stage == WorkflowStage.REVIEW
    assert item.lifecycle_state == LifecycleState.REVIEW
    assert package.updated_at == before_updated_at
    assert container.event_store.list_events() == before_events


def test_eventing_disabled_workflow_is_functional() -> None:
    container = create_runtime_container(eventing_enabled=False)
    capability = AgentCapability("python", "Python", "Python", "1")
    container.agent_registry.register_agent(
        AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            "Agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=[capability],
        )
    )
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(request(correlation_id=None))
    service.plan_request(workflow.id)

    assert workflow.current_stage == WorkflowStage.READY
    assert service.get_workflow_events(workflow.id) == []


def test_example_runs_successfully() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "examples/end_to_end_software_delivery.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "stage=RELEASED" in result.stdout
    assert "SOFTWARE_WORK_RELEASED" in result.stdout
