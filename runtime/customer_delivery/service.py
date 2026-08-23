"""Bind one Module 3 patch to human review and controlled draft delivery."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import subprocess
from threading import RLock

from runtime.coding_providers import ProviderOperationStore, ProviderStateError
from runtime.coding_providers.models import PatchEffectState
from runtime.customer_delivery.errors import (
    CustomerDeliveryConflict,
    CustomerDeliveryNotConfigured,
    CustomerDeliveryPolicyError,
    CustomerDeliveryReconciliationRequired,
)
from runtime.customer_delivery.models import (
    CustomerDeliveryConfiguration,
    CustomerDeliveryReview,
    CustomerDeliveryStatus,
    ReviewedFile,
    delivery_id_for,
    text_digest,
)
from runtime.customer_delivery.persistence import FileCustomerDeliveryStore
from runtime.customer_delivery.provider import CustomerDeliveryAdapter, canonical_review_patch
from runtime.customer_execution import (
    CustomerExecutionPlan,
    CustomerExecutionPlanStatus,
    CustomerExecutionService,
    CustomerExecutionTask,
    CustomerExecutionTaskStatus,
    inspect_workspace,
)


_MAX_REVIEW_DIFF_BYTES = 256_000


class CustomerDeliveryService:
    """Prepare, approve, and deliver one exact customer-reviewed patch."""

    def __init__(
        self,
        store: FileCustomerDeliveryStore,
        executions: CustomerExecutionService,
        provider_store: ProviderOperationStore,
        configuration: CustomerDeliveryConfiguration | None,
        adapter: CustomerDeliveryAdapter | None,
        clock=None,
    ) -> None:
        self._store = store
        self._executions = executions
        self._provider_store = provider_store
        self._configuration = configuration
        self._adapter = adapter
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    @property
    def configured(self) -> bool:
        return self._configuration is not None

    @property
    def live_enabled(self) -> bool:
        return bool(
            self._configuration
            and self._configuration.enabled
            and self._configuration.product_write_confirmed
            and self._adapter is not None
        )

    def find(self, customer_id: str, request_id: str) -> CustomerDeliveryReview | None:
        self._executions.find(customer_id, request_id)
        return self._store.find(customer_id, request_id)

    def view(
        self, customer_id: str, request_id: str
    ) -> tuple[CustomerDeliveryReview | None, str]:
        plan = self._require_review_plan(customer_id, request_id)
        review = self._store.find(customer_id, request_id)
        if review is None:
            return None, ""
        self._require_plan_binding(review, plan)
        if review.status in {
            CustomerDeliveryStatus.AWAITING_REVIEW,
            CustomerDeliveryStatus.REVIEW_APPROVED,
        }:
            _, _, diff = self._source(plan)
            if text_digest(diff) != review.git_diff_digest:
                raise CustomerDeliveryPolicyError("Displayed patch differs from review evidence")
            return review, diff
        return review, ""

    def prepare(self, customer_id: str, request_id: str) -> CustomerDeliveryReview:
        configuration = self._require_configuration()
        with self._lock:
            plan = self._require_review_plan(customer_id, request_id)
            task, files, diff = self._source(plan)
            now = self._clock()
            commit_message = f"feat: implement {task.requirement_id} with governed ASCOS delivery"
            title = f"ASCOS delivery: {task.title}"
            delivery_id = delivery_id_for(request_id)
            body = _pull_request_body(delivery_id, plan, task)
            review = CustomerDeliveryReview(
                delivery_id=delivery_id,
                customer_id=customer_id,
                request_id=request_id,
                product_id=plan.product_id,
                execution_plan_id=plan.plan_id,
                execution_plan_digest=plan.digest,
                execution_scope_digest=plan.scope_digest,
                provider_operation_id=task.provider_operation_id or "",
                provider_task_id=task.provider_task_id or "",
                patch_manifest_digest=task.manifest_digest or "",
                git_diff_digest=text_digest(diff),
                workspace_id=plan.workspace_id,
                workspace_branch=plan.workspace_branch,
                workspace_commit_before_turn=plan.workspace_commit,
                repository_full_name=configuration.repository_full_name,
                base_branch=configuration.base_branch,
                reviewed_files=files,
                additions=task.additions,
                deletions=task.deletions,
                commit_message=commit_message,
                pull_request_title=title,
                pull_request_body=body,
                pull_request_body_digest=text_digest(body),
                created_at=now,
                updated_at=now,
            )
            return self._store.create(review)

    def approve(
        self,
        customer_id: str,
        request_id: str,
        *,
        expected_review_digest: str,
        confirm_review: bool,
    ) -> CustomerDeliveryReview:
        if not confirm_review:
            raise CustomerDeliveryPolicyError("Exact patch review confirmation is required")
        with self._lock:
            plan = self._require_review_plan(customer_id, request_id)
            review = self._store.load(customer_id, request_id)
            self._require_plan_binding(review, plan)
            if review.status is CustomerDeliveryStatus.REVIEW_APPROVED:
                if review.review_digest == expected_review_digest:
                    return review
                raise CustomerDeliveryConflict("Patch review approval is stale")
            if review.status is not CustomerDeliveryStatus.AWAITING_REVIEW:
                raise CustomerDeliveryConflict("Patch cannot be approved now")
            if review.review_digest != expected_review_digest:
                raise CustomerDeliveryConflict("Patch review approval is stale")
            _, files, diff = self._source(plan)
            if files != review.reviewed_files or text_digest(diff) != review.git_diff_digest:
                raise CustomerDeliveryPolicyError("Patch changed before review approval")
            now = self._clock()
            approved = replace(
                review,
                status=CustomerDeliveryStatus.REVIEW_APPROVED,
                reviewed_at=now,
                reviewed_by=customer_id,
                updated_at=now,
            )
            return self._store.replace(approved, expected_digest=review.digest)

    def deliver(
        self,
        customer_id: str,
        request_id: str,
        *,
        expected_review_digest: str,
        confirm_repository_write: bool,
    ) -> CustomerDeliveryReview:
        self._require_configuration()
        if not self.live_enabled:
            raise CustomerDeliveryNotConfigured(
                "Product delivery requires operator enablement and repository-write confirmation"
            )
        if not confirm_repository_write:
            raise CustomerDeliveryPolicyError("Repository delivery confirmation is required")
        assert self._adapter is not None
        with self._lock:
            plan = self._require_review_plan(customer_id, request_id)
            review = self._store.load(customer_id, request_id)
            self._require_plan_binding(review, plan)
            if review.status is CustomerDeliveryStatus.DRAFT_PR_CREATED:
                if review.review_digest == expected_review_digest:
                    return review
                raise CustomerDeliveryConflict("Draft delivery request is stale")
            if review.status is not CustomerDeliveryStatus.REVIEW_APPROVED:
                raise CustomerDeliveryConflict("Exact human review is not approved")
            if review.review_digest != expected_review_digest:
                raise CustomerDeliveryConflict("Draft delivery request is stale")
            self._source(plan)
            self._adapter.preflight(review)
            in_progress = replace(
                review,
                status=CustomerDeliveryStatus.DELIVERY_IN_PROGRESS,
                updated_at=self._clock(),
            )
            in_progress = self._store.replace(in_progress, expected_digest=review.digest)
            try:
                outcome = self._adapter.deliver(in_progress)
                delivered = replace(
                    in_progress,
                    status=CustomerDeliveryStatus.DRAFT_PR_CREATED,
                    commit_sha=outcome.commit_sha,
                    tree_sha=outcome.tree_sha,
                    pull_request_number=outcome.pull_request_number,
                    pull_request_url=outcome.pull_request_url,
                    updated_at=self._clock(),
                )
                return self._store.replace(delivered, expected_digest=in_progress.digest)
            except Exception as error:
                current = self._store.load(customer_id, request_id)
                failed = replace(
                    current,
                    status=CustomerDeliveryStatus.RECONCILIATION_REQUIRED,
                    failure_classification=type(error).__name__,
                    updated_at=self._clock(),
                )
                self._store.replace(failed, expected_digest=current.digest)
                raise CustomerDeliveryReconciliationRequired(
                    "A repository delivery effect requires manual reconciliation"
                ) from error

    def _require_configuration(self) -> CustomerDeliveryConfiguration:
        if self._configuration is None:
            raise CustomerDeliveryNotConfigured(
                "The operator has not bound a governed repository delivery target"
            )
        return self._configuration

    def _require_review_plan(
        self, customer_id: str, request_id: str
    ) -> CustomerExecutionPlan:
        plan = self._executions.find(customer_id, request_id)
        if plan is None or plan.status is not CustomerExecutionPlanStatus.REVIEW_REQUIRED:
            raise CustomerDeliveryConflict("Module 3 has not produced a reviewable patch")
        return plan

    @staticmethod
    def _require_plan_binding(
        review: CustomerDeliveryReview, plan: CustomerExecutionPlan
    ) -> None:
        if (
            review.customer_id != plan.customer_id
            or review.request_id != plan.request_id
            or review.product_id != plan.product_id
            or review.execution_plan_id != plan.plan_id
            or review.execution_plan_digest != plan.digest
            or review.execution_scope_digest != plan.scope_digest
            or review.workspace_id != plan.workspace_id
            or review.workspace_branch != plan.workspace_branch
            or review.workspace_commit_before_turn != plan.workspace_commit
        ):
            raise CustomerDeliveryPolicyError("Delivery review differs from Module 3 authority")

    def _source(
        self, plan: CustomerExecutionPlan
    ) -> tuple[CustomerExecutionTask, tuple[ReviewedFile, ...], str]:
        configuration = self._require_configuration()
        completed = tuple(
            task for task in plan.tasks if task.status is CustomerExecutionTaskStatus.REVIEW_REQUIRED
        )
        if len(completed) != 1:
            raise CustomerDeliveryPolicyError("Exactly one Module 3 task must await review")
        task = completed[0]
        if not task.provider_operation_id or not task.provider_task_id or not task.manifest_digest:
            raise CustomerDeliveryPolicyError("Module 3 provider evidence is incomplete")
        try:
            effect = self._provider_store.load_patch_effect(
                plan.product_id, f"patch-{task.provider_operation_id}"
            )
        except ProviderStateError as error:
            raise CustomerDeliveryPolicyError("Module 3 patch evidence is unavailable") from error
        manifest = effect.manifest
        if (
            effect.state is not PatchEffectState.ACCEPTED
            or effect.project_id != plan.product_id
            or effect.provider_operation_id != task.provider_operation_id
            or effect.execution_plan_id != plan.plan_id
            or effect.workspace_id != plan.workspace_id
            or effect.branch != plan.workspace_branch
            or effect.pre_application_commit_sha != plan.workspace_commit
            or manifest is None
            or manifest.provider_operation_id != task.provider_operation_id
            or manifest.manifest_digest != task.manifest_digest
            or manifest.changed_paths != task.changed_paths
            or manifest.additions != task.additions
            or manifest.deletions != task.deletions
            or manifest.workspace_status != "DIRTY"
        ):
            raise CustomerDeliveryPolicyError("Module 3 patch evidence is invalid")
        workspace = inspect_workspace(configuration.workspace_root)
        if (
            workspace.workspace_id != plan.workspace_id
            or workspace.branch != plan.workspace_branch
            or workspace.commit != plan.workspace_commit
            or workspace.clean
            or tuple(sorted(workspace.changed_paths)) != tuple(sorted(task.changed_paths))
        ):
            raise CustomerDeliveryPolicyError("Product workspace changed after Module 3")
        expected_files = tuple(
            ReviewedFile(item.path, item.content_digest) for item in manifest.files
        )
        if tuple(item.path for item in expected_files) != task.changed_paths:
            raise CustomerDeliveryPolicyError("Patch manifest file set is incomplete")
        for item in expected_files:
            path = configuration.workspace_root / item.path
            if not path.is_file() or path.is_symlink():
                raise CustomerDeliveryPolicyError("Reviewed patch file is missing or unsafe")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item.content_digest:
                raise CustomerDeliveryPolicyError("Reviewed patch file content changed")
        tracked_diff = _git_diff(configuration.workspace_root, task.changed_paths)
        if text_digest(tracked_diff) != manifest.git_diff_digest:
            raise CustomerDeliveryPolicyError("Git diff differs from the accepted patch manifest")
        diff = canonical_review_patch(configuration.workspace_root, expected_files)
        if len(diff.encode("utf-8")) > _MAX_REVIEW_DIFF_BYTES:
            raise CustomerDeliveryPolicyError("Reviewed patch exceeds the browser evidence budget")
        return task, expected_files, diff


def _git_diff(workspace: Path, paths: tuple[str, ...]) -> str:
    environment = dict(os.environ)
    for name in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        environment.pop(name, None)
    try:
        result = subprocess.run(
            (
                "git",
                "-c",
                f"core.hooksPath={os.devnull}",
                "diff",
                "--no-ext-diff",
                "--no-color",
                "--",
                *paths,
            ),
            cwd=workspace,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise CustomerDeliveryPolicyError("Could not inspect the reviewed Git diff") from error
    if result.returncode:
        raise CustomerDeliveryPolicyError("Could not inspect the reviewed Git diff")
    return result.stdout


def _pull_request_body(
    delivery_id: str,
    plan: CustomerExecutionPlan,
    task: CustomerExecutionTask,
) -> str:
    criteria = "\n".join(f"- {value}" for value in task.acceptance_criteria)
    changed = "\n".join(f"- `{value}`" for value in task.changed_paths)
    return (
        f"<!-- ASCOS-DELIVERY:{delivery_id}:{task.manifest_digest} -->\n\n"
        "## Governed customer delivery\n\n"
        f"Execution plan: `{plan.plan_id}`  \n"
        f"Requirement: `{task.requirement_id}` — {task.title}\n\n"
        "### Acceptance criteria\n\n"
        f"{criteria}\n\n"
        "### Exact reviewed files\n\n"
        f"{changed}\n\n"
        f"Patch manifest: `{task.manifest_digest}`\n\n"
        "### Boundary\n\n"
        "This is an open draft PR created from one human-reviewed patch. ASCOS did not approve "
        "or merge the PR, deploy a preview or production environment, release, or start FamilyVault."
    )
