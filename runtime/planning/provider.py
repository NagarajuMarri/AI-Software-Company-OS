"""Provider-neutral and deterministic offline planning providers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from runtime.planning.errors import PlanningProviderError
from runtime.planning.models import *


@runtime_checkable
class ManagedProductPlanningProvider(Protocol):
    def propose(self, request: ManagedProductChangeRequest,
                context: ManagedProductPlanningContext) -> ProposedProductMilestone: ...


class FutureLLMPlanningProvider(Protocol):
    """Boundary only: implementations must return reviewed structured output."""

    def propose(self, request: ManagedProductChangeRequest,
                context: ManagedProductPlanningContext) -> ProposedProductMilestone: ...


class DeterministicPlanningProvider:
    def __init__(self, *, provider_id="deterministic-planner", fail=False, malformed=False):
        self.provider_id, self.fail, self.malformed = provider_id, fail, malformed

    def propose(self, request, context):
        if self.fail:
            raise PlanningProviderError("Deterministic planning provider simulated failure")
        milestone_id = request.target_milestone_id or f"{request.request_id}-implementation"
        candidates = tuple(x.path for x in context.relevant_files[:5])
        criteria = request.acceptance_criteria
        tasks = (
            ProposedTask(f"{request.request_id}-design", "Define reviewed architecture",
                f"Define boundaries for {request.title}", (), ("software-architect",),
                ("architecture-design",), criteria, candidates, ("python -m pytest -q",),
                RiskLevel.MEDIUM, True),
            ProposedTask(f"{request.request_id}-implement", "Implement approved scope",
                request.objective, (f"{request.request_id}-design",), ("software-engineer",),
                request.requested_capabilities or ("implementation",), criteria, candidates,
                ("python -m pytest -q", "python -m compileall -q runtime tests examples"),
                RiskLevel.HIGH, True),
            ProposedTask(f"{request.request_id}-verify", "Verify acceptance criteria",
                "Validate the reviewed change without deployment",
                (f"{request.request_id}-implement",), ("quality-engineer",),
                ("test-engineering",), criteria, candidates,
                ("python -m pytest -q",), RiskLevel.MEDIUM, True),
        )
        if self.malformed:
            tasks = tasks + (tasks[0],)
        return ProposedProductMilestone(
            f"{request.request_id}-proposal-v1", 1, request.request_id,
            request.project_id, milestone_id, request.title, request.objective,
            request.requested_capabilities, request.out_of_scope,
            ("Preserve provider-neutral boundaries", "Require explicit approval"),
            tasks, criteria, candidates,
            ("python -m pytest -q",), ("Implementation uncertainty",),
            ("Knowledge snapshot is reviewed and current",),
            ("product-owner", "engineering-reviewer"),
            (("provider_id", self.provider_id), ("mode", "offline-deterministic")),
            request.created_at, ProposalStatus.PROPOSED)
