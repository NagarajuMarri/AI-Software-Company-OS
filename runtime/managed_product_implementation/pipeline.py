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
        if task.state is not ImplementationState.REQUESTED:
            raise ValueError("New task must be REQUESTED")
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
            workspace_evidence = task.workspace
            path = Path(workspace_evidence.path)
            if task.provider_result is None:
                result = self.provider.implement(task, path)
                self._validate_provider_result(task, result, path)
                task = self._save(
                    replace(task, provider_result=result, execution_id=result.execution_id),
                    ImplementationState.VERIFYING,
                )
            if not task.verification:
                verification = self.verification_service.run(path, self.steps)
                if len(verification) != len(self.steps) or any(
                    result.name != step.name for result, step in zip(verification, self.steps)
                ):
                    return self._fail(
                        replace(task, verification=verification),
                        ImplementationState.VERIFICATION_FAILED,
                        "Verification results do not match configured steps",
                    )
                if (
                    any(
                        result.workspace_commit_sha != workspace_evidence.commit_sha
                        or not result.diff_digest
                        for result in verification
                    )
                    or len({result.diff_digest for result in verification}) != 1
                ):
                    return self._fail(
                        replace(task, verification=verification),
                        ImplementationState.VERIFICATION_FAILED,
                        "Verification evidence is not bound to the workspace state",
                    )
                blocked = any(
                    result.status is VerificationStatus.FAIL
                    or (step.required and result.status is not VerificationStatus.PASS)
                    for result, step in zip(verification, self.steps)
                )
                if blocked:
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
                    path,
                    task.provider_result.changed_files,
                    task.milestone,
                    approved_paths=task.allowed_paths or task.provider_result.changed_files,
                )
                task = self._save(
                    replace(task, commit_result=commit, commit_sha=commit.commit_sha),
                    ImplementationState.PUSHING,
                )
            if task.push_result is None:
                pushed = self.push_service.push(
                    path,
                    task.branch,
                    expected_repository=task.repository,
                    expected_commit_sha=task.commit_sha,
                )
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
                if (
                    not pr.draft
                    or pr.base_branch != task.base_branch
                    or pr.head_branch != task.branch
                    or pr.head_sha != task.commit_sha
                ):
                    raise ValueError("Draft pull request identity does not match task evidence")
                review = replace(review, pull_request_url=pr.url)
                task = replace(
                    task,
                    pull_request=pr,
                    pull_request_id=pr.number,
                    pull_request_url=pr.url,
                    review_package=review,
                )
            task = self._save(
                replace(
                    task,
                    review_status="WAITING_FOR_HUMAN_REVIEW",
                    pending_actions=("human review",),
                ),
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

    def record_human_approval(
        self,
        task_id: str,
        reviewer: str,
        *,
        allow_self_approval: bool = False,
    ) -> ManagedProductTask:
        """Record the external human gate; this does not merge the pull request."""
        task = self.store.load(task_id)
        if task is None:
            raise ValueError("Unknown task")
        if task.state is not ImplementationState.WAITING_FOR_HUMAN_REVIEW:
            raise ValueError("Task is not waiting for human review")
        if not reviewer.strip():
            raise ValueError("Reviewer is required")
        if (
            task.implementation_actor
            and reviewer.strip().casefold() == task.implementation_actor.casefold()
            and not allow_self_approval
        ):
            raise ValueError("Implementation actor cannot self-approve")
        if task.commit_sha is None or task.review_package is None:
            raise ValueError("Commit-bound review evidence is required")
        if task.review_package.commit_sha != task.commit_sha:
            raise ValueError("Review evidence is stale for the current commit")
        completed = replace(
            task,
            state=ImplementationState.COMPLETED,
            review_status=f"APPROVED_BY:{reviewer.strip()}",
            updated_at=utc_now(),
            completed_at=utc_now(),
            resume_from=None,
            reviewer=reviewer.strip(),
            reviewed_commit_sha=task.commit_sha,
            pending_actions=(),
        )
        self.store.save(completed)
        if self.cleanup_policy in {CleanupPolicy.ON_SUCCESS, CleanupPolicy.ALWAYS}:
            assert completed.workspace is not None
            self.workspace_manager.cleanup(completed.workspace)
        return completed

    def _save(self, task: ManagedProductTask, state: ImplementationState) -> ManagedProductTask:
        pending = {
            ImplementationState.PREPARING_WORKSPACE: ("prepare workspace",),
            ImplementationState.IMPLEMENTING: ("run provider",),
            ImplementationState.VERIFYING: ("run verification",),
            ImplementationState.COMMITTING: ("create commit",),
            ImplementationState.PUSHING: ("push branch",),
            ImplementationState.CREATING_PR: ("create draft pull request",),
        }.get(state, task.pending_actions)
        value = replace(
            task,
            state=state,
            resume_from=state,
            pending_actions=pending,
            updated_at=utc_now(),
        )
        self.store.save(value)
        return value

    def _fail(
        self, task: ManagedProductTask, state: ImplementationState, detail: str
    ) -> ManagedProductTask:
        return self._save(replace(task, failure=detail), state)

    @staticmethod
    def _validate_provider_result(
        task: ManagedProductTask,
        result: ProviderImplementationResult,
        workspace: Path,
    ) -> None:
        if result.execution_id == task.execution_id and task.execution_id is not None:
            raise ValueError("Provider execution identity was reused")
        allowed = task.allowed_paths
        for changed in result.changed_files:
            if allowed and not any(
                changed == item or changed.startswith(f"{item.rstrip('/')}/") for item in allowed
            ):
                raise ValueError("Provider returned a path outside approved scope")
            candidate = workspace / changed
            parent = candidate.parent.resolve()
            root = workspace.resolve()
            if root != parent and root not in parent.parents:
                raise ValueError("Provider path escapes workspace")
