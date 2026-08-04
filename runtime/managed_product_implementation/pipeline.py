"""Resumable implementation orchestration ending at mandatory human review."""

from dataclasses import replace
from pathlib import Path

from runtime.managed_product_implementation.contracts import (
    ManagedProductImplementationProvider,
    PullRequestService,
    WorkspaceManager,
)
from runtime.managed_product_implementation.models import *  # noqa: F403
from runtime.managed_product_implementation.persistence import ManagedProductTaskStore
from runtime.managed_product_implementation.services import CommitService, VerificationService


class ManagedProductImplementationPipeline:
    def __init__(
        self,
        store: ManagedProductTaskStore,
        workspace_manager: WorkspaceManager,
        provider: ManagedProductImplementationProvider,
        verification: VerificationService,
        commit: CommitService,
        push,
        pull_requests: PullRequestService,
        steps: tuple[VerificationStep, ...],
        cleanup_policy: CleanupPolicy = CleanupPolicy.KEEP,
    ) -> None:
        self.store, self.workspace_manager, self.provider = store, workspace_manager, provider
        self.verification_service, self.commit_service, self.push_service = (
            verification,
            commit,
            push,
        )
        self.pull_requests, self.steps, self.cleanup_policy = pull_requests, steps, cleanup_policy

    def request(self, task: ManagedProductTask) -> ManagedProductTask:
        if task.provider != self.provider.provider_id:
            raise ValueError("Injected provider does not match requested provider")
        if self.store.load(task.task_id) is not None:
            raise ValueError("Task already exists")
        self.store.save(task)
        return task

    def run(self, task_id: str) -> ManagedProductTask:
        task = self.store.load(task_id)
        if task is None:
            raise ValueError("Unknown task")
        if task.state is ImplementationState.WAITING_FOR_HUMAN_REVIEW:
            return task
        try:
            if task.workspace is None:
                task = self._save(task, ImplementationState.PREPARING_WORKSPACE)
                workspace = self.workspace_manager.prepare(task)
                task = self._save(
                    replace(task, workspace=workspace, workspace_id=workspace.workspace_id),
                    ImplementationState.IMPLEMENTING,
                )
            assert task.workspace is not None
            path = Path(task.workspace.path)
            if task.provider_result is None:
                result = self.provider.implement(task, path)
                task = self._save(
                    replace(task, provider_result=result, execution_id=result.execution_id),
                    ImplementationState.VERIFYING,
                )
            if not task.verification:
                verification = self.verification_service.run(path, self.steps)
                if any(item.status is VerificationStatus.FAIL for item in verification):
                    return self._fail(
                        replace(
                            task,
                            verification=verification,
                            verification_status=VerificationStatus.FAIL,
                        ),
                        ImplementationState.VERIFICATION_FAILED,
                        "Verification failed",
                    )
                task = self._save(
                    replace(
                        task, verification=verification, verification_status=VerificationStatus.PASS
                    ),
                    ImplementationState.COMMITTING,
                )
            if task.commit_result is None:
                assert task.provider_result is not None
                commit = self.commit_service.commit(
                    path, task.provider_result.changed_files, task.milestone
                )
                task = self._save(
                    replace(task, commit_result=commit, commit_sha=commit.commit_sha),
                    ImplementationState.PUSHING,
                )
            if task.push_result is None:
                pushed = self.push_service.push(path, task.branch)
                if not pushed.success:
                    return self._fail(
                        replace(task, push_result=pushed),
                        ImplementationState.FAILED,
                        pushed.details,
                    )
                task = self._save(
                    replace(task, push_result=pushed), ImplementationState.CREATING_PR
                )
            review = self._review(task)
            if task.pull_request is None:
                pr = self.pull_requests.create_draft(task, review)
                review = replace(review, pull_request_url=pr.url)
                task = replace(
                    task,
                    pull_request=pr,
                    pull_request_id=pr.number,
                    pull_request_url=pr.url,
                    review_package=review,
                )
            task = self._save(
                replace(task, review_status="WAITING_FOR_HUMAN_REVIEW"),
                ImplementationState.WAITING_FOR_HUMAN_REVIEW,
            )
            if self.cleanup_policy is CleanupPolicy.ALWAYS:
                assert task.workspace is not None
                self.workspace_manager.cleanup(task.workspace)
            return task
        except Exception as error:
            state = (
                ImplementationState.PROVIDER_FAILED
                if task.state is ImplementationState.IMPLEMENTING
                else ImplementationState.PR_FAILED
                if task.state is ImplementationState.CREATING_PR
                else ImplementationState.FAILED
            )
            return self._fail(task, state, str(error))

    def _review(self, task: ManagedProductTask) -> ReviewPackage:
        result = task.provider_result
        commit = task.commit_result
        if result is None or commit is None or task.commit_sha is None:
            raise ValueError("Implementation, commit, and SHA are required for review")
        tests = (
            "\n".join(
                f"{x.name}: {x.status.value}"
                for x in task.verification
                if "test" in x.name or x.name == "pytest"
            )
            or "No test-specific step configured"
        )
        return ReviewPackage(
            result.summary,
            task.verification,
            tests,
            commit.changed_files,
            task.commit_sha,
            task.pull_request_url or "PENDING",
            result.known_risks,
            result.remaining_work,
        )

    def recover(self, task_id: str) -> ManagedProductTask:
        """Clear only failed-stage evidence so a durable task can be resumed safely."""
        task = self.store.load(task_id)
        if task is None:
            raise ValueError("Unknown task")
        if task.state is ImplementationState.VERIFICATION_FAILED:
            task = replace(task, verification=(), verification_status=VerificationStatus.UNKNOWN)
        elif task.state is ImplementationState.PROVIDER_FAILED:
            task = replace(task, provider_result=None, execution_id=None)
        elif task.state is ImplementationState.PR_FAILED:
            task = replace(task, pull_request=None, pull_request_id=None, pull_request_url=None)
        elif task.state is not ImplementationState.FAILED:
            raise ValueError("Only failed tasks can be recovered")
        value = replace(
            task,
            state=task.resume_from or ImplementationState.REQUESTED,
            failure=None,
            updated_at=utc_now(),
        )
        self.store.save(value)
        return value

    def record_human_approval(self, task_id: str, reviewer: str) -> ManagedProductTask:
        """Record the external human gate; this does not merge the pull request."""
        task = self.store.load(task_id)
        if task is None:
            raise ValueError("Unknown task")
        if task.state is not ImplementationState.WAITING_FOR_HUMAN_REVIEW:
            raise ValueError("Task is not waiting for human review")
        if not reviewer.strip():
            raise ValueError("Reviewer is required")
        completed = replace(
            task,
            state=ImplementationState.COMPLETED,
            review_status=f"APPROVED_BY:{reviewer.strip()}",
            updated_at=utc_now(),
            completed_at=utc_now(),
            resume_from=None,
        )
        self.store.save(completed)
        if self.cleanup_policy in {CleanupPolicy.ON_SUCCESS, CleanupPolicy.ALWAYS}:
            assert completed.workspace is not None
            self.workspace_manager.cleanup(completed.workspace)
        return completed

    def _save(self, task: ManagedProductTask, state: ImplementationState) -> ManagedProductTask:
        value = replace(task, state=state, resume_from=state, updated_at=utc_now())
        self.store.save(value)
        return value

    def _fail(
        self, task: ManagedProductTask, state: ImplementationState, detail: str
    ) -> ManagedProductTask:
        return self._save(replace(task, failure=detail), state)
