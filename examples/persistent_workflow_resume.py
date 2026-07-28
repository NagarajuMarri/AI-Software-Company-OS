"""Checkpoint a workflow, restart the runtime, and release it."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.composition import create_runtime_container
from runtime.execution.executor import DeterministicExecutor
from runtime.persistence import FilePersistenceProvider
from runtime.workflows import SoftwareDeliveryRequest


def main(storage_directory: str | None = None) -> None:
    temporary = None
    if storage_directory is None:
        temporary = tempfile.TemporaryDirectory()
        storage_directory = temporary.name
    provider = FilePersistenceProvider(storage_directory)
    container = create_runtime_container(
        persistence_enabled=True,
        persistence_provider=provider,
        runtime_id="resume-example",
    )
    container.agent_registry.register_agent(
        AgentMetadata(
            "agent",
            "Backend Agent",
            AgentRole.BACKEND_ENGINEER,
            "Persistent delivery agent",
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
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(
        SoftwareDeliveryRequest(
            "persistent-health",
            "Persistent health endpoint",
            "Build a health endpoint and resume after restart",
            "platform",
            AgentRole.BACKEND_ENGINEER,
            ["python"],
            ["Endpoint returns HTTP 200"],
            correlation_id="persistent-correlation",
        )
    )
    service.plan_request(workflow.id)
    service.assign_work(workflow.id)
    service.execute_work(workflow.id)
    checkpoint = container.persistence_service.save_checkpoint(
        "workflow reached review",
        checkpoint_id="review",
    )

    restored = create_runtime_container(
        persistence_enabled=True,
        persistence_provider=provider,
        runtime_id="resume-example",
    )
    restored.persistence_service.restore_runtime(checkpoint)
    restored_service = restored.software_delivery_workflow_service
    restored_workflow = restored_service.get_workflow(workflow.id)
    restored_service.approve_work(restored_workflow.id)
    restored_service.complete_work(restored_workflow.id)
    restored_service.release_work(restored_workflow.id)
    restored.persistence_service.save_checkpoint(
        "workflow released",
        checkpoint_id="released",
    )

    print(
        f"Restored workflow {restored_workflow.id}: "
        f"stage={restored_workflow.current_stage.value}"
    )
    for event in restored_service.get_workflow_events(restored_workflow.id):
        print(event.event_type.value, event.sequence_number)
    if temporary is not None:
        temporary.cleanup()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
