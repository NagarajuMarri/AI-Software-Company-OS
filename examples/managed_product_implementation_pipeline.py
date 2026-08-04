"""Offline Milestone 13.2 flow: request through mandatory review stop."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.managed_product_implementation.models import *  # noqa: F403
from runtime.managed_product_implementation.persistence import InMemoryManagedProductTaskStore
from runtime.managed_product_implementation.pipeline import ManagedProductImplementationPipeline
from runtime.managed_product_implementation.pull_requests import InMemoryPullRequestService


class Workspace:
    def prepare(self, task):
        return WorkspaceResult(
            task.task_id,
            ".",
            task.repository,
            task.branch,
            task.expected_commit_sha,
            True,
            utc_now(),
        )

    def cleanup(self, workspace):
        pass


class Provider:
    provider_id = "offline-example"

    def implement(self, task, workspace):
        return ProviderImplementationResult(
            "example-execution", "Example implementation", ("example.txt",), (), ("Human review",)
        )


class Verify:
    def run(self, workspace, steps):
        return (
            VerificationStepResult(
                "pytest", VerificationStatus.PASS, ("pytest",), 0, "passed", utc_now(), utc_now()
            ),
        )


class Commit:
    def commit(self, workspace, paths, milestone):
        return CommitResult("a" * 40, f"Implement {milestone}", paths)


class Push:
    def push(self, workspace, branch, remote="origin"):
        return PushResult(True, branch, remote, f"origin/{branch}")


def main() -> None:
    with TemporaryDirectory() as directory:
        store = InMemoryManagedProductTaskStore()
        pipeline = ManagedProductImplementationPipeline(
            store,
            Workspace(),
            Provider(),
            Verify(),
            Commit(),
            Push(),
            InMemoryPullRequestService(),
            (VerificationStep("pytest", ("pytest",)),),
        )
        request = ManagedProductTask(
            "example-task",
            "example-project",
            "https://example.invalid/product",
            "feature/milestone",
            "0" * 40,
            "Milestone X",
            "Implement approved scope",
            "offline-example",
        )
        pipeline.request(request)
        result = pipeline.run(request.task_id)
        assert result.state is ImplementationState.WAITING_FOR_HUMAN_REVIEW
        print(result.state.value, result.commit_sha, result.pull_request_url)


if __name__ == "__main__":
    main()
