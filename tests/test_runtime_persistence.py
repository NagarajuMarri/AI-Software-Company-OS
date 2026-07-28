from datetime import datetime, timezone
from pathlib import Path

import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.composition import create_runtime_container
from runtime.events.types import EventType
from runtime.exceptions import RuntimeCompositionError
from runtime.execution.executor import DeterministicExecutor
from runtime.persistence import FilePersistenceProvider, RuntimeCheckpoint
from runtime.persistence.exceptions import (
    CheckpointCorruptedError,
    DuplicateCheckpointError,
    PersistenceCommitError,
    PersistenceConfigurationError,
    PersistenceIntegrityError,
    RuntimeRestoreError,
    UnsupportedCheckpointVersionError,
)
from runtime.exceptions import WorkflowExecutionError
from runtime.persistence.serializer import CanonicalSerializer
from runtime.workflows import SoftwareDeliveryRequest, WorkflowStage
from runtime.models.artifact import Artifact


def configured(tmp_path: Path, *, automatic: bool = False):
    provider = FilePersistenceProvider(tmp_path)
    container = create_runtime_container(
        persistence_enabled=True,
        persistence_provider=provider,
        runtime_id="test-runtime",
        automatic_checkpoint_policy=automatic,
    )
    container.agent_registry.register_agent(
        AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            "Persistent agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=[
                AgentCapability("python", "Python", "Python", "1")
            ],
        )
    )
    container.executor_registry.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
        )
    )
    return provider, container


def review_workflow(container):
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(
        SoftwareDeliveryRequest(
            "delivery",
            "Delivery",
            "Persistent delivery",
            "owner",
            AgentRole.BACKEND_ENGINEER,
            ["python"],
            ["Works"],
            correlation_id="correlation",
        )
    )
    service.plan_request(workflow.id)
    service.assign_work(workflow.id)
    service.execute_work(workflow.id)
    return workflow


def test_canonical_serialization_round_trips_enum_and_datetime() -> None:
    value = {
        "time": datetime(2026, 1, 2, tzinfo=timezone.utc),
        "stage": WorkflowStage.REVIEW,
        "items": ("b", "a"),
    }
    encoded = CanonicalSerializer.encode_value(value)
    text = CanonicalSerializer.dumps(encoded)

    assert text == CanonicalSerializer.dumps(encoded)
    restored = CanonicalSerializer.decode_value(
        CanonicalSerializer.loads(text)
    )
    assert restored["time"] == value["time"]
    assert restored["stage"] == WorkflowStage.REVIEW
    with pytest.raises(TypeError):
        CanonicalSerializer.encode_value(object())


def test_checkpoint_immutability_and_digest() -> None:
    checkpoint = RuntimeCheckpoint.create("one", "runtime", "test", 0, {"a": [1]})

    with pytest.raises(TypeError):
        checkpoint.payload["x"] = 1
    with pytest.raises(PersistenceIntegrityError):
        RuntimeCheckpoint(
            checkpoint.id,
            checkpoint.schema_version,
            checkpoint.runtime_id,
            checkpoint.created_at,
            checkpoint.reason,
            checkpoint.last_event_position,
            "bad",
            checkpoint.payload,
        )
    with pytest.raises(UnsupportedCheckpointVersionError):
        RuntimeCheckpoint(
            "future",
            99,
            "runtime",
            checkpoint.created_at,
            "future",
            0,
            checkpoint.state_digest,
            checkpoint.payload,
        )


def test_file_provider_duplicate_path_and_corruption(tmp_path: Path) -> None:
    provider = FilePersistenceProvider(tmp_path)
    checkpoint = RuntimeCheckpoint.create("one", "runtime", "test", 0, {})
    provider.save_checkpoint(checkpoint)
    assert not list(tmp_path.glob("*.tmp"))
    with pytest.raises(DuplicateCheckpointError):
        provider.save_checkpoint(checkpoint)
    with pytest.raises(PersistenceConfigurationError):
        provider.load_checkpoint("../one")

    corrupt = tmp_path / "runtime--two.checkpoint.json"
    corrupt.write_text("{", encoding="utf-8")
    with pytest.raises(CheckpointCorruptedError):
        provider.load_checkpoint("two")
    assert provider.load_latest_checkpoint("runtime").id == "one"


