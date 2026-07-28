import pytest

from runtime.coding_agents import (
    CodingAgentResultStatus, CodingAgentTaskRequest,
    DeterministicCodingAgentProvider,
)
from runtime.composition import create_runtime_container
from runtime.tasks import ExternalTaskStatus
from runtime.tasks.exceptions import InvalidExternalTaskTransitionError


def create(service):
    return service.create_task(
        task_id="task", project_id="project", work_item_id="work",
        title="Change", description="Safe change",
        repository_reference="org/repo", working_branch="agent/task",
        requested_capabilities=("python",), correlation_id="corr",
    )


def request():
    return CodingAgentTaskRequest(
        "task", "project", "org/repo", "workspace", "agent/task",
        "Change", (), ("pass",), ("python",), ("src",), "corr", 30,
    )


def test_success_requires_review_approval_then_completion():
    container = create_runtime_container()
    container.coding_agent_provider_registry.register_provider(
        DeterministicCodingAgentProvider()
    )
    service = container.external_task_service
    task = create(service)
    service.queue_task(task.task_id)
    service.execute_task(task.task_id, request())
    assert task.status == ExternalTaskStatus.RUNNING
    service.request_review(task.task_id)
    service.approve_task(task.task_id, "human")
    service.complete_task(task.task_id)
    assert task.status == ExternalTaskStatus.COMPLETED
    assert len(container.event_store.list_events_for_aggregate(
        "external-task", "task"
    )) >= 8


def test_retryable_failure_requires_explicit_retry():
    container = create_runtime_container()
    container.coding_agent_provider_registry.register_provider(
        DeterministicCodingAgentProvider(
            outcomes=(CodingAgentResultStatus.FAILED_RETRYABLE,)
        )
    )
    service = container.external_task_service
    task = create(service)
    service.queue_task(task.task_id)
    service.execute_task(task.task_id, request())
    assert task.status == ExternalTaskStatus.FAILED
    service.retry_task(task.task_id)
    assert task.status == ExternalTaskStatus.QUEUED and task.retry_count == 1


def test_invalid_lifecycle_jump_is_rejected():
    container = create_runtime_container()
    task = create(container.external_task_service)
    with pytest.raises(InvalidExternalTaskTransitionError):
        container.external_task_service.complete_task(task.task_id)
