"""Provider-neutral ports; the pipeline never calls a concrete coding agent."""

from pathlib import Path
from typing import Protocol

from runtime.managed_product_implementation.models import (
    ManagedProductTask,
    ProviderImplementationResult,
    PullRequestResult,
    PushResult,
    ReviewPackage,
    WorkspaceResult,
)


class ManagedProductImplementationProvider(Protocol):
    provider_id: str

    def implement(
        self, task: ManagedProductTask, workspace: Path
    ) -> ProviderImplementationResult: ...


class WorkspaceManager(Protocol):
    def prepare(self, task: ManagedProductTask) -> WorkspaceResult: ...
    def cleanup(self, workspace: WorkspaceResult) -> None: ...


class PushServicePort(Protocol):
    def push(self, workspace: Path, branch: str, remote: str = "origin") -> PushResult: ...


class PullRequestService(Protocol):
    def create_draft(
        self, task: ManagedProductTask, review: ReviewPackage
    ) -> PullRequestResult: ...
    def update_draft(self, number: int, review: ReviewPackage) -> PullRequestResult: ...
