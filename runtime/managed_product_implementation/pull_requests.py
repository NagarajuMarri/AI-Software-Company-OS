"""Deterministic no-network draft-PR adapter for tests and examples."""

from dataclasses import replace

from runtime.managed_product_implementation.models import (
    ManagedProductTask,
    PullRequestResult,
    ReviewPackage,
)


class InMemoryPullRequestService:
    def __init__(self, repository_url: str = "https://example.invalid/repository") -> None:
        self.repository_url = repository_url.rstrip("/")
        self.values: dict[int, tuple[ManagedProductTask, ReviewPackage]] = {}
        self.by_task: dict[str, int] = {}

    def create_draft(self, task: ManagedProductTask, review: ReviewPackage) -> PullRequestResult:
        if task.task_id in self.by_task:
            raise ValueError("Draft pull request already exists for task")
        if task.commit_sha is None or review.commit_sha != task.commit_sha:
            raise ValueError("Commit-bound review evidence is required")
        number = len(self.values) + 1
        self.values[number] = (task, review)
        self.by_task[task.task_id] = number
        return PullRequestResult(
            number,
            f"{self.repository_url}/pull/{number}",
            True,
            (("evidence", "attached"),),
            task.base_branch,
            task.branch,
            task.commit_sha,
        )

    def update_draft(self, number: int, review: ReviewPackage) -> PullRequestResult:
        if number not in self.values:
            raise ValueError("Unknown pull request")
        task, _ = self.values[number]
        if task.commit_sha is None or review.commit_sha != task.commit_sha:
            raise ValueError("Updated evidence does not match pull request head")
        self.values[number] = (task, review)
        return PullRequestResult(
            number,
            f"{self.repository_url}/pull/{number}",
            True,
            (("evidence", "updated"),),
            task.base_branch,
            task.branch,
            task.commit_sha,
        )
