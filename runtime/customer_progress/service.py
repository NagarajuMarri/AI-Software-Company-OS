"""Build the read-only Day 20 dashboard from exact governed customer authority."""

from __future__ import annotations

from runtime.customer_estimate import CustomerDeliveryEstimateService
from runtime.customer_progress.errors import (
    CustomerProjectProgressConflict,
    CustomerProjectProgressCorrupt,
)
from runtime.customer_progress.models import (
    GENERATION_PROFILE,
    CustomerProgressBlocker,
    CustomerProgressDecision,
    CustomerProgressMilestone,
    CustomerProgressTask,
    CustomerProjectProgressSnapshot,
    progress_id_for,
    task_id_for,
)
from runtime.project_manager import (
    Decision,
    Milestone,
    ProjectManagerState,
    Risk,
    RiskSeverity,
    Task,
)
from runtime.project_manager.progress import project_progress


class CustomerProjectProgressService:
    """Project approved scope into a customer-visible, non-executable dashboard."""

    def __init__(self, estimates: CustomerDeliveryEstimateService) -> None:
        self._estimates = estimates

    def view(self, customer_id: str, request_id: str) -> CustomerProjectProgressSnapshot:
        request, prd, roadmap, approval, estimate = self._estimates.context(
            customer_id,
            request_id,
        )
        if prd is None or roadmap is None or approval is None or estimate is None:
            raise CustomerProjectProgressConflict(
                "An exact locked roadmap and delivery-estimate draft are required"
            )
        requirements = {value.requirement_id: value for value in prd.requirements}
        if (
            estimate.customer_id != customer_id
            or estimate.request_id != request_id
            or estimate.roadmap_digest != roadmap.digest
            or estimate.roadmap_approval_digest != approval.digest
            or estimate.requirement_ids != roadmap.requirement_ids
            or set(requirements) != set(estimate.requirement_ids)
        ):
            raise CustomerProjectProgressCorrupt(
                "Project progress cannot bind the current customer authority"
            )

        tasks: list[CustomerProgressTask] = []
        milestones: list[CustomerProgressMilestone] = []
        manager_tasks: list[Task] = []
        manager_milestones: list[Milestone] = []
        for value in estimate.milestones:
            task_ids: list[str] = []
            for requirement_id in value.requirement_ids:
                requirement = requirements[requirement_id]
                task_id = task_id_for(request_id, requirement_id)
                task_ids.append(task_id)
                tasks.append(
                    CustomerProgressTask(
                        task_id,
                        requirement_id,
                        value.roadmap_item_id,
                        requirement.title,
                        requirement.priority.value,
                    )
                )
                manager_tasks.append(
                    Task(
                        task_id,
                        requirement.title,
                        description=(
                            "Read-only planned task projected from locked requirement "
                            f"{requirement_id}; no execution authority"
                        ),
                        created_at=estimate.generated_at,
                        updated_at=estimate.generated_at,
                        metadata={"requirement_id": requirement_id, "authority": "READ_ONLY"},
                    )
                )
            milestones.append(
                CustomerProgressMilestone(
                    value.roadmap_item_id,
                    value.milestone,
                    value.sequence,
                    value.requirement_ids,
                    tuple(task_ids),
                    value.minimum_effort_days,
                    value.maximum_effort_days,
                )
            )
            manager_milestones.append(
                Milestone(
                    value.roadmap_item_id,
                    value.milestone,
                    goal="Deliver only the exact locked requirement mapping",
                    task_ids=tuple(task_ids),
                    created_at=estimate.generated_at,
                    updated_at=estimate.generated_at,
                    metadata={"roadmap_digest": roadmap.digest, "authority": "READ_ONLY"},
                )
            )

        decisions = (
            Decision(
                "roadmap-scope-approved",
                "Roadmap scope approved and locked",
                "The customer approved this exact roadmap as immutable planning scope.",
                approval.approved_at,
                approval.customer_id,
                {"authority_digest": approval.digest},
            ),
            Decision(
                "delivery-estimate-drafted",
                "Delivery estimate recorded as a draft",
                "The deterministic estimate is visible but grants no execution authority.",
                estimate.generated_at,
                "ascos-estimation-policy",
                {"authority_digest": estimate.digest},
            ),
        )
        risks = (
            Risk(
                "execution-authority-required",
                "Execution authority required",
                "No implementation work may begin until a later explicit customer and founder gate.",
                RiskSeverity.CRITICAL,
                timestamp=estimate.generated_at,
            ),
            Risk(
                "workforce-not-activated",
                "Operational workforce not activated",
                "Day 20 displays assignment state; operational agents remain a later module.",
                RiskSeverity.HIGH,
                timestamp=estimate.generated_at,
            ),
            Risk(
                "product-workspace-unavailable",
                "Product workspace not created",
                "No product repository, branch, worktree, or executable task exists.",
                RiskSeverity.HIGH,
                timestamp=estimate.generated_at,
            ),
        )
        state = ProjectManagerState(
            estimate.product_id,
            milestones=tuple(manager_milestones),
            tasks=tuple(manager_tasks),
            decisions=decisions,
            risks=risks,
            created_at=approval.approved_at,
            updated_at=estimate.generated_at,
            metadata={
                "customer_id": customer_id,
                "request_id": request_id,
                "authority": "READ_ONLY_CUSTOMER_PROGRESS",
            },
        )
        progress = project_progress(state)
        if (
            progress.total != len(tasks)
            or progress.completed != 0
            or progress.blocked != 0
            or progress.in_progress != 0
            or progress.percentage != 0
        ):
            raise CustomerProjectProgressCorrupt("Project progress calculation is invalid")

        return CustomerProjectProgressSnapshot(
            progress_id_for(request_id),
            customer_id,
            request_id,
            estimate.product_id,
            estimate.prd_id,
            estimate.roadmap_id,
            estimate.roadmap_approval_id,
            estimate.estimate_id,
            estimate.source_request_digest,
            estimate.requirements_digest,
            estimate.requirements_approval_digest,
            estimate.prd_digest,
            estimate.prd_approval_digest,
            estimate.roadmap_digest,
            estimate.roadmap_approval_digest,
            estimate.digest,
            GENERATION_PROFILE,
            f"{request.product_name} — Project Progress",
            tuple(milestones),
            tuple(tasks),
            (),
            tuple(
                CustomerProgressBlocker(value.risk_id, value.title, value.description)
                for value in state.risks
            ),
            tuple(
                CustomerProgressDecision(
                    value.decision_id,
                    value.title,
                    "APPROVED_AND_LOCKED"
                    if value.decision_id == "roadmap-scope-approved"
                    else "DRAFT_RECORDED",
                    value.rationale,
                    str(value.metadata["authority_digest"]),
                    value.timestamp,
                )
                for value in state.decisions
            ),
            progress.total,
            progress.completed,
            progress.blocked,
            progress.in_progress,
            progress.percentage,
            estimate.generated_at,
        )
