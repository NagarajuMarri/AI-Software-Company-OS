"""Read-only eligibility evaluation for materialised planning tasks."""

from __future__ import annotations

from runtime.managed_execution.models import EligibilityReason, TaskEligibility
from runtime.managed_execution.policy import IDENTIFIER, safe_relative_path
from runtime.planning.models import MaterialisationState, ProposalStatus
from runtime.project_manager.models import MilestoneStatus, TaskStatus
from runtime.projects.models import ProjectLifecycle


class ManagedProductExecutionEligibilityService:
    def __init__(self, registry, planning_store, manager_loader, execution_store):
        self.registry = registry
        self.planning_store = planning_store
        self.manager_loader = manager_loader
        self.execution_store = execution_store

    def evaluate(self, request, *, require_execution_approval=False):
        reasons_by_task = {task_id: [] for task_id in request.selected_task_ids}
        project = self.registry.get(request.project_id)
        proposal = self.planning_store.load_proposal(
            request.project_id, request.proposal_id)
        operation = self.planning_store.load_materialisation(
            request.project_id, f"{request.proposal_id}-materialisation")
        state = self.manager_loader(request.project_id).current_state()
        selected = set(request.selected_task_ids)
        proposal_tasks = {task.task_id: task for task in proposal.tasks}
        manager_tasks = {task.task_id: task for task in state.tasks}

        common = []
        if proposal.status != ProposalStatus.APPROVED or not proposal.decisions:
            common.append(EligibilityReason("PROPOSAL_NOT_APPROVED",
                                            "Proposal lacks human approval evidence"))
        if operation.state != MaterialisationState.COMPLETED:
            common.append(EligibilityReason("MATERIALISATION_INCOMPLETE",
                                            "Materialisation operation is not completed"))
        if proposal.project_id != request.project_id or state.project_id != request.project_id:
            common.append(EligibilityReason("PROJECT_MISMATCH", "Project identity differs"))
        if proposal.milestone_id != request.milestone_id:
            common.append(EligibilityReason("MILESTONE_MISMATCH", "Milestone differs"))
        if project.lifecycle not in {ProjectLifecycle.REGISTERED, ProjectLifecycle.ACTIVE}:
            common.append(EligibilityReason("PROJECT_INACTIVE",
                                            "Repository lifecycle forbids execution"))
        try:
            milestone = state.milestone(request.milestone_id)
            if milestone.status == MilestoneStatus.COMPLETED:
                common.append(EligibilityReason("MILESTONE_COMPLETED",
                                                "Milestone is already completed"))
            if milestone.task_ids != tuple(task.task_id for task in proposal.tasks):
                common.append(EligibilityReason("MILESTONE_DIVERGED",
                                                "Manager milestone differs from proposal"))
            if (
                milestone.title != proposal.title
                or milestone.goal != proposal.objective
                or milestone.metadata != {
                    "proposal_id": proposal.proposal_id,
                    "acceptance_criteria": list(proposal.acceptance_criteria),
                }
            ):
                common.append(EligibilityReason(
                    "MILESTONE_METADATA_DIVERGED",
                    "Manager milestone metadata differs from proposal"))
        except Exception:
            common.append(EligibilityReason("MILESTONE_MISSING", "Milestone is missing"))

        active_mappings = {
            mapping.project_task_id for mapping in
            self.execution_store.list_mappings(request.project_id)
        }
        for task_id in request.selected_task_ids:
            reasons = reasons_by_task[task_id]
            reasons.extend(common)
            proposed = proposal_tasks.get(task_id)
            managed = manager_tasks.get(task_id)
            if proposed is None or managed is None:
                reasons.append(EligibilityReason("TASK_UNRELATED",
                                                 "Task is not part of the milestone"))
                continue
            if managed.status != TaskStatus.TODO:
                reasons.append(EligibilityReason("TASK_NOT_TODO",
                                                 "Task is not executable from its state"))
            if task_id in active_mappings:
                reasons.append(EligibilityReason("TASK_ALREADY_BOUND",
                                                 "Task already has runtime mapping"))
            missing = [
                dependency for dependency in proposed.dependencies
                if dependency not in selected
                and manager_tasks[dependency].status not in
                {TaskStatus.DONE, TaskStatus.SKIPPED}
            ]
            if missing:
                reasons.append(EligibilityReason(
                    "DEPENDENCY_UNSATISFIED", f"Unsatisfied dependencies: {missing}"))
            if any(not IDENTIFIER.fullmatch(value) for value in
                   proposed.role_requirements + proposed.capability_requirements):
                reasons.append(EligibilityReason("INVALID_REQUIREMENT",
                                                 "Role or capability is invalid"))
            try:
                for path in proposed.candidate_files:
                    safe_relative_path(path)
            except Exception:
                reasons.append(EligibilityReason("UNSAFE_CANDIDATE_PATH",
                                                 "Candidate path is unsafe"))
            if managed.metadata.get("quality_gates") != list(proposed.quality_gates):
                reasons.append(EligibilityReason("TASK_METADATA_DIVERGED",
                                                 "Task quality gates differ"))
            if (
                managed.title != proposed.title
                or managed.description != proposed.description
                or managed.dependencies != proposed.dependencies
                or managed.metadata != {
                    "acceptance_criteria": list(proposed.acceptance_criteria),
                    "candidate_files": list(proposed.candidate_files),
                    "quality_gates": list(proposed.quality_gates),
                    "requires_human_review": proposed.requires_human_review,
                }
            ):
                reasons.append(EligibilityReason(
                    "TASK_METADATA_DIVERGED",
                    "Manager task metadata differs from proposal"))
            if require_execution_approval:
                reasons.append(EligibilityReason("EXECUTION_APPROVAL_REQUIRED",
                                                 "Exact plan approval is required"))
        return tuple(TaskEligibility(
            task_id, not reasons, tuple(reasons)
        ) for task_id, reasons in reasons_by_task.items())
