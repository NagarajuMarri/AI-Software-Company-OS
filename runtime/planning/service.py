"""Managed product planning service and approval/materialisation boundary."""

from dataclasses import replace
from datetime import datetime, timezone

from runtime.planning.context import PlanningContextBuilder
from runtime.planning.errors import (
    MaterialisationReconciliationError,
    PlanningConflictError,
    PlanningNotFoundError,
    PlanningValidationError,
    ProposalLifecycleError,
)
from runtime.planning.models import (
    MaterialisationOperation,
    MaterialisationState,
    ProposalDecision,
    ProposalStatus,
)
from runtime.planning.validation import validate_proposal
from runtime.project_manager.models import (
    MilestoneStatus,
    RiskSeverity,
    RiskStatus,
    TaskStatus,
)


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
        operation_id = f"{proposal.proposal_id}-materialisation"
        operation = self._load_or_prepare_materialisation(proposal, operation_id)
        manager = self.manager_loader(project_id)
        state = manager.current_state()
        if state.project_id != project_id:
            raise PlanningValidationError("Materialisation project identity mismatch")
        presence = self._materialisation_presence(state, operation)
        if presence == "none":
            if operation.state in {
                MaterialisationState.MANAGER_COMMITTED,
                MaterialisationState.COMPLETED,
            }:
                raise self._reconciliation_required(
                    operation, "operation records a manager commit but expected state is absent"
                )
            self._apply_to_manager(manager, proposal)
            try:
                manager.save()
            except Exception as error:
                self._record_materialisation_failure(operation, error)
                raise
            state = self.manager_loader(project_id).current_state()
        elif presence == "partial":
            raise self._reconciliation_required(
                operation, "only part of the expected manager state exists"
            )
        self._verify_materialised_state(state, proposal, operation)
        operation = self._advance_materialisation(
            operation, MaterialisationState.MANAGER_COMMITTED
        )
        if proposal.materialised_at is None:
            proposal = replace(proposal, materialised_at=datetime.now(timezone.utc))
            self.store.save_proposal(proposal)
        self._advance_materialisation(operation, MaterialisationState.COMPLETED)
        return proposal

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

    def _load_or_prepare_materialisation(self, proposal, operation_id):
        try:
            operation = self.store.load_materialisation(
                proposal.project_id, operation_id
            )
        except PlanningNotFoundError:
            now = datetime.now(timezone.utc)
            operation = MaterialisationOperation(
                operation_id=operation_id,
                project_id=proposal.project_id,
                proposal_id=proposal.proposal_id,
                milestone_id=proposal.milestone_id,
                expected_task_ids=tuple(task.task_id for task in proposal.tasks),
                expected_risk_ids=tuple(
                    f"{proposal.proposal_id}-risk-{index}"
                    for index in range(1, len(proposal.risks) + 1)
                ),
                expected_decision_id=f"{proposal.proposal_id}-approval",
                state=MaterialisationState.PREPARED,
                created_at=now,
                updated_at=now,
            )
            self.store.save_materialisation(operation)
        expected = (
            proposal.project_id,
            proposal.proposal_id,
            proposal.milestone_id,
            tuple(task.task_id for task in proposal.tasks),
            tuple(
                f"{proposal.proposal_id}-risk-{index}"
                for index in range(1, len(proposal.risks) + 1)
            ),
            f"{proposal.proposal_id}-approval",
            1,
        )
        actual = (
            operation.project_id,
            operation.proposal_id,
            operation.milestone_id,
            operation.expected_task_ids,
            operation.expected_risk_ids,
            operation.expected_decision_id,
            operation.schema_version,
        )
        if actual != expected:
            raise self._reconciliation_required(
                operation, "operation expectations do not match the approved proposal"
            )
        return operation

    def _apply_to_manager(self, manager, proposal):
        manager.create_milestone(
            proposal.milestone_id,
            proposal.title,
            goal=proposal.objective,
            metadata=self._expected_milestone_metadata(proposal),
        )
        for task in proposal.tasks:
            manager.create_task(
                proposal.milestone_id,
                task.task_id,
                task.title,
                description=task.description,
                dependencies=task.dependencies,
                metadata=self._expected_task_metadata(task),
            )
        for index, risk in enumerate(proposal.risks, 1):
            manager.add_risk(
                f"{proposal.proposal_id}-risk-{index}",
                risk,
                risk,
                RiskSeverity.MEDIUM,
                timestamp=proposal.generated_at,
                metadata={"proposal_id": proposal.proposal_id},
            )
        approval = proposal.decisions[-1]
        manager.add_decision(
            f"{proposal.proposal_id}-approval",
            "Planning proposal explicitly approved",
            approval.reason or "Approved without additional reason",
            author=approval.actor,
            timestamp=approval.timestamp,
            metadata={"proposal_id": proposal.proposal_id},
        )

    def _materialisation_presence(self, state, operation):
        checks = [
            any(item.milestone_id == operation.milestone_id for item in state.milestones),
            *[
                any(item.task_id == task_id for item in state.tasks)
                for task_id in operation.expected_task_ids
            ],
            *[
                any(item.risk_id == risk_id for item in state.risks)
                for risk_id in operation.expected_risk_ids
            ],
            any(
                item.decision_id == operation.expected_decision_id
                for item in state.decisions
            ),
        ]
        if not any(checks):
            return "none"
        return "all" if all(checks) else "partial"

    def _verify_materialised_state(self, state, proposal, operation):
        try:
            milestone = state.milestone(proposal.milestone_id)
        except Exception as error:
            raise self._reconciliation_required(
                operation, "expected milestone is missing"
            ) from error
        expected_milestone = (
            proposal.title,
            proposal.objective,
            MilestoneStatus.NOT_STARTED,
            tuple(task.task_id for task in proposal.tasks),
            (),
            None,
            None,
            self._expected_milestone_metadata(proposal),
        )
        actual_milestone = (
            milestone.title,
            milestone.goal,
            milestone.status,
            milestone.task_ids,
            milestone.dependencies,
            milestone.started_at,
            milestone.completed_at,
            milestone.metadata,
        )
        if actual_milestone != expected_milestone:
            raise self._reconciliation_required(
                operation, "existing milestone does not match the approved proposal"
            )
        if state.active_milestone_id == proposal.milestone_id:
            raise self._reconciliation_required(
                operation, "materialised milestone is unexpectedly active"
            )
        for proposed in proposal.tasks:
            try:
                task = state.task(proposed.task_id)
            except Exception as error:
                raise self._reconciliation_required(
                    operation, f"expected task {proposed.task_id!r} is missing"
                ) from error
            expected_task = (
                proposed.title,
                proposed.description,
                TaskStatus.TODO,
                proposed.dependencies,
                None,
                None,
                None,
                None,
                None,
                None,
                self._expected_task_metadata(proposed),
            )
            actual_task = (
                task.title,
                task.description,
                task.status,
                task.dependencies,
                task.owner,
                task.estimated_effort,
                task.actual_effort,
                task.blocker_reason,
                task.started_at,
                task.completed_at,
                task.metadata,
            )
            if actual_task != expected_task:
                raise self._reconciliation_required(
                    operation,
                    f"existing task {proposed.task_id!r} does not match the approved proposal",
                )
        for index, risk_text in enumerate(proposal.risks, 1):
            risk_id = f"{proposal.proposal_id}-risk-{index}"
            risks = [item for item in state.risks if item.risk_id == risk_id]
            if len(risks) != 1:
                raise self._reconciliation_required(
                    operation, f"expected risk {risk_id!r} is missing or duplicated"
                )
            risk = risks[0]
            if (
                risk.title,
                risk.description,
                risk.severity,
                risk.status,
                risk.mitigation,
                risk.timestamp,
                risk.metadata,
            ) != (
                risk_text,
                risk_text,
                RiskSeverity.MEDIUM,
                RiskStatus.OPEN,
                None,
                proposal.generated_at,
                {"proposal_id": proposal.proposal_id},
            ):
                raise self._reconciliation_required(
                    operation, f"existing risk {risk_id!r} does not match"
                )
        decisions = [
            item
            for item in state.decisions
            if item.decision_id == operation.expected_decision_id
        ]
        expected_reason = (
            proposal.decisions[-1].reason or "Approved without additional reason"
        )
        if len(decisions) != 1 or (
            decisions[0].title,
            decisions[0].rationale,
            decisions[0].author,
            decisions[0].timestamp,
            decisions[0].metadata,
        ) != (
            "Planning proposal explicitly approved",
            expected_reason,
            proposal.decisions[-1].actor,
            proposal.decisions[-1].timestamp,
            {"proposal_id": proposal.proposal_id},
        ):
            raise self._reconciliation_required(
                operation, "existing approval decision does not match"
            )

    def _advance_materialisation(self, operation, target):
        order = {
            MaterialisationState.NOT_STARTED: 0,
            MaterialisationState.PREPARED: 1,
            MaterialisationState.FAILED: 1,
            MaterialisationState.MANAGER_COMMITTED: 2,
            MaterialisationState.COMPLETED: 3,
        }
        if operation.state == MaterialisationState.RECONCILIATION_REQUIRED:
            raise MaterialisationReconciliationError(
                operation.failure_details or "Materialisation requires reconciliation"
            )
        if order[operation.state] >= order[target]:
            return operation
        updated = replace(
            operation,
            state=target,
            updated_at=datetime.now(timezone.utc),
            failure_details=None,
        )
        self.store.save_materialisation(updated)
        return updated

    def _record_materialisation_failure(self, operation, error):
        failed = replace(
            operation,
            state=MaterialisationState.FAILED,
            updated_at=datetime.now(timezone.utc),
            failure_details=f"{type(error).__name__}: {error}",
        )
        try:
            self.store.save_materialisation(failed)
        except Exception:
            pass

    def _reconciliation_required(self, operation, details):
        updated = replace(
            operation,
            state=MaterialisationState.RECONCILIATION_REQUIRED,
            updated_at=datetime.now(timezone.utc),
            failure_details=details,
        )
        try:
            self.store.save_materialisation(updated)
        except Exception:
            pass
        return MaterialisationReconciliationError(details)

    @staticmethod
    def _expected_milestone_metadata(proposal):
        return {
            "proposal_id": proposal.proposal_id,
            "acceptance_criteria": list(proposal.acceptance_criteria),
        }

    @staticmethod
    def _expected_task_metadata(task):
        return {
            "acceptance_criteria": list(task.acceptance_criteria),
            "candidate_files": list(task.candidate_files),
            "quality_gates": list(task.quality_gates),
            "requires_human_review": task.requires_human_review,
        }
