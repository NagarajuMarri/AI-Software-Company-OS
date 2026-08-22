"""Public controlled managed-product execution façade."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from runtime.integrations.github.models import CreatePullRequestRequest
from runtime.managed_execution.eligibility import (
    ManagedProductExecutionEligibilityService,
)
from runtime.managed_execution.errors import (
    ExecutionApprovalError,
    ExecutionConflictError,
    ExecutionNotFoundError,
    ExecutionPolicyError,
    ExecutionReconciliationError,
    ExecutionValidationError,
)
from runtime.managed_execution.models import (
    AcceptedCodingResult,
    ChangePolicy,
    ExecutionDecision,
    ExecutionMode,
    ExecutionOperationPhase,
    ExecutionPlanStatus,
    ExternalEffectKind,
    ExternalEffectRecord,
    ExternalEffectState,
    GateStatus,
    ManagedCodingRequest,
    ManagedExecutionOperation,
    ManagedProductExecutionPlan,
    QualityGateProfile,
    QualityGateResult,
    ReviewDecisionStatus,
    ReviewEvidence,
    RuntimeTaskMapping,
    TaskExecution,
    ValidatedCodingResult,
    WorkspaceLifecycle,
    WorkspaceRecord,
)
from runtime.managed_execution.policy import (
    evidence_digest,
    safe_relative_path,
    validate_branch,
    validate_coding_result,
    verify_evidence_digest,
)
from runtime.models.work_item import WorkItem
from runtime.models.work_package import WorkPackage
from runtime.planning.models import MaterialisationState, ProposalStatus
from runtime.project_manager.models import MilestoneStatus, TaskStatus
from runtime.tools.models import CommandRequest


class ManagedProductExecutionService:
    def __init__(
        self,
        registry,
        planning_store,
        execution_store,
        manager_loader,
        *,
        workspace_provider=None,
        git_provider_factory=None,
        github_provider=None,
        command_runner=None,
        change_policies=(),
        quality_gate_profiles=(),
        coding_provider_ids=("deterministic",),
        gate_environment=None,
        coding_provider_service=None,
    ):
        self.registry = registry
        self.planning_store = planning_store
        self.store = execution_store
        self.manager_loader = manager_loader
        self.workspace_provider = workspace_provider
        self.git_provider_factory = git_provider_factory
        self.github_provider = github_provider
        self.command_runner = command_runner
        self.change_policies = {policy.policy_id: policy for policy in change_policies}
        self.gate_profiles = {profile.profile_id: profile for profile in quality_gate_profiles}
        self.coding_provider_ids = frozenset(coding_provider_ids)
        self.gate_environment = dict(gate_environment or {})
        self.coding_provider_service = coding_provider_service
        self.eligibility = ManagedProductExecutionEligibilityService(
            registry, planning_store, manager_loader, execution_store)

    def create_execution_request(self, request):
        self.validate_execution_request(request)
        try:
            self.store.load_request(request.project_id, request.execution_request_id)
        except ExecutionNotFoundError:
            self.store.save_request(request)
            return request
        raise ExecutionConflictError("Execution request already exists")

    def validate_execution_request(self, request):
        project = self.registry.get(request.project_id)
        proposal = self.planning_store.load_proposal(
            request.project_id, request.proposal_id)
        if proposal.status != ProposalStatus.APPROVED:
            raise ExecutionValidationError("Proposal is not approved")
        if proposal.materialised_at is None:
            raise ExecutionValidationError("Proposal is not materialised")
        operation = self.planning_store.load_materialisation(
            request.project_id, f"{request.proposal_id}-materialisation")
        if operation.state != MaterialisationState.COMPLETED:
            raise ExecutionValidationError("Materialisation operation is incomplete")
        if request.milestone_id != proposal.milestone_id:
            raise ExecutionValidationError("Execution milestone does not match proposal")
        state = self.manager_loader(request.project_id).current_state()
        milestone = state.milestone(request.milestone_id)
        if milestone.status == MilestoneStatus.COMPLETED:
            raise ExecutionValidationError("Completed milestone cannot execute")
        if request.base_branch != project.default_branch:
            raise ExecutionValidationError("Base branch violates repository policy")
        validate_branch(request.requested_branch_name)
        results = self.eligibility.evaluate(request)
        failures = [reason for result in results for reason in result.reasons]
        if failures:
            raise ExecutionValidationError(
                "; ".join(f"{reason.code}: {reason.message}" for reason in failures))
        return request

    def generate_execution_plan(self, project_id, execution_request_id):
        request = self.store.load_request(project_id, execution_request_id)
        self.validate_execution_request(request)
        proposal = self.planning_store.load_proposal(project_id, request.proposal_id)
        selected = set(request.selected_task_ids)
        maximum_files = request.maximum_changed_files or 25
        maximum_lines = request.maximum_changed_lines or 2_000
        timeout = request.timeout_seconds or 900
        tasks = tuple(
            TaskExecution(
                project_task_id=task.task_id,
                runtime_work_item_id=f"{request.execution_request_id}-{task.task_id}",
                title=task.title,
                objective=task.description,
                dependencies=tuple(dep for dep in task.dependencies if dep in selected),
                role_requirements=task.role_requirements,
                capability_requirements=task.capability_requirements,
                acceptance_criteria=task.acceptance_criteria,
                candidate_files=task.candidate_files,
                allowed_paths=tuple(sorted({
                    str(PurePathParent(path)) for path in task.candidate_files
                })) or (".",),
                forbidden_paths=(
                    ".github/workflows/", ".env", "deploy/", "infrastructure/",
                    "payment/", "migrations/",
                ),
                allowed_commands=tuple(
                    tuple(gate.split()) for gate in task.quality_gates),
                quality_gates=task.quality_gates,
                maximum_changed_files=maximum_files,
                maximum_changed_lines=maximum_lines,
                timeout_seconds=timeout,
                requires_human_review=task.requires_human_review,
                expected_artifacts=(f"{task.task_id}-result",),
            )
            for task in proposal.tasks if task.task_id in selected
        )
        plan_id = f"{execution_request_id}-plan-v1"
        try:
            existing = self.store.load_plan(project_id, plan_id)
            return existing
        except ExecutionNotFoundError:
            pass
        plan = ManagedProductExecutionPlan(
            execution_plan_id=plan_id,
            version=1,
            execution_request_id=execution_request_id,
            project_id=project_id,
            proposal_id=request.proposal_id,
            milestone_id=request.milestone_id,
            ordered_task_executions=tasks,
            dependency_graph=tuple(
                (task.project_task_id, task.dependencies) for task in tasks),
            runtime_work_package_id=f"{execution_request_id}-work-package",
            expected_runtime_work_item_ids=tuple(
                task.runtime_work_item_id for task in tasks),
            role_requirements=tuple(sorted({
                role for task in tasks for role in task.role_requirements})),
            capability_requirements=tuple(sorted({
                capability for task in tasks
                for capability in task.capability_requirements})),
            repository_identity=self.registry.get(project_id).repository_url,
            base_branch=request.base_branch,
            feature_branch=request.requested_branch_name,
            workspace_identity=f"{execution_request_id}-workspace",
            coding_provider_requirement=request.coding_provider_capability,
            quality_gates=tuple(dict.fromkeys(
                gate for task in tasks for gate in task.quality_gates)),
            limits=(("maximum_changed_files", maximum_files),
                    ("maximum_changed_lines", maximum_lines),
                    ("timeout_seconds", timeout)),
            required_approvals=(request.human_approval_policy_id,),
            generated_at=request.requested_at,
            planning_evidence_references=(
                request.proposal_id,
                f"{request.proposal_id}-materialisation",
            ),
        )
        self.store.save_plan(plan)
        operation = ManagedExecutionOperation(
            operation_id=f"{plan_id}-operation",
            project_id=project_id,
            proposal_id=plan.proposal_id,
            milestone_id=plan.milestone_id,
            task_ids=tuple(task.project_task_id for task in tasks),
            runtime_ids=(plan.runtime_work_package_id,
                         *plan.expected_runtime_work_item_ids),
            workspace_id=plan.workspace_identity,
            branch=plan.feature_branch,
            phase=ExecutionOperationPhase.PREPARED,
            created_at=request.requested_at,
            updated_at=request.requested_at,
        )
        self.store.save_operation(operation)
        return plan

    def get_execution_plan(self, project_id, plan_id):
        return self.store.load_plan(project_id, plan_id)

    def approve_execution_plan(self, project_id, plan_id, actor, reason=None):
        plan = self.get_execution_plan(project_id, plan_id)
        if plan.status != ExecutionPlanStatus.AWAITING_APPROVAL:
            raise ExecutionApprovalError("Plan is not awaiting approval")
        if not actor or actor in self.coding_provider_ids:
            raise ExecutionApprovalError("Coding provider cannot approve execution")
        decision = ExecutionDecision(
            f"{plan_id}-approval-{len(plan.decisions)+1}", plan_id, plan.version,
            ReviewDecisionStatus.APPROVED, actor, datetime.now(timezone.utc), reason)
        updated = replace(plan, status=ExecutionPlanStatus.APPROVED,
                          decisions=plan.decisions + (decision,))
        self.store.save_plan(updated)
        return updated

    def reject_execution_plan(self, project_id, plan_id, actor, reason):
        if not reason or not reason.strip():
            raise ExecutionApprovalError("Plan rejection requires a reason")
        plan = self.get_execution_plan(project_id, plan_id)
        if plan.status != ExecutionPlanStatus.AWAITING_APPROVAL:
            raise ExecutionApprovalError("Plan is not awaiting approval")
        decision = ExecutionDecision(
            f"{plan_id}-rejection-{len(plan.decisions)+1}", plan_id, plan.version,
            ReviewDecisionStatus.REJECTED, actor, datetime.now(timezone.utc), reason)
        updated = replace(plan, status=ExecutionPlanStatus.REJECTED,
                          decisions=plan.decisions + (decision,))
        self.store.save_plan(updated)
        return updated

    def create_runtime_work(self, project_id, plan_id):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.PREPARED,
                    ExecutionOperationPhase.RUNTIME_CREATED})
        expected_identity = tuple(
            (task.project_task_id, task.runtime_work_item_id)
            for task in plan.ordered_task_executions)
        effect = self._prepare_effect(
            plan, ExternalEffectKind.RUNTIME_MAPPING, expected_identity)
        existing = self.store.list_mappings(project_id)
        by_task = {mapping.project_task_id: mapping for mapping in existing}
        if all(task.project_task_id in by_task for task in plan.ordered_task_executions):
            values = tuple(by_task[task.project_task_id]
                           for task in plan.ordered_task_executions)
            self._verify_runtime_mappings(plan, values)
            self._complete_effect(effect, expected_identity)
            self._phase(plan, ExecutionOperationPhase.RUNTIME_CREATED)
            return values
        for task in plan.ordered_task_executions:
            mapping = by_task.get(task.project_task_id)
            if mapping is not None and (
                mapping.runtime_work_item_id != task.runtime_work_item_id
                or mapping.runtime_work_package_id != plan.runtime_work_package_id
            ):
                self._effect_reconciliation(
                    plan, effect, "Runtime mapping identity diverges")
        package = WorkPackage(
            plan.runtime_work_package_id,
            f"Managed execution {plan.execution_plan_id}",
            "Approved managed-product execution plan",
            plan.decisions[-1].actor,
        )
        mappings = []
        for task in plan.ordered_task_executions:
            package.add_work_item(WorkItem(
                task.runtime_work_item_id, task.title, task.objective,
                dependencies=[
                    f"{plan.execution_request_id}-{dependency}"
                    for dependency in task.dependencies],
            ))
            mapping = by_task.get(task.project_task_id) or RuntimeTaskMapping(
                task.project_task_id, task.runtime_work_item_id,
                package.id, plan.execution_request_id, plan.execution_plan_id)
            if task.project_task_id not in by_task:
                self.store.save_mapping(project_id, mapping)
            mappings.append(mapping)
        self._verify_runtime_mappings(plan, tuple(mappings))
        self._complete_effect(effect, expected_identity)
        self._phase(plan, ExecutionOperationPhase.RUNTIME_CREATED)
        return tuple(mappings)

    def prepare_workspace(self, project_id, plan_id, *, allow_product_write=False):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.PREPARED,
                    ExecutionOperationPhase.RUNTIME_CREATED,
                    ExecutionOperationPhase.WORKSPACE_READY})
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        if self.workspace_provider is None:
            raise ExecutionValidationError("Workspace provider is not configured")
        project = self.registry.get(project_id)
        if not project.local_path:
            raise ExecutionValidationError("Registered project has no explicit local source")
        source = Path(project.local_path).resolve()
        if not source.is_dir():
            raise ExecutionValidationError("Registered project source is missing")
        for item in source.rglob("*"):
            if item.is_symlink():
                raise ExecutionPolicyError("Source repository contains a symlink")
            if item.is_dir() and item.name == ".git" and item.parent != source:
                raise ExecutionPolicyError("Nested unrelated repository is forbidden")
        source_digest = _tree_digest(source)
        expected_destination = str(
            Path(self.workspace_provider.root)
            / plan.workspace_identity / "repository")
        expected = (
            ("project_id", project_id),
            ("plan_id", plan.execution_plan_id),
            ("plan_version", str(plan.version)),
            ("workspace_id", plan.workspace_identity),
            ("source_repository", project.repository_url),
            ("destination", expected_destination),
            ("base_branch", plan.base_branch),
            ("source_digest", source_digest),
        )
        effect = self._prepare_effect(
            plan, ExternalEffectKind.WORKSPACE_PREPARATION, expected)
        existing = self._reconcile_workspace(plan, effect)
        if existing is not None:
            return existing
        effect = self._start_effect(effect)
        try:
            workspace = self.workspace_provider.create_workspace(
                plan.workspace_identity)
            repository = workspace.local_path / "repository"
            shutil.copytree(source, repository)
        except Exception as error:
            self._uncertain_effect(effect, error)
            raise
        if _tree_digest(repository) != source_digest:
            self._effect_reconciliation(
                plan, effect, "Prepared workspace contents diverge from source")
        record = WorkspaceRecord(
            workspace.workspace_id, project_id, str(repository),
            project.repository_url, plan.base_branch, WorkspaceLifecycle.READY,
            workspace.created_at, datetime.now(timezone.utc))
        self.store.save_workspace(record)
        self._complete_effect(effect, (("workspace_path", str(repository)),))
        self._phase(plan, ExecutionOperationPhase.WORKSPACE_READY)
        return record

    def create_feature_branch(self, project_id, plan_id, *, allow_product_write=False):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.WORKSPACE_READY,
                    ExecutionOperationPhase.BRANCH_READY,
                    ExecutionOperationPhase.RUNTIME_CREATED})
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        record = self.store.load_workspace(project_id, plan.workspace_identity)
        git = self._git(plan.workspace_identity)
        status = git.status(record.local_path)
        base_sha = git.current_commit(record.local_path)
        expected = (
            ("workspace_id", plan.workspace_identity),
            ("repository_path", record.local_path),
            ("base_branch", plan.base_branch),
            ("expected_base_sha", base_sha),
            ("feature_branch", plan.feature_branch),
        )
        effect = self._prepare_effect(
            plan, ExternalEffectKind.BRANCH_CREATION, expected)
        reconciled = self._reconcile_branch(plan, effect, git, record.local_path)
        if reconciled:
            return plan.feature_branch
        if not status.clean or status.branch != plan.base_branch:
            raise ExecutionPolicyError("Workspace base branch is dirty or unexpected")
        validate_branch(plan.feature_branch)
        effect = self._start_effect(effect)
        try:
            git.create_branch(record.local_path, plan.feature_branch)
        except Exception as error:
            self._uncertain_effect(effect, error)
            raise
        if (
            git.current_branch(record.local_path) != plan.feature_branch
            or git.current_commit(record.local_path) != base_sha
        ):
            self._effect_reconciliation(
                plan, effect, "Created branch identity is not exact")
        self._complete_effect(
            effect, (("branch_sha", base_sha),))
        self._phase(plan, ExecutionOperationPhase.BRANCH_READY)
        return plan.feature_branch

    def build_coding_request(self, project_id, plan_id, project_task_id):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.BRANCH_READY,
                    ExecutionOperationPhase.RUNTIME_CREATED,
                    ExecutionOperationPhase.CODING_SUBMITTED,
                    ExecutionOperationPhase.CODING_COMPLETED,
                    ExecutionOperationPhase.PREPARED,
                    ExecutionOperationPhase.WORKSPACE_READY})
        request = self.store.load_request(project_id, plan.execution_request_id)
        task = next(
            (item for item in plan.ordered_task_executions
             if item.project_task_id == project_task_id), None)
        if task is None:
            raise ExecutionValidationError("Task is not in execution plan")
        return ManagedCodingRequest(
            external_task_id=f"{plan.execution_plan_id}-{project_task_id}-attempt-1",
            project_id=project_id,
            workspace_id=plan.workspace_identity,
            branch=plan.feature_branch,
            objective=task.objective,
            acceptance_criteria=task.acceptance_criteria,
            allowed_paths=task.allowed_paths,
            forbidden_paths=task.forbidden_paths,
            candidate_files=task.candidate_files,
            allowed_commands=task.allowed_commands,
            quality_gates=task.quality_gates,
            timeout_seconds=task.timeout_seconds,
            maximum_changed_files=task.maximum_changed_files,
            maximum_changed_lines=task.maximum_changed_lines,
            expected_artifacts=task.expected_artifacts,
            correlation_id=request.correlation_id,
            provider_idempotency_key=(
                f"{plan.execution_plan_id}:{plan.version}:{project_task_id}:1"),
        )

    def submit_coding_task(self, project_id, plan_id, project_task_id):
        coding_request = self.build_coding_request(project_id, plan_id, project_task_id)
        plan = self.get_execution_plan(project_id, plan_id)
        operation = self._operation(plan)
        if operation.phase not in {
            ExecutionOperationPhase.BRANCH_READY,
            ExecutionOperationPhase.RUNTIME_CREATED,
            ExecutionOperationPhase.CODING_SUBMITTED,
        }:
            raise ExecutionApprovalError(
                "Coding submission is not allowed from current phase")
        if coding_request.external_task_id not in operation.external_coding_task_ids:
            operation = replace(
                operation,
                external_coding_task_ids=operation.external_coding_task_ids
                + (coding_request.external_task_id,),
                phase=ExecutionOperationPhase.CODING_SUBMITTED,
                updated_at=datetime.now(timezone.utc),
            )
            self.store.save_operation(operation)
        manager = self.manager_loader(project_id)
        task = manager.current_state().task(project_task_id)
        if task.status == TaskStatus.TODO:
            manager.start_task(project_task_id)
            manager.save()
        return coding_request

    def prepare_provider_operation(
        self, project_id, plan_id, project_task_id, provider_id, *, attempt=1
    ):
        """Bind one submitted managed coding request to durable provider intent."""
        if self.coding_provider_service is None:
            raise ExecutionValidationError("Coding-provider service is not configured")
        coding_request = self.submit_coding_task(
            project_id, plan_id, project_task_id)
        plan = self.get_execution_plan(project_id, plan_id)
        task = next(
            item for item in plan.ordered_task_executions
            if item.project_task_id == project_task_id)
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        operation, provider_request = self.coding_provider_service.prepare(
            plan=plan, task=task, coding_request=coding_request,
            workspace_path=workspace.local_path, provider_id=provider_id,
            attempt=attempt)
        return operation, provider_request

    def accept_provider_result(
        self, project_id, plan_id, project_task_id, operation_id,
        provider_request, policy_id, *, allow_live_provider=False,
        confirm_usage_consumption=False,
    ):
        """Run the provider boundary and feed ASCOS-observed changes into 12.3B."""
        if self.coding_provider_service is None:
            raise ExecutionValidationError("Coding-provider service is not configured")
        plan = self.get_execution_plan(project_id, plan_id)
        task = next(
            item for item in plan.ordered_task_executions
            if item.project_task_id == project_task_id)
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        self.coding_provider_service.submit(
            project_id, operation_id, provider_request,
            allow_live_provider=allow_live_provider,
            confirm_usage_consumption=confirm_usage_consumption)
        operation = self.coding_provider_service.poll(project_id, operation_id)
        if operation.state.value != "RESULT_AVAILABLE":
            raise ExecutionPolicyError("Provider result is not successful")
        result = self.coding_provider_service.result(project_id, operation_id)
        _, manifest = self.coding_provider_service.apply_and_accept(
            project_id, operation_id, workspace_path=workspace.local_path,
            task=task, policy_id=policy_id)
        validated = ValidatedCodingResult(
            provider_request.external_task_id, plan.workspace_identity,
            "SUCCEEDED", tuple(sorted(manifest.changed_paths)),
            manifest.additions, manifest.deletions,
            (), tuple(dict.fromkeys(
                (*provider_request.context.evidence, *result.artifacts,
                 *self.build_coding_request(
                     project_id, plan_id, project_task_id).expected_artifacts))),
            result.summary, result.provider_task_id,
            tuple(range(1, len(result.progress_sequences) + 1)),
        )
        coding_request = self.build_coding_request(
            project_id, plan_id, project_task_id)
        return self.process_coding_result(
            project_id, plan_id, coding_request, validated, policy_id)

    def process_coding_result(
        self, project_id, plan_id, coding_request, result, policy_id
    ):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.CODING_SUBMITTED,
                    ExecutionOperationPhase.CODING_COMPLETED,
                    ExecutionOperationPhase.BRANCH_READY,
                    ExecutionOperationPhase.RUNTIME_CREATED})
        task = next(
            (item for item in plan.ordered_task_executions
             if coding_request.external_task_id
             == f"{plan.execution_plan_id}-{item.project_task_id}-attempt-1"),
            None,
        )
        if task is None:
            raise ExecutionPolicyError("Coding request is not a planned task")
        expected_request = self.build_coding_request(
            project_id, plan_id, task.project_task_id)
        operation = self._operation(plan)
        if (
            coding_request != expected_request
            or coding_request.external_task_id
            not in operation.external_coding_task_ids
        ):
            raise ExecutionPolicyError(
                "Coding result does not match a submitted planned request")
        policy = self._policy(policy_id)
        validated = validate_coding_result(coding_request, result, policy)
        manager = self.manager_loader(project_id)
        if validated.status != "SUCCEEDED":
            task = manager.current_state().task(
                next(task.project_task_id for task in plan.ordered_task_executions
                     if coding_request.external_task_id.startswith(
                         f"{plan.execution_plan_id}-{task.project_task_id}")))
            if task.status in {TaskStatus.TODO, TaskStatus.IN_PROGRESS}:
                manager.block_task(task.task_id, validated.status)
                manager.save()
            self._phase(plan, ExecutionOperationPhase.FAILED,
                        failure=validated.status)
            return validated
        accepted_id = f"{plan.execution_plan_id}-{task.project_task_id}-accepted-1"
        try:
            existing = self.store.load_coding_result(project_id, accepted_id)
            if (
                existing.result != validated
                or existing.provider_operation_id != validated.provider_task_id
            ):
                self._reconciliation(plan, "Accepted coding result changed on retry")
            return existing.result
        except ExecutionNotFoundError:
            pass
        accepted_results = self.store.list_coding_results(project_id)
        if any(
            item.provider_operation_id == validated.provider_task_id
            and item.accepted_result_id != accepted_id
            for item in accepted_results
        ):
            self._reconciliation(
                plan, "Provider operation ID is already bound to another result")
        accepted = AcceptedCodingResult(
            accepted_id,
            plan.execution_plan_id,
            plan.version,
            project_id,
            task.project_task_id,
            coding_request.external_task_id,
            coding_request.workspace_id,
            coding_request.branch,
            validated.provider_task_id,
            validated,
            datetime.now(timezone.utc),
        )
        self.store.save_coding_result(accepted)
        self.store.save_operation(replace(
            operation,
            provider_operation_ids=operation.provider_operation_ids
            + (validated.provider_task_id,),
            phase=ExecutionOperationPhase.CODING_COMPLETED,
            updated_at=datetime.now(timezone.utc),
        ))
        return validated

    def run_quality_gates(self, project_id, plan_id, profile_id):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.CODING_COMPLETED,
                    ExecutionOperationPhase.QUALITY_GATES_COMPLETED})
        profile = self._profile(profile_id, project_id)
        if not profile.ordered_gates:
            raise ExecutionPolicyError("Quality-gate profile is empty")
        if profile.failure_policy not in {"stop-required", "continue"}:
            raise ExecutionPolicyError("Unsupported quality-gate failure policy")
        shell_executables = {
            "sh", "bash", "zsh", "fish", "cmd", "cmd.exe",
            "powershell", "powershell.exe", "pwsh",
        }
        for gate in profile.ordered_gates:
            if (
                not isinstance(gate.command, tuple)
                or not gate.command
                or not gate.command[0]
                or gate.command[0] not in profile.allowed_executables
                or gate.command[0].casefold() in shell_executables
            ):
                raise ExecutionPolicyError(
                    f"Gate {gate.gate_id!r} executable is not allowed")
            if not 0 < gate.timeout_seconds <= 3_600:
                raise ExecutionPolicyError("Quality-gate timeout is not bounded")
        try:
            existing = self.store.load_gate_results(project_id, plan_id)
            self._verify_gate_results(profile, existing)
            return existing
        except ExecutionNotFoundError:
            pass
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        if self.command_runner is None:
            raise ExecutionValidationError("Command runner is not configured")
        results = []
        environment = {
            key: self.gate_environment[key]
            for key in profile.environment_allow_list
            if key in self.gate_environment
        }
        redactions = tuple(profile.redaction_rules) + tuple(environment.values())
        for index, gate in enumerate(profile.ordered_gates, 1):
            started = datetime.now(timezone.utc)
            try:
                command = CommandRequest(
                    gate.command[0], gate.command[1:], Path(workspace.local_path),
                    environment=environment,
                    timeout_seconds=gate.timeout_seconds)
                output = self.command_runner.execute(command)
                status = GateStatus.PASSED if output.exit_code in gate.expected_exit_codes \
                    else GateStatus.FAILED
                result = QualityGateResult(
                    f"{plan_id}-gate-{index}", gate.gate_id, status,
                    output.exit_code,
                    _bounded_redacted(output.stdout, redactions),
                    _bounded_redacted(output.stderr, redactions),
                    output.started_at, output.completed_at)
            except Exception as error:
                completed = datetime.now(timezone.utc)
                status = GateStatus.TIMED_OUT if "timeout" in type(error).__name__.lower() \
                    else GateStatus.ERROR
                result = QualityGateResult(
                    f"{plan_id}-gate-{index}", gate.gate_id, status,
                None, "", _bounded_redacted(str(error), redactions),
                started, completed)
            results.append(result)
            if (
                profile.failure_policy == "stop-required"
                and gate.required
                and result.status != GateStatus.PASSED
            ):
                break
        for gate in profile.ordered_gates[len(results):]:
            results.append(QualityGateResult(
                f"{plan_id}-gate-{len(results)+1}", gate.gate_id,
                GateStatus.NOT_RUN, None, "", "", datetime.now(timezone.utc),
                datetime.now(timezone.utc)))
        values = tuple(results)
        self._verify_gate_results(profile, values, require_success=False)
        self.store.save_gate_results(project_id, plan_id, values)
        if any(gate.required and result.status != GateStatus.PASSED
               for gate, result in zip(profile.ordered_gates, values)):
            raise ExecutionPolicyError("Required quality gate did not pass")
        operation = self._operation(plan)
        self.store.save_operation(replace(
            operation,
            gate_execution_ids=tuple(result.gate_execution_id for result in values),
            phase=ExecutionOperationPhase.QUALITY_GATES_COMPLETED,
            updated_at=datetime.now(timezone.utc)))
        return values

    def generate_review_evidence(
        self, project_id, plan_id, accepted_result_ids=None, *, base_commit=None
    ):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.QUALITY_GATES_COMPLETED})
        gates = self.store.load_gate_results(project_id, plan_id)
        profile = self._profile(
            self.store.load_request(
                project_id, plan.execution_request_id).quality_gate_profile_id,
            project_id)
        self._verify_gate_results(profile, gates)
        identifiers = tuple(accepted_result_ids or ())
        if not identifiers or any(not isinstance(item, str) for item in identifiers):
            raise ExecutionPolicyError(
                "Evidence requires persisted accepted coding-result IDs")
        accepted = tuple(
            self.store.load_coding_result(project_id, identifier)
            for identifier in identifiers)
        expected_tasks = {
            task.project_task_id for task in plan.ordered_task_executions}
        actual_tasks = {item.project_task_id for item in accepted}
        if actual_tasks != expected_tasks or len(actual_tasks) != len(accepted):
            raise ExecutionPolicyError(
                "Accepted coding results do not exactly cover planned tasks")
        for item in accepted:
            if (
                item.execution_plan_id != plan_id
                or item.plan_version != plan.version
                or item.project_id != project_id
                or item.workspace_id != plan.workspace_identity
                or item.branch != plan.feature_branch
                or item.result.status != "SUCCEEDED"
                or item.provider_operation_id != item.result.provider_task_id
            ):
                raise ExecutionPolicyError(
                    "Accepted coding result identity differs from the plan")
        branch_effect = self.store.load_effect(
            project_id,
            self._effect_id(plan, ExternalEffectKind.BRANCH_CREATION))
        expected_base = dict(branch_effect.expected_identity)[
            "expected_base_sha"]
        if base_commit is not None and base_commit != expected_base:
            raise ExecutionPolicyError("Evidence base commit differs from branch intent")
        changed_files = tuple(sorted({
            path for item in accepted for path in item.result.changed_files}))
        additions = sum(item.result.additions for item in accepted)
        deletions = sum(item.result.deletions for item in accepted)
        payload = {
            "evidence_id": f"{plan_id}-evidence-1",
            "execution_plan_id": plan_id,
            "plan_version": plan.version,
            "project_id": project_id,
            "task_ids": tuple(task.project_task_id for task in plan.ordered_task_executions),
            "workspace_id": plan.workspace_identity,
            "branch": plan.feature_branch,
            "base_commit": expected_base,
            "resulting_commit": None,
            "changed_files": changed_files,
            "additions": additions,
            "deletions": deletions,
            "provider_result_reference": ",".join(
                item.provider_operation_id for item in accepted),
            "accepted_coding_result_ids": identifiers,
            "gate_execution_ids": tuple(
                result.gate_execution_id for result in gates),
            "quality_gate_results": gates,
            "acceptance_criteria_mapping": tuple(
                (task.project_task_id, task.acceptance_criteria)
                for task in plan.ordered_task_executions),
            "unresolved_risks": (),
            "warnings": (),
            "policy_exceptions": (),
            "reviewer_required_flags": ("human-completion-approval",),
            "generated_at": datetime.now(timezone.utc),
        }
        digest = evidence_digest(payload)
        evidence = ReviewEvidence(**payload, integrity_digest=digest)
        self.store.save_evidence(evidence)
        operation = self._operation(plan)
        self.store.save_operation(replace(
            operation, evidence_ids=operation.evidence_ids + (evidence.evidence_id,),
            phase=ExecutionOperationPhase.REVIEW_REQUIRED,
            updated_at=datetime.now(timezone.utc)))
        self.store.save_plan(replace(plan, status=ExecutionPlanStatus.REVIEW_REQUIRED))
        return evidence

    def approve_review(self, project_id, plan_id, actor, reason=None):
        plan = self.get_execution_plan(project_id, plan_id)
        if plan.status != ExecutionPlanStatus.REVIEW_REQUIRED:
            raise ExecutionApprovalError("Execution is not awaiting review")
        if not actor or actor in self.coding_provider_ids:
            raise ExecutionApprovalError("Coding provider cannot approve review")
        evidence = self._verified_evidence(plan)
        decision = ExecutionDecision(
            f"{plan_id}-review-{len(plan.decisions)+1}", plan_id, plan.version,
            ReviewDecisionStatus.APPROVED, actor, datetime.now(timezone.utc),
            reason, evidence.integrity_digest)
        updated = replace(plan, decisions=plan.decisions + (decision,))
        self.store.save_plan(updated)
        operation = self._operation(plan)
        self.store.save_operation(replace(
            operation, approval_ids=operation.approval_ids + (decision.decision_id,),
            phase=ExecutionOperationPhase.REVIEW_APPROVED,
            updated_at=datetime.now(timezone.utc)))
        manager = self.manager_loader(project_id)
        changed = False
        for task in plan.ordered_task_executions:
            managed = manager.current_state().task(task.project_task_id)
            submitted = any(
                identifier.startswith(
                    f"{plan.execution_plan_id}-{task.project_task_id}-")
                for identifier in operation.external_coding_task_ids
            )
            if submitted and managed.status == TaskStatus.IN_PROGRESS:
                manager.complete_task(task.project_task_id)
                changed = True
        if changed:
            manager.save()
        return decision

    def reject_review(self, project_id, plan_id, actor, reason):
        if not reason or not reason.strip():
            raise ExecutionApprovalError("Review rejection requires a reason")
        return self._review_decision(
            project_id, plan_id, actor, reason, ReviewDecisionStatus.REJECTED)

    def request_correction(self, project_id, plan_id, actor, reason):
        if not reason or not reason.strip():
            raise ExecutionApprovalError("Correction request requires a reason")
        return self._review_decision(
            project_id, plan_id, actor, reason,
            ReviewDecisionStatus.CORRECTION_REQUESTED)

    def create_commit(self, project_id, plan_id, *, allow_product_write=False):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.REVIEW_APPROVED,
                    ExecutionOperationPhase.COMMIT_CREATED})
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        operation = self._operation(plan)
        if operation.commit_sha:
            self._verified_evidence(plan)
            return operation.commit_sha
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        evidence = self._verified_evidence(plan)
        self._require_review_approval(plan, evidence)
        git = self._git(plan.workspace_identity)
        message = (
            f"ASCOS {plan.execution_plan_id}: approved changes "
            f"[ASCOS-EVIDENCE:{evidence.integrity_digest}]")
        try:
            existing_effect = self.store.load_effect(
                project_id,
                self._effect_id(plan, ExternalEffectKind.COMMIT_CREATION))
            expected = existing_effect.expected_identity
        except ExecutionNotFoundError:
            status = git.status(workspace.local_path)
            if set(status.changed_paths) != set(evidence.changed_files):
                raise ExecutionReconciliationError("Workspace changed after review")
            parent_sha = git.current_commit(workspace.local_path)
            expected = (
                ("workspace_id", plan.workspace_identity),
                ("repository_path", workspace.local_path),
                ("branch", plan.feature_branch),
                ("evidence_id", evidence.evidence_id),
                ("evidence_digest", evidence.integrity_digest),
                ("expected_parent_sha", parent_sha),
                ("reviewed_paths", "\n".join(evidence.changed_files)),
                ("commit_message", message),
            )
        effect = self._prepare_effect(
            plan, ExternalEffectKind.COMMIT_CREATION, expected)
        reconciled_sha = self._reconcile_commit(
            plan, effect, git, workspace.local_path)
        if reconciled_sha is not None:
            return reconciled_sha
        status = git.status(workspace.local_path)
        if set(status.changed_paths) != set(evidence.changed_files):
            raise ExecutionReconciliationError("Workspace changed after review")
        effect = self._start_effect(effect)
        try:
            git.add(workspace.local_path, evidence.changed_files)
            commit = git.commit(workspace.local_path, message)
        except Exception as error:
            self._uncertain_effect(effect, error)
            raise
        self._verify_commit(
            plan, effect, git, workspace.local_path, commit.sha)
        self._complete_effect(effect, (("commit_sha", commit.sha),))
        self.store.save_operation(replace(
            operation, commit_sha=commit.sha,
            phase=ExecutionOperationPhase.COMMIT_CREATED,
            updated_at=datetime.now(timezone.utc)))
        return commit.sha

    def push_branch(self, project_id, plan_id, *, allow_product_write=False):
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.COMMIT_CREATED,
                    ExecutionOperationPhase.PUSH_COMPLETED})
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        operation = self._operation(plan)
        if operation.push_state == "PUSHED":
            self._verified_evidence(plan)
            return "PUSHED"
        if not operation.commit_sha:
            raise ExecutionValidationError("Push requires a controlled commit")
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        evidence = self._verified_evidence(plan)
        self._require_review_approval(plan, evidence)
        git = self._git(plan.workspace_identity)
        expected = (
            ("remote", "origin"),
            ("remote_identity", plan.repository_identity),
            ("branch", plan.feature_branch),
            ("expected_commit_sha", operation.commit_sha),
            ("expected_remote_ref", f"refs/heads/{plan.feature_branch}"),
            ("evidence_digest", evidence.integrity_digest),
        )
        effect = self._prepare_effect(
            plan, ExternalEffectKind.BRANCH_PUSH, expected)
        if self._reconcile_push(plan, effect, git, workspace.local_path):
            return "PUSHED"
        effect = self._start_effect(effect)
        try:
            git.push(workspace.local_path, "origin", plan.feature_branch)
        except Exception as error:
            self._uncertain_effect(effect, error)
            raise
        remote_sha = git.remote_branch_commit(
            workspace.local_path, "origin", plan.feature_branch)
        if remote_sha != operation.commit_sha:
            self._effect_reconciliation(
                plan, effect, "Remote branch does not point to reviewed commit")
        self._complete_effect(effect, (("remote_sha", remote_sha),))
        self.store.save_operation(replace(
            operation, push_state="PUSHED",
            phase=ExecutionOperationPhase.PUSH_COMPLETED,
            updated_at=datetime.now(timezone.utc)))
        return "PUSHED"

    def create_draft_pull_request(
        self, project_id, plan_id, *, allow_product_write=False
    ):
        existing_plan = self.get_execution_plan(project_id, plan_id)
        existing_operation = self._operation(existing_plan)
        if (
            existing_plan.status == ExecutionPlanStatus.SUCCEEDED
            and existing_operation.phase == ExecutionOperationPhase.COMPLETED
            and existing_operation.pr_number is not None
        ):
            self._verified_evidence(existing_plan)
            return self.github_provider.get_pull_request(
                existing_plan.repository_identity,
                existing_operation.pr_number)
        plan = self._require_execution_allowed(
            project_id, plan_id,
            phases={ExecutionOperationPhase.PUSH_COMPLETED,
                    ExecutionOperationPhase.PR_CREATED})
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        operation = self._operation(plan)
        if operation.pr_number is not None:
            self._verified_evidence(plan)
            return self.github_provider.get_pull_request(
                plan.repository_identity, operation.pr_number)
        if operation.push_state != "PUSHED":
            raise ExecutionValidationError("Draft PR requires completed push")
        evidence = self._verified_evidence(plan)
        self._require_review_approval(plan, evidence)
        marker = (
            f"ASCOS-EFFECT:{plan.execution_plan_id}:v{plan.version}:"
            f"{operation.commit_sha}")
        body = self._expected_pr_body(plan, marker)
        title = f"ASCOS managed execution: {plan.execution_plan_id}"
        expected = (
            ("repository", plan.repository_identity),
            ("base_branch", plan.base_branch),
            ("head_branch", plan.feature_branch),
            ("expected_head_sha", operation.commit_sha or ""),
            ("marker", marker),
            ("title_digest", _text_digest(title)),
            ("body_digest", _text_digest(body)),
            ("evidence_digest", evidence.integrity_digest),
        )
        effect = self._prepare_effect(
            plan, ExternalEffectKind.DRAFT_PR_CREATION, expected)
        existing = self._reconcile_pr(plan, effect, title, body)
        if existing is not None:
            return existing
        effect = self._start_effect(effect)
        try:
            pr = self.github_provider.create_draft_pull_request(
                CreatePullRequestRequest(
                    plan.repository_identity, title, body,
                    plan.base_branch, plan.feature_branch, draft=True))
        except Exception as error:
            self._uncertain_effect(effect, error)
            raise
        if not pr.draft:
            self._effect_reconciliation(
                plan, effect, "Provider did not create a draft PR")
        matches = self._reconcile_pr(plan, effect, title, body)
        if matches is None or matches.number != pr.number:
            self._effect_reconciliation(
                plan, effect, "Created draft PR could not be exactly verified")
        return matches

    def reconcile_execution(self, project_id, plan_id):
        plan = self.get_execution_plan(project_id, plan_id)
        operation = self._operation(plan)
        mappings = self.store.list_mappings(project_id)
        expected = set(plan.expected_runtime_work_item_ids)
        actual = {
            mapping.runtime_work_item_id for mapping in mappings
            if mapping.runtime_work_package_id == plan.runtime_work_package_id}
        if actual and not actual.issubset(expected):
            self._reconciliation(plan, "Runtime mappings diverge from execution plan")
        effects = self.store.list_effects(project_id)
        for effect in effects:
            if effect.execution_plan_id != plan_id:
                continue
            if effect.state == ExternalEffectState.RECONCILIATION_REQUIRED:
                raise ExecutionReconciliationError(
                    effect.failure_details or "External effect requires reconciliation")
            if effect.kind == ExternalEffectKind.RUNTIME_MAPPING:
                mappings = tuple(
                    mapping for mapping in self.store.list_mappings(project_id)
                    if mapping.runtime_work_package_id
                    == plan.runtime_work_package_id)
                if mappings:
                    self._verify_runtime_mappings(plan, mappings, allow_partial=True)
            elif effect.kind == ExternalEffectKind.WORKSPACE_PREPARATION:
                self._reconcile_workspace(plan, effect)
            elif effect.kind == ExternalEffectKind.BRANCH_CREATION:
                workspace = self.store.load_workspace(
                    project_id, plan.workspace_identity)
                self._reconcile_branch(
                    plan, effect, self._git(plan.workspace_identity),
                    workspace.local_path)
            elif effect.kind == ExternalEffectKind.COMMIT_CREATION:
                workspace = self.store.load_workspace(
                    project_id, plan.workspace_identity)
                self._reconcile_commit(
                    plan, effect, self._git(plan.workspace_identity),
                    workspace.local_path)
            elif effect.kind == ExternalEffectKind.BRANCH_PUSH:
                workspace = self.store.load_workspace(
                    project_id, plan.workspace_identity)
                self._reconcile_push(
                    plan, effect, self._git(plan.workspace_identity),
                    workspace.local_path)
            elif effect.kind == ExternalEffectKind.DRAFT_PR_CREATION:
                expected_values = dict(effect.expected_identity)
                self._reconcile_pr(
                    plan, effect,
                    f"ASCOS managed execution: {plan.execution_plan_id}",
                    self._expected_pr_body(plan, expected_values["marker"]))
        if operation.phase == ExecutionOperationPhase.RECONCILIATION_REQUIRED:
            raise ExecutionReconciliationError(
                operation.failure_details or "Operator reconciliation required")
        return self._operation(self.get_execution_plan(project_id, plan_id))

    def cancel_execution(self, project_id, plan_id, actor, reason):
        if not actor or not reason:
            raise ExecutionApprovalError("Cancellation requires actor and reason")
        plan = self.get_execution_plan(project_id, plan_id)
        if plan.status in self._terminal_statuses():
            raise ExecutionApprovalError("Terminal execution cannot be cancelled")
        updated = replace(plan, status=ExecutionPlanStatus.CANCELLED)
        self.store.save_plan(updated)
        self._phase(plan, ExecutionOperationPhase.CANCELLED, failure=reason)
        return updated

    def get_execution_status(self, project_id, plan_id):
        plan = self.get_execution_plan(project_id, plan_id)
        operation = self._operation(plan)
        return {
            "project_id": project_id,
            "execution_plan_id": plan_id,
            "plan_status": plan.status.value,
            "operation_phase": operation.phase.value,
        }

    def list_executions(self, project_id):
        self.registry.get(project_id)
        return self.store.list_plans(project_id)

    def _require_execution_allowed(self, project_id, plan_id, *, phases):
        plan = self.get_execution_plan(project_id, plan_id)
        if plan.status in self._terminal_statuses():
            raise ExecutionApprovalError(
                f"Execution cannot continue from terminal status {plan.status.value}")
        if not any(decision.status == ReviewDecisionStatus.APPROVED
                   and decision.plan_version == plan.version
                   for decision in plan.decisions):
            raise ExecutionApprovalError("Exact execution plan is not approved")
        operation = self._operation(plan)
        if operation.phase in {
            ExecutionOperationPhase.FAILED,
            ExecutionOperationPhase.CANCELLED,
            ExecutionOperationPhase.COMPLETED,
            ExecutionOperationPhase.RECONCILIATION_REQUIRED,
        }:
            raise ExecutionApprovalError(
                f"Execution cannot continue from phase {operation.phase.value}")
        if operation.phase not in phases:
            raise ExecutionApprovalError(
                f"Operation is not allowed from phase {operation.phase.value}")
        return plan

    @staticmethod
    def _terminal_statuses():
        return {
            ExecutionPlanStatus.FAILED,
            ExecutionPlanStatus.CANCELLED,
            ExecutionPlanStatus.SUCCEEDED,
            ExecutionPlanStatus.REJECTED,
            ExecutionPlanStatus.SUPERSEDED,
            ExecutionPlanStatus.RECONCILIATION_REQUIRED,
        }

    def _write_allowed(self, request, allow_product_write):
        if request.execution_mode != ExecutionMode.CONTROLLED_WRITE:
            raise ExecutionPolicyError("Only CONTROLLED_WRITE permits repository mutation")
        if not allow_product_write:
            raise ExecutionPolicyError("--allow-product-write is required")

    def _operation(self, plan):
        return self.store.load_operation(
            plan.project_id, f"{plan.execution_plan_id}-operation")

    def _phase(self, plan, phase, *, failure=None):
        operation = self._operation(plan)
        self.store.save_operation(replace(
            operation, phase=phase, failure_details=failure,
            updated_at=datetime.now(timezone.utc)))

    def _reconciliation(self, plan, details):
        self._phase(plan, ExecutionOperationPhase.RECONCILIATION_REQUIRED,
                    failure=details)
        self.store.save_plan(replace(
            plan, status=ExecutionPlanStatus.RECONCILIATION_REQUIRED))
        raise ExecutionReconciliationError(details)

    def _effect_id(self, plan, kind):
        digest = hashlib.sha256(
            f"{plan.execution_plan_id}:{plan.version}:{kind.value}".encode()
        ).hexdigest()[:24]
        return f"effect-{digest}"

    def _prepare_effect(self, plan, kind, expected_identity):
        identifier = self._effect_id(plan, kind)
        expected_identity = tuple(expected_identity)
        try:
            effect = self.store.load_effect(plan.project_id, identifier)
            if (
                effect.execution_plan_id != plan.execution_plan_id
                or effect.plan_version != plan.version
                or effect.kind != kind
                or effect.expected_identity != expected_identity
            ):
                self._effect_reconciliation(
                    plan, effect, "External effect intent identity changed")
            if effect.state == ExternalEffectState.RECONCILIATION_REQUIRED:
                raise ExecutionReconciliationError(
                    effect.failure_details or "External effect requires reconciliation")
            return effect
        except ExecutionNotFoundError:
            now = datetime.now(timezone.utc)
            effect = ExternalEffectRecord(
                identifier, plan.project_id, plan.execution_plan_id, plan.version,
                kind, ExternalEffectState.PREPARED, expected_identity,
                created_at=now, updated_at=now)
            self.store.save_effect(effect)
            return effect

    def _start_effect(self, effect):
        if effect.state == ExternalEffectState.COMPLETED:
            return effect
        updated = replace(
            effect, state=ExternalEffectState.IN_PROGRESS,
            updated_at=datetime.now(timezone.utc), failure_details=None)
        self.store.save_effect(updated)
        return updated

    def _complete_effect(self, effect, result_identity):
        updated = replace(
            effect, state=ExternalEffectState.COMPLETED,
            result_identity=tuple(result_identity),
            updated_at=datetime.now(timezone.utc), failure_details=None)
        self.store.save_effect(updated)
        return updated

    def _uncertain_effect(self, effect, error):
        try:
            self.store.save_effect(replace(
                effect, state=ExternalEffectState.UNCERTAIN,
                updated_at=datetime.now(timezone.utc),
                failure_details=f"{type(error).__name__}: {error}"))
        except Exception:
            pass

    def _effect_reconciliation(self, plan, effect, details):
        try:
            self.store.save_effect(replace(
                effect, state=ExternalEffectState.RECONCILIATION_REQUIRED,
                updated_at=datetime.now(timezone.utc),
                failure_details=details))
        finally:
            self._reconciliation(plan, details)

    def _reconcile_workspace(self, plan, effect):
        expected = dict(effect.expected_identity)
        repository = Path(expected["destination"])
        workspace_path = repository.parent
        if not workspace_path.exists():
            return None
        if not repository.is_dir():
            self._effect_reconciliation(
                plan, effect, "Expected workspace exists without repository")
        if _tree_digest(repository) != expected["source_digest"]:
            self._effect_reconciliation(
                plan, effect, "Existing workspace contents diverge")
        workspace = self.workspace_provider.inspect_workspace(plan.workspace_identity)
        try:
            record = self.store.load_workspace(
                plan.project_id, plan.workspace_identity)
            if (
                record.local_path != str(repository)
                or record.repository_identity != expected["source_repository"]
                or record.base_branch != expected["base_branch"]
            ):
                self._effect_reconciliation(
                    plan, effect, "Workspace record identity diverges")
        except ExecutionNotFoundError:
            record = WorkspaceRecord(
                workspace.workspace_id, plan.project_id, str(repository),
                expected["source_repository"], expected["base_branch"],
                WorkspaceLifecycle.READY, workspace.created_at,
                datetime.now(timezone.utc))
            self.store.save_workspace(record)
        self._complete_effect(effect, (("workspace_path", str(repository)),))
        self._phase(plan, ExecutionOperationPhase.WORKSPACE_READY)
        return record

    def _reconcile_branch(self, plan, effect, git, repository_path):
        expected = dict(effect.expected_identity)
        branch_sha = git.branch_commit(repository_path, plan.feature_branch)
        if branch_sha is None:
            return False
        if branch_sha != expected["expected_base_sha"]:
            self._effect_reconciliation(
                plan, effect, "Feature branch points to unexpected commit")
        self._complete_effect(effect, (("branch_sha", branch_sha),))
        self._phase(plan, ExecutionOperationPhase.BRANCH_READY)
        return True

    def _verify_commit(self, plan, effect, git, repository_path, commit_sha):
        expected = dict(effect.expected_identity)
        if (
            git.current_branch(repository_path) != expected["branch"]
            or git.commit_parent(repository_path, commit_sha)
            != expected["expected_parent_sha"]
            or git.commit_message(repository_path, commit_sha)
            != expected["commit_message"]
            or tuple(sorted(git.commit_changed_paths(repository_path, commit_sha)))
            != tuple(sorted(expected["reviewed_paths"].splitlines()))
        ):
            self._effect_reconciliation(
                plan, effect, "Commit does not exactly match reviewed intent")

    def _reconcile_commit(self, plan, effect, git, repository_path):
        expected = dict(effect.expected_identity)
        current_sha = git.current_commit(repository_path)
        if current_sha == expected["expected_parent_sha"]:
            return None
        self._verify_commit(plan, effect, git, repository_path, current_sha)
        self._complete_effect(effect, (("commit_sha", current_sha),))
        operation = self._operation(plan)
        self.store.save_operation(replace(
            operation, commit_sha=current_sha,
            phase=ExecutionOperationPhase.COMMIT_CREATED,
            updated_at=datetime.now(timezone.utc)))
        return current_sha

    def _reconcile_push(self, plan, effect, git, repository_path):
        expected = dict(effect.expected_identity)
        remote_sha = git.remote_branch_commit(
            repository_path, expected["remote"], expected["branch"])
        if remote_sha is None:
            return False
        if remote_sha != expected["expected_commit_sha"]:
            self._effect_reconciliation(
                plan, effect, "Remote branch points to unexpected commit")
        self._complete_effect(effect, (("remote_sha", remote_sha),))
        operation = self._operation(plan)
        self.store.save_operation(replace(
            operation, push_state="PUSHED",
            phase=ExecutionOperationPhase.PUSH_COMPLETED,
            updated_at=datetime.now(timezone.utc)))
        return True

    def _reconcile_pr(self, plan, effect, title, body):
        expected = dict(effect.expected_identity)
        matches = []
        divergent = []
        for item in self.github_provider.list_pull_requests(
            plan.repository_identity):
            if expected["marker"] in item.body:
                if (
                    item.base_branch == plan.base_branch
                    and item.head_branch == plan.feature_branch
                    and item.draft
                    and item.title == title
                    and item.body == body
                ):
                    matches.append(item)
                else:
                    divergent.append(item)
        if divergent or len(matches) > 1:
            self._effect_reconciliation(
                plan, effect, "Pull-request marker has divergent or multiple matches")
        if not matches:
            return None
        pr = matches[0]
        branch = self.github_provider.get_branch(
            plan.repository_identity, plan.feature_branch)
        if branch.commit_sha != expected["expected_head_sha"]:
            self._effect_reconciliation(
                plan, effect, "Draft PR head differs from reviewed commit")
        self._complete_effect(effect, (("pr_number", str(pr.number)),))
        operation = self._operation(plan)
        created = replace(
            operation, pr_number=pr.number,
            pr_url=f"offline://pull/{pr.number}",
            phase=ExecutionOperationPhase.PR_CREATED,
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(created)
        self.store.save_operation(replace(
            created, phase=ExecutionOperationPhase.COMPLETED,
            updated_at=datetime.now(timezone.utc)))
        self.store.save_plan(replace(plan, status=ExecutionPlanStatus.SUCCEEDED))
        return pr

    def _verify_runtime_mappings(self, plan, mappings, *, allow_partial=False):
        by_task = {mapping.project_task_id: mapping for mapping in mappings}
        expected_tasks = {
            task.project_task_id: task.runtime_work_item_id
            for task in plan.ordered_task_executions}
        if not allow_partial and set(by_task) != set(expected_tasks):
            raise ExecutionReconciliationError("Runtime mappings are incomplete")
        for task_id, mapping in by_task.items():
            if (
                task_id not in expected_tasks
                or mapping.runtime_work_item_id != expected_tasks[task_id]
                or mapping.runtime_work_package_id
                != plan.runtime_work_package_id
                or mapping.correlation_id != plan.execution_request_id
                or mapping.causation_id != plan.execution_plan_id
            ):
                self._reconciliation(plan, "Runtime mapping identity diverges")

    def _verified_evidence(self, plan):
        evidence = self.store.load_evidence(
            plan.project_id, f"{plan.execution_plan_id}-evidence-1")
        verify_evidence_digest(evidence)
        if (
            evidence.execution_plan_id != plan.execution_plan_id
            or evidence.plan_version != plan.version
            or evidence.project_id != plan.project_id
            or evidence.workspace_id != plan.workspace_identity
            or evidence.branch != plan.feature_branch
        ):
            raise ExecutionPolicyError("Review evidence identity differs from plan")
        accepted = tuple(
            self.store.load_coding_result(plan.project_id, identifier)
            for identifier in evidence.accepted_coding_result_ids)
        expected_tasks = {
            task.project_task_id for task in plan.ordered_task_executions}
        if (
            {item.project_task_id for item in accepted} != expected_tasks
            or len(accepted) != len(expected_tasks)
            or tuple(task.project_task_id for task in plan.ordered_task_executions)
            != evidence.task_ids
        ):
            raise ExecutionPolicyError("Evidence coding-result task binding is invalid")
        for item in accepted:
            if (
                item.execution_plan_id != plan.execution_plan_id
                or item.plan_version != plan.version
                or item.project_id != plan.project_id
                or item.external_task_id
                != f"{plan.execution_plan_id}-{item.project_task_id}-attempt-1"
                or item.workspace_id != plan.workspace_identity
                or item.branch != plan.feature_branch
                or item.result.status != "SUCCEEDED"
                or item.provider_operation_id != item.result.provider_task_id
            ):
                raise ExecutionPolicyError(
                    "Evidence contains an invalid accepted coding result")
        changed_files = tuple(sorted({
            path for item in accepted for path in item.result.changed_files}))
        if (
            changed_files != evidence.changed_files
            or sum(item.result.additions for item in accepted) != evidence.additions
            or sum(item.result.deletions for item in accepted) != evidence.deletions
            or ",".join(item.provider_operation_id for item in accepted)
            != evidence.provider_result_reference
        ):
            raise ExecutionPolicyError(
                "Evidence change summary differs from accepted coding results")
        branch_effect = self.store.load_effect(
            plan.project_id,
            self._effect_id(plan, ExternalEffectKind.BRANCH_CREATION))
        if evidence.base_commit != dict(
            branch_effect.expected_identity)["expected_base_sha"]:
            raise ExecutionPolicyError("Evidence base commit differs from branch intent")
        gates = self.store.load_gate_results(
            plan.project_id, plan.execution_plan_id)
        if (
            tuple(result.gate_execution_id for result in gates)
            != evidence.gate_execution_ids
            or gates != evidence.quality_gate_results
        ):
            raise ExecutionPolicyError("Evidence quality-gate binding is invalid")
        return evidence

    @staticmethod
    def _require_review_approval(plan, evidence):
        if not any(
            decision.status == ReviewDecisionStatus.APPROVED
            and decision.plan_version == plan.version
            and decision.evidence_digest == evidence.integrity_digest
            for decision in plan.decisions
        ):
            raise ExecutionApprovalError(
                "Exact review evidence is not human-approved")

    @staticmethod
    def _verify_gate_results(profile, results, *, require_success=True):
        if len(results) != len(profile.ordered_gates):
            raise ExecutionPolicyError(
                "Every configured quality gate requires one durable result")
        if len({result.gate_id for result in results}) != len(results):
            raise ExecutionPolicyError("Quality-gate results are duplicated")
        for gate, result in zip(profile.ordered_gates, results):
            if gate.gate_id != result.gate_id:
                raise ExecutionPolicyError("Quality-gate result ordering differs")
            if (
                require_success
                and gate.required
                and result.status != GateStatus.PASSED
            ):
                raise ExecutionPolicyError("Required quality gate did not pass")

    def _expected_pr_body(self, plan, marker):
        evidence = self._verified_evidence(plan)
        operation = self._operation(plan)
        return (
            f"<!-- {marker} -->\n\n"
            f"ASCOS execution plan: {plan.execution_plan_id}\n\n"
            f"Project tasks: {', '.join(evidence.task_ids)}\n\n"
            f"Acceptance criteria: {evidence.acceptance_criteria_mapping}\n\n"
            f"Quality gates: {[(x.gate_id, x.status.value) for x in evidence.quality_gate_results]}\n\n"
            f"Review approvals: {operation.approval_ids}\n\n"
            "Known limitations: deterministic offline managed execution; no merge or deployment."
        )

    def _policy(self, policy_id):
        try:
            return self.change_policies[policy_id]
        except KeyError as error:
            raise ExecutionValidationError("Unknown change policy") from error

    def _profile(self, profile_id, project_id):
        try:
            profile = self.gate_profiles[profile_id]
        except KeyError as error:
            raise ExecutionValidationError("Unknown quality-gate profile") from error
        if profile.project_id != project_id:
            raise ExecutionValidationError("Quality-gate profile project mismatch")
        return profile

    def _git(self, workspace_id):
        if self.git_provider_factory is None:
            raise ExecutionValidationError("Git provider is not configured")
        return self.git_provider_factory(workspace_id)

    def _review_decision(self, project_id, plan_id, actor, reason, status):
        plan = self.get_execution_plan(project_id, plan_id)
        if plan.status != ExecutionPlanStatus.REVIEW_REQUIRED:
            raise ExecutionApprovalError("Execution is not awaiting review")
        if actor in self.coding_provider_ids:
            raise ExecutionApprovalError("Coding provider cannot review itself")
        evidence = self._verified_evidence(plan)
        decision = ExecutionDecision(
            f"{plan_id}-review-{len(plan.decisions)+1}", plan_id, plan.version,
            status, actor, datetime.now(timezone.utc), reason,
            evidence.integrity_digest)
        self.store.save_plan(replace(
            plan, decisions=plan.decisions + (decision,),
            status=ExecutionPlanStatus.FAILED))
        return decision


def PurePathParent(value: str) -> str:
    normalized = safe_relative_path(value)
    parent = str(Path(normalized).parent).replace("\\", "/")
    return "" if parent == "." else f"{parent}/"


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise ExecutionPolicyError("Workspace digest rejects symlinks")
        if path.is_file():
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_redacted(value: str, redactions, *, limit=4_000) -> str:
    bounded = value
    for secret in sorted(
        {item for item in redactions if item}, key=len, reverse=True
    ):
        bounded = bounded.replace(secret, "[REDACTED]")
    bounded = re.sub(
        r"(?i)\b(token|secret|password|api[_-]?key|credential)"
        r"(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[REDACTED]",
        bounded,
    )
    return bounded[:limit]
