"""Show deterministic provider selection, explicit retry, and review."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.coding_agents import (
    CodingAgentResultStatus, CodingAgentTaskRequest,
    DeterministicCodingAgentProvider,
)
from runtime.composition import create_runtime_container


def main():
    container = create_runtime_container()
    provider = DeterministicCodingAgentProvider(
        outcomes=(
            CodingAgentResultStatus.FAILED_RETRYABLE,
            CodingAgentResultStatus.SUCCEEDED,
        )
    )
    container.coding_agent_provider_registry.register_provider(provider)
    service = container.external_task_service
    task = service.create_task(
        task_id="retry", project_id="project", work_item_id="work",
        title="Retry simulation", description="One explicit retry",
        repository_reference="example/project",
        working_branch="agent/retry",
        requested_capabilities=("python",),
    )
    request = CodingAgentTaskRequest(
        "retry", "project", "example/project", "workspace", "agent/retry",
        "Simulate work", (), ("success",), ("python",), ("src",),
        "retry-correlation", 30,
    )
    service.queue_task(task.task_id)
    first = service.execute_task(task.task_id, request)
    service.retry_task(task.task_id)
    second = service.execute_task(task.task_id, request)
    service.request_review(task.task_id)
    print(
        f"provider={provider.provider_id} first={first.status.value} "
        f"second={second.status.value} progress="
        f"{len(service.list_progress(task.task_id))} "
        f"status={task.status.value}"
    )


if __name__ == "__main__":
    main()
