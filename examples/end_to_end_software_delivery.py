"""Run the deterministic ASCOS software factory from intake to release."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.composition import create_runtime_container
from runtime.execution.executor import DeterministicExecutor
from runtime.workflows import SoftwareDeliveryRequest


def main() -> None:
    container = create_runtime_container()
    container.agent_registry.register_agent(
        AgentMetadata(
            "backend-agent",
            "Backend Agent",
            AgentRole.BACKEND_ENGINEER,
            "Deterministic Python backend agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=[
                AgentCapability(
                    "python",
                    "Python",
                    "Build Python backend services",
                    "1",
                )
            ],
        )
    )
    container.executor_registry.register_executor(
        DeterministicExecutor(
            "python-executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
            deterministic_output=(
                "Implemented GET /health returning service status"
            ),
        )
    )
    service = container.software_delivery_workflow_service
    workflow = service.submit_request(
        SoftwareDeliveryRequest(
            "health-check",
            "Build a health-check endpoint",
            "Build a health-check endpoint for a Python backend service.",
            "platform-team",
            AgentRole.BACKEND_ENGINEER,
            ["python"],
            [
                "GET /health returns HTTP 200",
                "Response contains service status",
            ],
            correlation_id="delivery:health-check",
        )
    )
    service.plan_request(workflow.id)
    service.assign_work(workflow.id)
    service.execute_work(workflow.id)
    service.approve_work(workflow.id)
    service.complete_work(workflow.id)
    service.release_work(workflow.id)

    print(
        f"Workflow {workflow.id}: stage={workflow.current_stage.value}, "
        f"executions={workflow.execution_ids}"
    )
    for event in service.get_workflow_events(workflow.id):
        print(
            f"{event.occurred_at.isoformat()} "
            f"{event.event_type.value} "
            f"aggregate={event.aggregate_type}:{event.aggregate_id}"
        )


if __name__ == "__main__":
    main()
