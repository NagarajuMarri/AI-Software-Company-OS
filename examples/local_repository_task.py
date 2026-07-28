"""Run a reviewed deterministic coding task in a temporary Git workspace."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.coding_agents import (
    CodingAgentTaskRequest, DeterministicCodingAgentProvider,
)
from runtime.composition import create_runtime_container
from runtime.integrations.git import LocalGitProvider
from runtime.tools import (
    CommandRequest, LocalCommandRunner, LocalWorkspaceProvider,
)


def main():
    with tempfile.TemporaryDirectory() as directory:
        workspaces = LocalWorkspaceProvider(directory)
        workspace = workspaces.create_workspace("project")
        runner = LocalCommandRunner(
            workspace.local_path, allowed_executables={"git", "python"}
        )
        git = LocalGitProvider(runner, workspaces, "project")
        git.initialize(workspace.local_path)
        runner.execute(CommandRequest(
            "git", ("config", "user.email", "example@invalid"),
            workspace.local_path,
        ))
        runner.execute(CommandRequest(
            "git", ("config", "user.name", "ASCOS Example"),
            workspace.local_path,
        ))
        git.create_branch(workspace.local_path, "agent/example-task")

        container = create_runtime_container()
        container.coding_agent_provider_registry.register_provider(
            DeterministicCodingAgentProvider()
        )
        service = container.external_task_service
        task = service.create_task(
            task_id="example", project_id="project", work_item_id="work",
            title="Create change", description="Deterministic local change",
            repository_reference="local/project",
            working_branch="agent/example-task",
            requested_capabilities=("python",),
        )
        service.queue_task(task.task_id)
        request = CodingAgentTaskRequest(
            task.task_id, "project", "local/project", "project",
            "agent/example-task", "Create change", (), ("test passes",),
            ("python",), ("change.txt",), "example", 30,
        )
        service.execute_task(task.task_id, request)
        (workspace.local_path / "change.txt").write_text(
            "deterministic change\n", encoding="utf-8"
        )
        test = runner.execute(CommandRequest(
            "python", ("-c", "assert open('change.txt').read().strip()"),
            workspace.local_path,
        ))
        service.request_review(task.task_id)
        service.approve_task(task.task_id, "human-reviewer")
        git.add(workspace.local_path, ["change.txt"])
        commit = git.commit(workspace.local_path, "Add deterministic change")
        print(
            f"status={task.status.value} commit={commit.sha} "
            f"events={len(container.event_store.list_events())} "
            f"test_exit={test.exit_code}"
        )


if __name__ == "__main__":
    main()
