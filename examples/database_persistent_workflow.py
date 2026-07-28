"""Persist, restart, and finish a leased workflow with SQLite."""

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
from runtime.persistence.database import DatabasePersistenceProvider
from runtime.workflows import SoftwareDeliveryRequest


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "runtime.sqlite3"
        provider = DatabasePersistenceProvider(path)
        first = create_runtime_container(
            persistence_enabled=True,
            persistence_provider=provider,
            runtime_id="database-example",
            writer_owner_id="process-one",
        )
        first.agent_registry.register_agent(
            AgentMetadata(
                "agent", "Backend Agent", AgentRole.BACKEND_ENGINEER,
                "Database example", state=AgentState.AVAILABLE,
                supported_capabilities=[
                    AgentCapability("python", "Python", "Python", "1")
                ],
            )
        )
        first.executor_registry.register_executor(
            DeterministicExecutor(
                "executor", [AgentRole.BACKEND_ENGINEER], ["python"]
            )
        )
        service = first.software_delivery_workflow_service
        workflow = service.submit_request(
            SoftwareDeliveryRequest(
                "database-workflow", "Database workflow",
                "Demonstrate durable restart", "platform",
                AgentRole.BACKEND_ENGINEER, ["python"], ["Completed"],
            )
        )
        service.plan_request(workflow.id)
        service.assign_work(workflow.id)
        service.execute_work(workflow.id)
        checkpoint = first.persistence_service.save_checkpoint(
            "workflow reached review", checkpoint_id="review"
        )
        provider.leases.release_lease(first.runtime_lease)

        restarted_provider = DatabasePersistenceProvider(path)
        second = create_runtime_container(
            persistence_enabled=True,
            persistence_provider=restarted_provider,
            runtime_id="database-example",
            writer_owner_id="process-two",
        )
        second.persistence_service.restore_runtime(checkpoint)
        resumed = second.software_delivery_workflow_service
        restored = resumed.get_workflow(workflow.id)
        resumed.approve_work(restored.id)
        resumed.complete_work(restored.id)
        resumed.release_work(restored.id)
        second.persistence_service.save_checkpoint(
            "workflow released", checkpoint_id="released"
        )
        print(
            "state_version="
            f"{restarted_provider.get_state_version('database-example')} "
            "event_position="
            f"{restarted_provider.latest_global_position('database-example')} "
            f"stage={restored.current_stage.value}"
        )


if __name__ == "__main__":
    main()
