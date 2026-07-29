"""Managed product planning service and approval/materialisation boundary."""

from dataclasses import replace
from datetime import datetime, timezone

from runtime.planning.context import PlanningContextBuilder
from runtime.planning.errors import *
from runtime.planning.models import *
from runtime.planning.validation import validate_proposal


class ManagedProductPlanningService:
    def __init__(self, registry, store, knowledge_loader, manager_loader,
                 provider, context_builder=None):
        self.registry, self.store = registry, store
        self.knowledge_loader, self.manager_loader = knowledge_loader, manager_loader
        self.provider = provider
        self.context_builder = context_builder or PlanningContextBuilder()

    def create_request(self, request):
        self.registry.get(request.project_id)
        try:
            self.store.load_request(request.project_id, request.request_id)
        except PlanningNotFoundError:
            self.store.save_request(request)
            return request
        raise PlanningConflictError(f"Request {request.request_id!r} already exists")

    def get_request(self, project_id, request_id):
        self.registry.get(project_id)
        return self.store.load_request(project_id, request_id)

    def list_requests(self, project_id):
        self.registry.get(project_id)
        return self.store.list_requests(project_id)

    def build_context(self, project_id, request_id, *, now=None):
        project = self.registry.get(project_id)
        request = self.get_request(project_id, request_id)
        context = self.context_builder.build(project, request,
            self.knowledge_loader(project_id), self.manager_loader(project_id), now=now)
        self.store.save_context_reference(context)
        return context

    def generate_proposal(self, project_id, request_id, *, now=None):
        context = self.build_context(project_id, request_id, now=now)
        proposal = validate_proposal(self.provider.propose(context.request, context), context)
        try:
            self.store.load_proposal(project_id, proposal.proposal_id)
        except PlanningNotFoundError:
            self.store.save_proposal(proposal)
            return proposal
        raise PlanningConflictError(f"Proposal {proposal.proposal_id!r} already exists")

    def get_proposal(self, project_id, proposal_id):
        self.registry.get(project_id)
        return self.store.load_proposal(project_id, proposal_id)

    def list_proposals(self, project_id):
        self.registry.get(project_id)
        return self.store.list_proposals(project_id)

    def approve_proposal(self, project_id, proposal_id, actor, reason=None):
        return self._decide(project_id, proposal_id, ProposalStatus.APPROVED, actor, reason)

    def reject_proposal(self, project_id, proposal_id, actor, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ProposalLifecycleError("Rejection requires a reason")
        return self._decide(project_id, proposal_id, ProposalStatus.REJECTED, actor, reason)

    def supersede_proposal(self, project_id, proposal_id, actor, reason):
        if not reason.strip():
            raise ProposalLifecycleError("Supersession requires a reason")
        return self._decide(project_id, proposal_id, ProposalStatus.SUPERSEDED, actor, reason)

    def materialise_approved_proposal(self, project_id, proposal_id):
        proposal = self.get_proposal(project_id, proposal_id)
        if proposal.status != ProposalStatus.APPROVED:
            raise ProposalLifecycleError("Only an approved proposal can be materialised")
        if proposal.materialised_at is not None:
            return proposal
        manager = self.manager_loader(project_id)
        state = manager.current_state()
        if state.project_id != project_id:
            raise PlanningValidationError("Materialisation project identity mismatch")
        if any(x.milestone_id == proposal.milestone_id for x in state.milestones) or \
                any(task.task_id in {x.task_id for x in state.tasks} for task in proposal.tasks):
            raise PlanningConflictError("Materialisation conflicts with existing milestone or task IDs")
        future_record_ids = {f"{proposal.proposal_id}-risk-{index}"
                             for index in range(1, len(proposal.risks) + 1)}
        if future_record_ids & {x.risk_id for x in state.risks} or \
                f"{proposal.proposal_id}-approval" in {x.decision_id for x in state.decisions}:
            raise PlanningConflictError("Materialisation conflicts with existing risk or decision IDs")
        manager.create_milestone(proposal.milestone_id, proposal.title, goal=proposal.objective,
            metadata={"proposal_id": proposal.proposal_id,
                      "acceptance_criteria": list(proposal.acceptance_criteria)})
        for task in proposal.tasks:
            manager.create_task(proposal.milestone_id, task.task_id, task.title,
                description=task.description, dependencies=task.dependencies,
                metadata={"acceptance_criteria": list(task.acceptance_criteria),
                          "candidate_files": list(task.candidate_files),
                          "quality_gates": list(task.quality_gates),
                          "requires_human_review": task.requires_human_review})
        for index, risk in enumerate(proposal.risks, 1):
            from runtime.project_manager.models import RiskSeverity
            manager.add_risk(f"{proposal.proposal_id}-risk-{index}", risk, risk,
                             RiskSeverity.MEDIUM)
        manager.add_decision(f"{proposal.proposal_id}-approval",
            "Planning proposal explicitly approved",
            proposal.decisions[-1].reason or "Approved without additional reason",
            author=proposal.decisions[-1].actor)
        manager.save()
        updated = replace(proposal, materialised_at=datetime.now(timezone.utc))
        self.store.save_proposal(updated)
        return updated

    def get_planning_status(self, project_id):
        proposals = self.list_proposals(project_id)
        return {"project_id": project_id, "requests": len(self.list_requests(project_id)),
                "proposals": len(proposals),
                "approved": sum(x.status == ProposalStatus.APPROVED for x in proposals),
                "materialised": sum(x.materialised_at is not None for x in proposals)}

    def _decide(self, project_id, proposal_id, status, actor, reason):
        if not isinstance(actor, str) or not actor.strip():
            raise ProposalLifecycleError("Decision actor is required")
        proposal = self.get_proposal(project_id, proposal_id)
        if proposal.status not in {ProposalStatus.DRAFT, ProposalStatus.PROPOSED}:
            raise ProposalLifecycleError(f"Proposal cannot transition from {proposal.status.value}")
        provider_ids = {value for key, value in proposal.provider_metadata if key == "provider_id"}
        if actor in provider_ids:
            raise ProposalLifecycleError("A planning provider cannot approve its own proposal")
        decision = ProposalDecision(status, actor, datetime.now(timezone.utc), reason)
        updated = replace(proposal, status=status,
                          decisions=proposal.decisions + (decision,))
        self.store.save_proposal(updated)
        return updated
