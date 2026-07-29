"""Public controlled managed-product execution façade."""

from __future__ import annotations

import shutil
from dataclasses import asdict, replace
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
    ChangePolicy,
    ExecutionDecision,
    ExecutionMode,
    ExecutionOperationPhase,
    ExecutionPlanStatus,
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
        decision = ExecutionDecision(
            f"{plan_id}-rejection-{len(plan.decisions)+1}", plan_id, plan.version,
            ReviewDecisionStatus.REJECTED, actor, datetime.now(timezone.utc), reason)
        updated = replace(plan, status=ExecutionPlanStatus.REJECTED,
                          decisions=plan.decisions + (decision,))
        self.store.save_plan(updated)
        return updated

    def create_runtime_work(self, project_id, plan_id):
        plan = self._approved(plan_id, project_id)
        existing = self.store.list_mappings(project_id)
        by_task = {mapping.project_task_id: mapping for mapping in existing}
        if all(task.project_task_id in by_task for task in plan.ordered_task_executions):
            return tuple(by_task[task.project_task_id]
                         for task in plan.ordered_task_executions)
        if any(task.project_task_id in by_task for task in plan.ordered_task_executions):
            self._reconciliation(plan, "Partial runtime task mapping exists")
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
            mapping = RuntimeTaskMapping(
                task.project_task_id, task.runtime_work_item_id,
                package.id, plan.execution_request_id, plan.execution_plan_id)
            self.store.save_mapping(project_id, mapping)
            mappings.append(mapping)
        self._phase(plan, ExecutionOperationPhase.RUNTIME_CREATED)
        return tuple(mappings)

    def prepare_workspace(self, project_id, plan_id, *, allow_product_write=False):
        plan = self._approved(plan_id, project_id)
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        if self.workspace_provider is None:
            raise ExecutionValidationError("Workspace provider is not configured")
        try:
            return self.store.load_workspace(project_id, plan.workspace_identity)
        except ExecutionNotFoundError:
            pass
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
        workspace = self.workspace_provider.create_workspace(plan.workspace_identity)
        repository = workspace.local_path / "repository"
        shutil.copytree(source, repository)
        record = WorkspaceRecord(
            workspace.workspace_id, project_id, str(repository),
            project.repository_url, plan.base_branch, WorkspaceLifecycle.READY,
            workspace.created_at, datetime.now(timezone.utc))
        self.store.save_workspace(record)
        self._phase(plan, ExecutionOperationPhase.WORKSPACE_READY)
        return record

    def create_feature_branch(self, project_id, plan_id, *, allow_product_write=False):
        plan = self._approved(plan_id, project_id)
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        record = self.store.load_workspace(project_id, plan.workspace_identity)
        git = self._git(plan.workspace_identity)
        status = git.status(record.local_path)
        if not status.clean or status.branch != plan.base_branch:
            raise ExecutionPolicyError("Workspace base branch is dirty or unexpected")
        validate_branch(plan.feature_branch)
        git.create_branch(record.local_path, plan.feature_branch)
        self._phase(plan, ExecutionOperationPhase.BRANCH_READY)
        return plan.feature_branch

    def build_coding_request(self, project_id, plan_id, project_task_id):
        plan = self._approved(plan_id, project_id)
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

    def process_coding_result(
        self, project_id, plan_id, coding_request, result, policy_id
    ):
        plan = self._approved(plan_id, project_id)
        policy = self._policy(policy_id)
        validated = validate_coding_result(coding_request, result, policy)
        operation = self._operation(plan)
        if validated.provider_task_id in operation.provider_operation_ids:
            return validated
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
        self.store.save_operation(replace(
            operation,
            provider_operation_ids=operation.provider_operation_ids
            + (validated.provider_task_id,),
            phase=ExecutionOperationPhase.CODING_COMPLETED,
            updated_at=datetime.now(timezone.utc),
        ))
        return validated

    def run_quality_gates(self, project_id, plan_id, profile_id):
        plan = self._approved(plan_id, project_id)
        profile = self._profile(profile_id, project_id)
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        if self.command_runner is None:
            raise ExecutionValidationError("Command runner is not configured")
        results = []
        for index, gate in enumerate(profile.ordered_gates, 1):
            started = datetime.now(timezone.utc)
            try:
                command = CommandRequest(
                    gate.command[0], gate.command[1:], Path(workspace.local_path),
                    timeout_seconds=gate.timeout_seconds)
                output = self.command_runner.execute(command)
                status = GateStatus.PASSED if output.exit_code in gate.expected_exit_codes \
                    else GateStatus.FAILED
                result = QualityGateResult(
                    f"{plan_id}-gate-{index}", gate.gate_id, status,
                    output.exit_code, output.stdout, output.stderr,
                    output.started_at, output.completed_at)
            except Exception as error:
                completed = datetime.now(timezone.utc)
                status = GateStatus.TIMED_OUT if "timeout" in type(error).__name__.lower() \
                    else GateStatus.ERROR
                result = QualityGateResult(
                    f"{plan_id}-gate-{index}", gate.gate_id, status,
                    None, "", str(error)[:2_000], started, completed)
            results.append(result)
            if gate.required and result.status != GateStatus.PASSED:
                break
        for gate in profile.ordered_gates[len(results):]:
            results.append(QualityGateResult(
                f"{plan_id}-gate-{len(results)+1}", gate.gate_id,
                GateStatus.NOT_RUN, None, "", "", datetime.now(timezone.utc),
                datetime.now(timezone.utc)))
        values = tuple(results)
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
        self, project_id, plan_id, coding_result, *, base_commit="uncommitted"
    ):
        plan = self._approved(plan_id, project_id)
        gates = self.store.load_gate_results(project_id, plan_id)
        if any(result.status != GateStatus.PASSED for result in gates):
            raise ExecutionPolicyError("Review evidence requires passing gates")
        payload = {
            "evidence_id": f"{plan_id}-evidence-1",
            "execution_plan_id": plan_id,
            "project_id": project_id,
            "task_ids": tuple(task.project_task_id for task in plan.ordered_task_executions),
            "workspace_id": plan.workspace_identity,
            "branch": plan.feature_branch,
            "base_commit": base_commit,
            "resulting_commit": None,
            "changed_files": coding_result.changed_files,
            "additions": coding_result.additions,
            "deletions": coding_result.deletions,
            "provider_result_reference": coding_result.provider_task_id,
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
        evidence = self.store.load_evidence(project_id, f"{plan_id}-evidence-1")
        decision = ExecutionDecision(
            f"{plan_id}-review-{len(plan.decisions)+1}", plan_id, plan.version,
            ReviewDecisionStatus.APPROVED, actor, datetime.now(timezone.utc), reason)
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
        plan = self._approved(plan_id, project_id)
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        operation = self._operation(plan)
        if operation.phase not in {
            ExecutionOperationPhase.REVIEW_APPROVED,
            ExecutionOperationPhase.COMMIT_CREATED,
        }:
            raise ExecutionApprovalError("Commit requires approved review evidence")
        if operation.commit_sha:
            return operation.commit_sha
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        evidence = self.store.load_evidence(project_id, f"{plan_id}-evidence-1")
        git = self._git(plan.workspace_identity)
        status = git.status(workspace.local_path)
        if set(status.changed_paths) != set(evidence.changed_files):
            raise ExecutionReconciliationError("Workspace changed after review")
        git.add(workspace.local_path, evidence.changed_files)
        commit = git.commit(
            workspace.local_path, f"ASCOS {plan.execution_plan_id}: approved changes")
        self.store.save_operation(replace(
            operation, commit_sha=commit.sha,
            phase=ExecutionOperationPhase.COMMIT_CREATED,
            updated_at=datetime.now(timezone.utc)))
        return commit.sha

    def push_branch(self, project_id, plan_id, *, allow_product_write=False):
        plan = self._approved(plan_id, project_id)
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        operation = self._operation(plan)
        if operation.push_state == "PUSHED":
            return "PUSHED"
        if not operation.commit_sha:
            raise ExecutionValidationError("Push requires a controlled commit")
        workspace = self.store.load_workspace(project_id, plan.workspace_identity)
        self._git(plan.workspace_identity).push(
            workspace.local_path, "origin", plan.feature_branch)
        self.store.save_operation(replace(
            operation, push_state="PUSHED",
            phase=ExecutionOperationPhase.PUSH_COMPLETED,
            updated_at=datetime.now(timezone.utc)))
        return "PUSHED"

    def create_draft_pull_request(
        self, project_id, plan_id, *, allow_product_write=False
    ):
        plan = self._approved(plan_id, project_id)
        request = self.store.load_request(project_id, plan.execution_request_id)
        self._write_allowed(request, allow_product_write)
        operation = self._operation(plan)
        if operation.pr_number is not None:
            return self.github_provider.get_pull_request(
                plan.repository_identity, operation.pr_number)
        if operation.push_state != "PUSHED":
            raise ExecutionValidationError("Draft PR requires completed push")
        evidence = self.store.load_evidence(project_id, f"{plan_id}-evidence-1")
        body = (
            f"ASCOS execution plan: {plan.execution_plan_id}\n\n"
            f"Project tasks: {', '.join(evidence.task_ids)}\n\n"
            f"Acceptance criteria: {evidence.acceptance_criteria_mapping}\n\n"
            f"Quality gates: {[(x.gate_id, x.status.value) for x in evidence.quality_gate_results]}\n\n"
            f"Review approvals: {operation.approval_ids}\n\n"
            "Known limitations: deterministic offline managed execution; no merge or deployment."
        )
        pr = self.github_provider.create_draft_pull_request(
            CreatePullRequestRequest(
                plan.repository_identity,
                f"ASCOS managed execution: {plan.execution_plan_id}",
                body, plan.base_branch, plan.feature_branch, draft=True))
        if not pr.draft:
            raise ExecutionReconciliationError("Provider did not create a draft PR")
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

    def reconcile_execution(self, project_id, plan_id):
        plan = self.get_execution_plan(project_id, plan_id)
        operation = self._operation(plan)
        mappings = self.store.list_mappings(project_id)
        expected = set(plan.expected_runtime_work_item_ids)
        actual = {
            mapping.runtime_work_item_id for mapping in mappings
            if mapping.runtime_work_package_id == plan.runtime_work_package_id}
        if actual and actual != expected:
            self._reconciliation(plan, "Runtime mappings diverge from execution plan")
        if operation.phase == ExecutionOperationPhase.RECONCILIATION_REQUIRED:
            raise ExecutionReconciliationError(
                operation.failure_details or "Operator reconciliation required")
        return operation

    def cancel_execution(self, project_id, plan_id, actor, reason):
        if not actor or not reason:
            raise ExecutionApprovalError("Cancellation requires actor and reason")
        plan = self.get_execution_plan(project_id, plan_id)
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

    def _approved(self, plan_id, project_id):
        plan = self.get_execution_plan(project_id, plan_id)
        if not any(decision.status == ReviewDecisionStatus.APPROVED
                   and decision.plan_version == plan.version
                   for decision in plan.decisions):
            raise ExecutionApprovalError("Exact execution plan is not approved")
        if plan.status in {
            ExecutionPlanStatus.REJECTED, ExecutionPlanStatus.SUPERSEDED,
            ExecutionPlanStatus.CANCELLED,
        }:
            raise ExecutionApprovalError("Execution plan cannot run")
        return plan

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
        decision = ExecutionDecision(
            f"{plan_id}-review-{len(plan.decisions)+1}", plan_id, plan.version,
            status, actor, datetime.now(timezone.utc), reason)
        self.store.save_plan(replace(
            plan, decisions=plan.decisions + (decision,),
            status=ExecutionPlanStatus.FAILED))
        return decision


def PurePathParent(value: str) -> str:
    normalized = safe_relative_path(value)
    parent = str(Path(normalized).parent).replace("\\", "/")
    return "" if parent == "." else f"{parent}/"
