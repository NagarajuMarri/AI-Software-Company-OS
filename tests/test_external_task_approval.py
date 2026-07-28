import pytest

from runtime.coding_agents import CodingAgentTaskRequest, DeterministicCodingAgentProvider
from runtime.composition import create_runtime_container
from runtime.tasks import ApprovalStatus, ExternalTaskStatus
from runtime.tasks.exceptions import ApprovalPolicyError
from tests.test_external_task_lifecycle import create, request


def review_service():
    container = create_runtime_container()
    container.coding_agent_provider_registry.register_provider(
        DeterministicCodingAgentProvider()
    )
    service = container.external_task_service
    task = create(service)
    service.queue_task(task.task_id)
    service.execute_task(task.task_id, request())
    service.request_review(task.task_id)
    return service, task


def test_approval_requires_review_and_human_identity():
    container = create_runtime_container()
    task = create(container.external_task_service)
    with pytest.raises(ApprovalPolicyError):
        container.external_task_service.approve_task(task.task_id, "human")
    service, task = review_service()
    with pytest.raises(ApprovalPolicyError):
        service.approve_task(task.task_id, "")


def test_provider_cannot_self_approve():
    service, task = review_service()
    with pytest.raises(ApprovalPolicyError):
        service.approve_task(task.task_id, task.provider_id)


def test_approval_does_not_automatically_complete_task():
    service, task = review_service()
    service.approve_task(task.task_id, "human")
    assert task.status == ExternalTaskStatus.APPROVED
    assert task.completed_at is None


def test_rejection_and_changes_require_reason_and_are_recorded():
    service, task = review_service()
    with pytest.raises(ApprovalPolicyError):
        service.request_changes(task.task_id, "reviewer", "")
    decision = service.request_changes(task.task_id, "reviewer", "Fix tests")
    assert decision.decision == ApprovalStatus.CHANGES_REQUESTED
    assert task.status == ExternalTaskStatus.CHANGES_REQUESTED
    assert len(service.list_decisions(task.task_id)) == 1
