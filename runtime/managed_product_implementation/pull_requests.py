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

    def create_draft(self, task: ManagedProductTask, review: ReviewPackage) -> PullRequestResult:
        number = len(self.values) + 1
        self.values[number] = (task, review)
        return PullRequestResult(
            number, f"{self.repository_url}/pull/{number}", True, (("evidence", "attached"),)
        )

    def update_draft(self, number: int, review: ReviewPackage) -> PullRequestResult:
        if number not in self.values:
            raise ValueError("Unknown pull request")
        task, _ = self.values[number]
        self.values[number] = (task, review)
        return PullRequestResult(
            number, f"{self.repository_url}/pull/{number}", True, (("evidence", "updated"),)
        )
