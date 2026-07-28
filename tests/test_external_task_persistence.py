from runtime.coding_agents import DeterministicCodingAgentProvider
from runtime.composition import create_runtime_container
from runtime.persistence import FilePersistenceProvider
from runtime.tasks import ExternalOperationStatus, ExternalTaskStatus
from tests.test_external_task_lifecycle import create, request


def test_external_task_round_trip_and_no_event_republication(tmp_path):
    provider = FilePersistenceProvider(tmp_path)
    first = create_runtime_container(
        persistence_enabled=True, persistence_provider=provider,
        runtime_id="external",
    )
    first.coding_agent_provider_registry.register_provider(
        DeterministicCodingAgentProvider()
    )
    task = create(first.external_task_service)
    first.external_task_service.queue_task(task.task_id)
    first.external_task_service.execute_task(task.task_id, request())
    first.external_task_service.request_review(task.task_id)
    checkpoint = first.persistence_service.save_checkpoint("external")
    event_count = len(first.event_store.list_events())

    second = create_runtime_container(
        persistence_enabled=True, persistence_provider=provider,
        runtime_id="external",
    )
    second.persistence_service.restore_runtime(checkpoint)
    restored = second.external_task_service.get_task("task")
    assert restored.status == ExternalTaskStatus.WAITING_FOR_REVIEW
    assert len(second.event_store.list_events()) == event_count


def test_started_operation_restores_as_reconciliation_required(tmp_path):
    provider = FilePersistenceProvider(tmp_path)
    first = create_runtime_container(
        persistence_enabled=True, persistence_provider=provider,
        runtime_id="external",
    )
    task = create(first.external_task_service)
    task.status = ExternalTaskStatus.RUNNING
    operation = first.external_task_service._operation(task, "REMOTE_CALL")
    operation.status = ExternalOperationStatus.STARTED
    checkpoint = first.persistence_service.save_checkpoint("interrupted")

    second = create_runtime_container(
        persistence_enabled=True, persistence_provider=provider,
        runtime_id="external",
    )
    second.persistence_service.restore_runtime(checkpoint)
    assert second.external_task_service.get_task(
        "task"
    ).status == ExternalTaskStatus.RECONCILIATION_REQUIRED
    assert second.external_task_service.list_operations(
        "task"
    )[0].status == ExternalOperationStatus.RECONCILIATION_REQUIRED
