"""Bind approved customer plans to one governed Codex coding turn."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import subprocess
from threading import RLock
from types import SimpleNamespace
from typing import Protocol

from runtime.coding_providers import (
    CodexSdkExecutionConfiguration,
    CodexSdkExecutionProvider,
    CodingContextBuilder,
    CodingProviderRegistry,
    CodingProviderService,
    ContextLimits,
    ControlledPatchApplier,
    ProviderOperationStore,
)
from runtime.coding_providers.path_policy import secure_destination
from runtime.coding_providers.redaction import redact
from runtime.customer_estimate import CustomerDeliveryEstimateService
from runtime.customer_execution.errors import (
    CustomerExecutionConflict,
    CustomerExecutionNotConfigured,
    CustomerExecutionPolicyError,
    CustomerExecutionReconciliationRequired,
)
from runtime.customer_execution.models import (
    CustomerExecutionConfiguration,
    CustomerExecutionPlan,
    CustomerExecutionPlanStatus,
    CustomerExecutionTask,
    CustomerExecutionTaskStatus,
    _FORBIDDEN_PATHS,
    plan_id_for,
    workspace_id_for,
)
from runtime.customer_execution.persistence import FileCustomerExecutionStore
from runtime.customer_progress import CustomerProjectProgressService
from runtime.managed_execution import ChangePolicy


@dataclass(frozen=True)
class CustomerExecutionOutcome:
    provider_operation_id: str
    provider_task_id: str
    changed_paths: tuple[str, ...]
    additions: int
    deletions: int
    input_units: int | None
    output_units: int | None
    request_count: int
    authentication_mode: str
    billing_source: str
    summary: str
    manifest_digest: str


@dataclass(frozen=True)
class WorkspaceIdentity:
    workspace_id: str
    branch: str
    commit: str
    clean: bool
    changed_paths: tuple[str, ...]


class CustomerExecutionAdapter(Protocol):
    def operation_id(
        self, plan: CustomerExecutionPlan, task: CustomerExecutionTask
    ) -> str: ...

    def execute(
        self, plan: CustomerExecutionPlan, task: CustomerExecutionTask
    ) -> CustomerExecutionOutcome: ...


class GovernedCodexCustomerExecutionAdapter:
    """Translate customer authority into the accepted Module 2 provider boundary."""

    def __init__(
        self,
        configuration: CustomerExecutionConfiguration,
        provider_service: CodingProviderService,
    ) -> None:
        self._configuration = configuration
        self._provider_service = provider_service

    @staticmethod
    def operation_id(plan: CustomerExecutionPlan, task: CustomerExecutionTask) -> str:
        return f"provider-{plan.plan_id}-{task.task_id}-1"

    def execute(
        self, plan: CustomerExecutionPlan, task: CustomerExecutionTask
    ) -> CustomerExecutionOutcome:
        managed_plan = SimpleNamespace(
            project_id=plan.product_id,
            execution_plan_id=plan.plan_id,
            version=1,
            workspace_identity=plan.workspace_id,
            feature_branch=plan.workspace_branch,
        )
        managed_task = SimpleNamespace(
            project_task_id=task.task_id,
            objective=task.objective,
            acceptance_criteria=task.acceptance_criteria,
            allowed_paths=task.allowed_paths,
            forbidden_paths=task.forbidden_paths,
            allowed_commands=(),
            candidate_files=task.candidate_files,
        )
        coding_request = SimpleNamespace(
            external_task_id=f"{task.task_id}-attempt-1",
            timeout_seconds=300,
        )
        operation, request = self._provider_service.prepare(
            plan=managed_plan,
            task=managed_task,
            coding_request=coding_request,
            workspace_path=self._configuration.workspace_root,
            provider_id=plan.provider_id,
            evidence=(
                f"customer_progress_digest={plan.progress_digest}",
                f"approved_prd_digest={plan.prd_digest}",
                f"approved_roadmap_digest={plan.roadmap_digest}",
                f"execution_scope_digest={plan.scope_digest}",
            ),
        )
        if operation.provider_operation_id != self.operation_id(plan, task):
            raise CustomerExecutionPolicyError("Provider operation identity is invalid")
        self._provider_service.submit(
            plan.product_id,
            operation.provider_operation_id,
            request,
            allow_live_provider=True,
            confirm_usage_consumption=True,
        )
        self._provider_service.poll(plan.product_id, operation.provider_operation_id)
        result = self._provider_service.result(plan.product_id, operation.provider_operation_id)
        summary = redact(result.summary.strip(), limit=2_000)
        if any(value in summary.casefold() for value in ("merge", "deploy", "release")):
            raise CustomerExecutionPolicyError("Provider result exceeds the coding boundary")
        if result.usage.request_count != 1:
            raise CustomerExecutionPolicyError("Provider result exceeds the one-turn boundary")
        _, manifest = self._provider_service.apply_and_accept(
            plan.product_id,
            operation.provider_operation_id,
            workspace_path=self._configuration.workspace_root,
            task=managed_task,
            policy_id="customer-dashboard-v1",
        )
        return CustomerExecutionOutcome(
            operation.provider_operation_id,
            result.provider_task_id,
            manifest.changed_paths,
            manifest.additions,
            manifest.deletions,
            result.usage.input_units,
            result.usage.output_units,
            result.usage.request_count,
            result.usage.authentication_mode or "unknown",
            result.usage.billing_source or "unknown",
            summary,
            manifest.manifest_digest,
        )


class CustomerExecutionService:
    """Create, approve, execute, and reopen exact customer execution authority."""

    def __init__(
        self,
        store: FileCustomerExecutionStore,
        progress: CustomerProjectProgressService,
        estimates: CustomerDeliveryEstimateService,
        configuration: CustomerExecutionConfiguration | None,
        adapter: CustomerExecutionAdapter | None,
        clock=None,
    ) -> None:
        self._store = store
        self._progress = progress
        self._estimates = estimates
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
            and self._configuration.live_operation_confirmed
        )

    def find(self, customer_id: str, request_id: str) -> CustomerExecutionPlan | None:
        self._progress.view(customer_id, request_id)
        return self._store.find(customer_id, request_id)

    def plan(self, customer_id: str, request_id: str) -> CustomerExecutionPlan:
        configuration = self._require_configuration()
        with self._lock:
            snapshot, prd = self._authority(customer_id, request_id)
            workspace = inspect_workspace(configuration.workspace_root)
            _require_workspace(workspace)
            _require_candidate_files(configuration)
            requirements = {value.requirement_id: value for value in prd.requirements}
            tasks = tuple(
                CustomerExecutionTask(
                    _task_id(request_id, task.requirement_id),
                    task.requirement_id,
                    requirements[task.requirement_id].title,
                    (
                        f"Implement only approved requirement {task.requirement_id}: "
                        f"{requirements[task.requirement_id].description}"
                    ),
                    requirements[task.requirement_id].acceptance_criteria,
                    tuple(value.replace("\\", "/").strip("/") for value in configuration.candidate_files),
                    tuple(value.replace("\\", "/").strip("/") for value in configuration.allowed_paths),
                    _FORBIDDEN_PATHS,
                )
                for task in snapshot.tasks
            )
            now = self._clock()
            plan = CustomerExecutionPlan(
                plan_id_for(request_id),
                customer_id,
                request_id,
                snapshot.product_id,
                snapshot.digest,
                snapshot.requirements_digest,
                snapshot.prd_digest,
                snapshot.roadmap_digest,
                snapshot.roadmap_approval_digest,
                snapshot.estimate_digest,
                workspace.workspace_id,
                workspace.branch,
                workspace.commit,
                configuration.provider_id,
                configuration.model,
                configuration.authentication_mode.value,
                configuration.billing_source,
                tasks,
                now,
                now,
            )
            return self._store.create(plan)

    def approve(
        self,
        customer_id: str,
        request_id: str,
        *,
        expected_scope_digest: str,
    ) -> CustomerExecutionPlan:
        configuration = self._require_configuration()
        with self._lock:
            plan = self._store.load(customer_id, request_id)
            if plan.status is not CustomerExecutionPlanStatus.AWAITING_APPROVAL:
                if (
                    plan.status is CustomerExecutionPlanStatus.APPROVED
                    and plan.scope_digest == expected_scope_digest
                ):
                    return plan
                raise CustomerExecutionConflict("Execution plan cannot be approved now")
            if plan.scope_digest != expected_scope_digest:
                raise CustomerExecutionConflict("Execution plan approval is stale")
            self._require_current_authority(plan)
            _require_same_workspace(
                plan, inspect_workspace(configuration.workspace_root), require_clean=True
            )
            now = self._clock()
            approved = replace(
                plan,
                status=CustomerExecutionPlanStatus.APPROVED,
                approved_at=now,
                approved_by=customer_id,
                updated_at=now,
            )
            return self._store.replace(approved, expected_digest=plan.digest)

    def execute_next(
        self,
        customer_id: str,
        request_id: str,
        *,
        expected_scope_digest: str,
        confirm_scope: bool,
        confirm_usage_consumption: bool,
    ) -> CustomerExecutionPlan:
        configuration = self._require_configuration()
        if not self.live_enabled or self._adapter is None:
            raise CustomerExecutionNotConfigured(
                "Live execution requires both operator enablement and confirmation"
            )
        if not confirm_scope or not confirm_usage_consumption:
            raise CustomerExecutionPolicyError(
                "Exact scope and usage consumption must both be confirmed"
            )
        with self._lock:
            plan = self._store.load(customer_id, request_id)
            if plan.status is not CustomerExecutionPlanStatus.APPROVED:
                raise CustomerExecutionConflict("Execution plan is not approved")
            if plan.scope_digest != expected_scope_digest:
                raise CustomerExecutionConflict("Execution request is stale")
            self._require_current_authority(plan)
            _require_same_workspace(
                plan, inspect_workspace(configuration.workspace_root), require_clean=True
            )
            try:
                index = next(
                    index
                    for index, value in enumerate(plan.tasks)
                    if value.status is CustomerExecutionTaskStatus.PENDING
                )
            except StopIteration:
                raise CustomerExecutionConflict("No approved pending task is available") from None
            task = replace(
                plan.tasks[index],
                status=CustomerExecutionTaskStatus.EXECUTING,
                provider_operation_id=self._adapter.operation_id(plan, plan.tasks[index]),
            )
            tasks = plan.tasks[:index] + (task,) + plan.tasks[index + 1 :]
            executing = replace(
                plan,
                tasks=tasks,
                status=CustomerExecutionPlanStatus.EXECUTING,
                updated_at=self._clock(),
            )
            executing = self._store.replace(executing, expected_digest=plan.digest)
            try:
                outcome = self._adapter.execute(executing, task)
                if (
                    outcome.provider_operation_id != task.provider_operation_id
                    or outcome.authentication_mode != plan.authentication_mode
                    or outcome.billing_source != plan.billing_source
                ):
                    raise CustomerExecutionPolicyError(
                        "Provider receipt differs from approved billing authority"
                    )
                completed_task = replace(
                    task,
                    status=CustomerExecutionTaskStatus.REVIEW_REQUIRED,
                    provider_task_id=outcome.provider_task_id,
                    changed_paths=outcome.changed_paths,
                    additions=outcome.additions,
                    deletions=outcome.deletions,
                    input_units=outcome.input_units,
                    output_units=outcome.output_units,
                    request_count=outcome.request_count,
                    result_summary=outcome.summary,
                    manifest_digest=outcome.manifest_digest,
                )
                current = self._store.load(customer_id, request_id)
                tasks = current.tasks[:index] + (completed_task,) + current.tasks[index + 1 :]
                review = replace(
                    current,
                    tasks=tasks,
                    status=CustomerExecutionPlanStatus.REVIEW_REQUIRED,
                    updated_at=self._clock(),
                )
                return self._store.replace(review, expected_digest=current.digest)
            except Exception as error:
                current = self._store.load(customer_id, request_id)
                failed_task = replace(
                    current.tasks[index],
                    status=CustomerExecutionTaskStatus.RECONCILIATION_REQUIRED,
                )
                failed = replace(
                    current,
                    tasks=current.tasks[:index]
                    + (failed_task,)
                    + current.tasks[index + 1 :],
                    status=CustomerExecutionPlanStatus.RECONCILIATION_REQUIRED,
                    failure_classification=type(error).__name__,
                    updated_at=self._clock(),
                )
                self._store.replace(failed, expected_digest=current.digest)
                raise CustomerExecutionReconciliationRequired(
                    "A live execution intent requires manual reconciliation"
                ) from error

    def _require_configuration(self) -> CustomerExecutionConfiguration:
        if self._configuration is None:
            raise CustomerExecutionNotConfigured(
                "The operator has not bound a governed product workspace"
            )
        return self._configuration

    def _authority(self, customer_id: str, request_id: str):
        snapshot = self._progress.view(customer_id, request_id)
        _, prd, roadmap, approval, estimate = self._estimates.context(customer_id, request_id)
        if prd is None or roadmap is None or approval is None or estimate is None:
            raise CustomerExecutionConflict("Locked planning authority is incomplete")
        if (
            snapshot.prd_digest != prd.digest
            or snapshot.roadmap_digest != roadmap.digest
            or snapshot.roadmap_approval_digest != approval.digest
            or snapshot.estimate_digest != estimate.digest
        ):
            raise CustomerExecutionConflict("Customer planning authority changed")
        return snapshot, prd

    def _require_current_authority(self, plan: CustomerExecutionPlan) -> None:
        snapshot, prd = self._authority(plan.customer_id, plan.request_id)
        if (
            snapshot.product_id != plan.product_id
            or snapshot.digest != plan.progress_digest
            or snapshot.requirements_digest != plan.requirements_digest
            or prd.digest != plan.prd_digest
            or snapshot.roadmap_digest != plan.roadmap_digest
            or snapshot.roadmap_approval_digest != plan.roadmap_approval_digest
            or snapshot.estimate_digest != plan.estimate_digest
        ):
            raise CustomerExecutionConflict("Approved customer authority is stale")


def create_governed_codex_adapter(
    state_root: Path,
    configuration: CustomerExecutionConfiguration,
    *,
    environment=None,
    sdk_loader=None,
) -> GovernedCodexCustomerExecutionAdapter:
    provider_store = ProviderOperationStore(state_root / "provider-state")

    def response_sink(receipt, result) -> None:
        provider_store.save_result(receipt.project_id, receipt.provider_operation_id, result)
        provider_store.save_receipt(receipt)

    provider = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            configuration.workspace_root,
            configuration.model,
            configuration.authentication_mode,
            enabled=configuration.enabled,
            live_operation_confirmed=configuration.live_operation_confirmed,
        ),
        environment=environment,
        sdk_loader=sdk_loader,
        response_sink=response_sink,
    )
    policy = ChangePolicy(
        "customer-dashboard-v1",
        configuration.allowed_paths,
        _FORBIDDEN_PATHS,
    )
    provider_service = CodingProviderService(
        CodingProviderRegistry((provider,)),
        provider_store,
        CodingContextBuilder(ContextLimits()),
        ControlledPatchApplier(),
        change_policies=(policy,),
        git_provider_factory=lambda _: _GitProbe(),
    )
    return GovernedCodexCustomerExecutionAdapter(configuration, provider_service)


def inspect_workspace(path: Path) -> WorkspaceIdentity:
    root = path.expanduser()
    if root.is_symlink():
        raise CustomerExecutionPolicyError("Execution workspace cannot be a symbolic link")
    try:
        root = root.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise CustomerExecutionPolicyError("Execution workspace does not exist") from error
    if not root.is_dir() or root == Path(root.anchor):
        raise CustomerExecutionPolicyError("Execution workspace is not a safe directory")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if _git(root, "submodule", "status", "--recursive").strip():
        raise CustomerExecutionPolicyError("Execution workspaces cannot contain submodules")
    branch = _git(root, "branch", "--show-current").strip()
    commit = _git(root, "rev-parse", "HEAD").strip()
    changed = tuple(line[3:] for line in status.splitlines() if len(line) > 3)
    return WorkspaceIdentity(workspace_id_for(root), branch, commit, not changed, changed)


def _require_workspace(value: WorkspaceIdentity) -> None:
    if not value.branch.startswith("agent/"):
        raise CustomerExecutionPolicyError("Execution workspace must use an agent/* branch")
    if not value.clean:
        raise CustomerExecutionPolicyError("Execution workspace must be clean")


def _require_candidate_files(configuration: CustomerExecutionConfiguration) -> None:
    root = configuration.workspace_root.expanduser().resolve()
    for value in configuration.candidate_files:
        try:
            candidate = secure_destination(root, value, allow_missing_leaf=False)
        except Exception as error:
            raise CustomerExecutionPolicyError("Candidate context file is unsafe") from error
        if not candidate.is_file():
            raise CustomerExecutionPolicyError("Candidate context file does not exist")


def _require_same_workspace(
    plan: CustomerExecutionPlan,
    value: WorkspaceIdentity,
    *,
    require_clean: bool,
) -> None:
    if (
        value.workspace_id != plan.workspace_id
        or value.branch != plan.workspace_branch
        or value.commit != plan.workspace_commit
        or (require_clean and not value.clean)
    ):
        raise CustomerExecutionConflict("Product workspace differs from the approved plan")


def _task_id(request_id: str, requirement_id: str) -> str:
    digest = hashlib.sha256(
        f"customer-execution-task:{request_id}:{requirement_id}".encode()
    ).hexdigest()
    return f"execution-task-{digest[:24]}"


def _git(path: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=path,
            env={
                **os.environ,
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
            },
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CustomerExecutionPolicyError("Git workspace inspection failed") from error
    if result.returncode:
        raise CustomerExecutionPolicyError("Execution workspace is not a valid Git repository")
    return result.stdout


class _GitProbe:
    def status(self, workspace):
        value = inspect_workspace(Path(workspace))
        return SimpleNamespace(
            clean=value.clean,
            branch=value.branch,
            changed_paths=value.changed_paths,
        )

    def current_commit(self, workspace):
        return _git(Path(workspace), "rev-parse", "HEAD").strip()

    def diff(self, workspace):
        return _git(Path(workspace), "diff", "--no-ext-diff")

    def diff_numstat(self, workspace):
        output = _git(Path(workspace), "diff", "--numstat", "--no-ext-diff")
        additions = 0
        deletions = 0
        for line in output.splitlines():
            added, deleted, _ = line.split("\t", 2)
            if added == "-" or deleted == "-":
                raise CustomerExecutionPolicyError("Binary product changes are forbidden")
            additions += int(added)
            deletions += int(deleted)
        return additions, deletions