def test_full_runtime_round_trip_and_event_continuity(tmp_path: Path) -> None:
    provider, original = configured(tmp_path)
    workflow = review_workflow(original)
    artifact = Artifact(
        "artifact",
        "Health endpoint",
        "source",
        "1",
        workflow.work_item_id,
    )
    original.artifact_store.add_artifact(artifact)
    original.runtime_engine.get_work_package(
        workflow.work_package_id
    ).add_artifact(artifact.id)
    checkpoint = original.persistence_service.save_checkpoint(
        "review", checkpoint_id="review"
    )
    event_count = len(original.event_store.list_events())

    restored = create_runtime_container(
        persistence_enabled=True,
        persistence_provider=provider,
        runtime_id="test-runtime",
    )
    restored.persistence_service.restore_runtime(checkpoint)
    restored_workflow = (
        restored.software_delivery_workflow_service.get_workflow(workflow.id)
    )

    assert restored_workflow.current_stage == WorkflowStage.REVIEW
    assert restored_workflow.execution_ids == workflow.execution_ids
    assert restored.artifact_store.get_artifact("artifact").work_item_id == (
        workflow.work_item_id
    )
    assert len(restored.event_store.list_events()) == event_count
    assert restored.agent_registry.get_agent("agent").state == AgentState.BUSY
    restored.software_delivery_workflow_service.approve_work(workflow.id)
    new_events = restored.event_store.list_events()
    assert len(new_events) > event_count
    aggregate = [
        event
        for event in new_events
        if event.aggregate_type == "SOFTWARE_DELIVERY_WORKFLOW"
    ]
    assert [event.sequence_number for event in aggregate] == list(
        range(1, len(aggregate) + 1)
    )
    assert {
        event.correlation_id
        for event in restored.software_delivery_workflow_service.get_workflow_events(
            workflow.id
        )
    } == {"correlation"}


def test_invalid_reference_is_rejected_without_partial_restore(tmp_path: Path) -> None:
    _, container = configured(tmp_path)
    review_workflow(container)
    payload = container.persistence_service._capture()
    payload["workflows"][0]["work_package_id"] = "missing"
    checkpoint = RuntimeCheckpoint.create(
        "invalid",
        "test-runtime",
        "invalid",
        len(payload["events"]),
        payload,
    )
    fresh = create_runtime_container(
        persistence_enabled=True,
        persistence_provider=FilePersistenceProvider(tmp_path / "fresh"),
        runtime_id="test-runtime",
    )

    with pytest.raises(RuntimeRestoreError):
        fresh.persistence_service.restore_runtime(checkpoint)
    assert fresh.runtime_engine.list_work_packages() == []


def test_recovery_records_survive_round_trip(tmp_path: Path) -> None:
    provider, container = configured(tmp_path)
    container.executor_registry.remove_executor("executor")
    container.executor_registry.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
            should_fail=True,
        )
    )
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(
        SoftwareDeliveryRequest(
            "failed",
            "Failed",
            "Recoverable",
            "owner",
            AgentRole.BACKEND_ENGINEER,
            ["python"],
            ["Can recover"],
        )
    )
    service.plan_request(workflow.id)
    service.assign_work(workflow.id)
    with pytest.raises(WorkflowExecutionError):
        service.execute_work(workflow.id)
    service.recover_failed_execution(
        workflow.id,
        "reset-record",
        "manual reset",
        action="reset",
    )
    checkpoint = container.persistence_service.save_checkpoint(
        "recovered",
        checkpoint_id="recovered",
    )
    fresh = create_runtime_container(
        persistence_enabled=True,
        persistence_provider=provider,
        runtime_id="test-runtime",
    )
    fresh.persistence_service.restore_runtime(checkpoint)

    record = fresh.execution_recovery_service.get_recovery_record(
        "reset-record"
    )
    assert record.execution_id == workflow.execution_ids[0]


def test_automatic_checkpoint_policy_and_failure(tmp_path: Path) -> None:
    provider, container = configured(tmp_path, automatic=True)
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(
        SoftwareDeliveryRequest(
            "auto",
            "Auto",
            "Auto checkpoint",
            "owner",
            AgentRole.BACKEND_ENGINEER,
            ["python"],
            ["Works"],
        )
    )
    assert provider.list_checkpoints("test-runtime")

    class BrokenProvider(FilePersistenceProvider):
        def save_checkpoint(self, checkpoint):
            raise OSError("failed")

    broken = create_runtime_container(
        persistence_enabled=True,
        persistence_provider=BrokenProvider(tmp_path / "broken"),
        runtime_id="broken",
        automatic_checkpoint_policy=True,
    )
    with pytest.raises(PersistenceCommitError):
        broken.software_delivery_workflow_service.submit_request(
            SoftwareDeliveryRequest(
                "committed",
                "Committed",
                "But not durable",
                "owner",
                AgentRole.BACKEND_ENGINEER,
                [],
                ["Exists"],
            )
        )
    assert broken.runtime_engine.get_work_package("committed:package")
    assert workflow.current_stage == WorkflowStage.INTAKE


def test_persistence_disabled_and_configuration_compatibility() -> None:
    container = create_runtime_container()
    assert container.persistence_service is None
    with pytest.raises(RuntimeCompositionError):
        create_runtime_container(persistence_enabled=True)
