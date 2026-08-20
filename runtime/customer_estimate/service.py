"""Generate a deterministic effort estimate from one exact locked roadmap."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac
import math

from runtime.customer_application import CustomerProductRequest
from runtime.customer_estimate.errors import (
    CustomerDeliveryEstimateConflict,
    CustomerDeliveryEstimateCorrupt,
)
from runtime.customer_estimate.models import (
    EFFORT_UNIT,
    GENERATION_PROFILE,
    CustomerDeliveryEstimateDraft,
    CustomerMilestoneEstimate,
    EffortBand,
    EstimateConfidence,
    estimate_id_for,
)
from runtime.customer_estimate.persistence import FileCustomerDeliveryEstimateStore
from runtime.customer_prd import CustomerPrdDraft
from runtime.customer_requirements import DataSensitivity
from runtime.customer_roadmap import (
    CustomerRoadmapApproval,
    CustomerRoadmapApprovalService,
    CustomerRoadmapDraft,
    LockedCustomerRoadmap,
)
from runtime.product_requirements import RequirementCategory, RequirementPriority


_PRIORITY_POINTS = {
    RequirementPriority.CRITICAL: 5,
    RequirementPriority.HIGH: 4,
    RequirementPriority.MEDIUM: 3,
    RequirementPriority.LOW: 2,
}
_CATEGORY_POINTS = {
    RequirementCategory.FUNCTIONAL: 0,
    RequirementCategory.NON_FUNCTIONAL: 1,
    RequirementCategory.SECURITY: 2,
    RequirementCategory.PRIVACY: 2,
    RequirementCategory.ACCESSIBILITY: 1,
    RequirementCategory.PERFORMANCE: 2,
    RequirementCategory.ARCHITECTURE: 2,
    RequirementCategory.COMMERCIAL: 1,
    RequirementCategory.DEPLOYMENT: 2,
    RequirementCategory.FUTURE_ROADMAP: 0,
}


class CustomerDeliveryEstimateService:
    """Create and reopen one customer-owned estimate draft."""

    def __init__(
        self,
        store: FileCustomerDeliveryEstimateStore,
        roadmap_approvals: CustomerRoadmapApprovalService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._roadmap_approvals = roadmap_approvals
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[
        CustomerProductRequest,
        CustomerPrdDraft | None,
        CustomerRoadmapDraft | None,
        CustomerRoadmapApproval | None,
        CustomerDeliveryEstimateDraft | None,
    ]:
        request, prd, _, roadmap, approval = self._roadmap_approvals.context(
            customer_id,
            request_id,
        )
        estimate = self._store.find(customer_id, request_id)
        if estimate is not None:
            if prd is None or roadmap is None or approval is None:
                raise CustomerDeliveryEstimateCorrupt(
                    "Customer estimate does not have locked-roadmap authority"
                )
            locked = self._roadmap_approvals.governed_roadmap(customer_id, request_id)
            expected = _build(prd, roadmap, approval, locked, estimate.generated_at)
            if estimate != expected:
                raise CustomerDeliveryEstimateCorrupt(
                    "Customer estimate does not bind the current locked roadmap"
                )
        return request, prd, roadmap, approval, estimate

    def generate(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_roadmap_approval_digest: str,
    ) -> CustomerDeliveryEstimateDraft:
        _, prd, roadmap, approval, existing = self.context(customer_id, request_id)
        if prd is None or roadmap is None or approval is None:
            raise CustomerDeliveryEstimateConflict("A locked customer roadmap is required")
        if (
            not isinstance(expected_roadmap_approval_digest, str)
            or not hmac.compare_digest(expected_roadmap_approval_digest, approval.digest)
        ):
            raise CustomerDeliveryEstimateConflict("Customer estimate form is stale")
        if existing is not None:
            return existing
        locked = self._roadmap_approvals.governed_roadmap(customer_id, request_id)
        return self._store.save(_build(prd, roadmap, approval, locked, self._clock()))


def _build(
    prd: CustomerPrdDraft,
    roadmap: CustomerRoadmapDraft,
    approval: CustomerRoadmapApproval,
    locked: LockedCustomerRoadmap,
    generated_at: datetime,
) -> CustomerDeliveryEstimateDraft:
    if (
        locked.status != "LOCKED"
        or locked.source_roadmap_digest != roadmap.digest
        or locked.approval_digest != approval.digest
        or locked.requirement_ids != roadmap.requirement_ids
        or any(item.status != "LOCKED" for item in locked.milestones)
    ):
        raise CustomerDeliveryEstimateConflict("A valid locked governed roadmap is required")
    requirements = {item.requirement_id: item for item in prd.requirements}
    if set(requirements) != set(locked.requirement_ids):
        raise CustomerDeliveryEstimateConflict("Locked estimate scope is incomplete")
    confidence = _confidence(prd)
    factor = {
        DataSensitivity.NO_PERSONAL_DATA: 1.20,
        DataSensitivity.PERSONAL_DATA: 1.35,
        DataSensitivity.SENSITIVE_DATA: 1.60,
    }[prd.data_sensitivity]
    milestones: list[CustomerMilestoneEstimate] = []
    for item in locked.milestones:
        scoped = tuple(requirements[requirement_id] for requirement_id in item.requirement_ids)
        points = sum(
            _PRIORITY_POINTS[value.priority] + _CATEGORY_POINTS[value.category]
            for value in scoped
        )
        minimum = max(1, points)
        maximum = max(minimum, math.ceil(points * factor))
        priorities = sorted({value.priority.value.title() for value in scoped})
        categories = sorted({value.category.value.replace("_", " ").title() for value in scoped})
        drivers = (
            f"{len(scoped)} locked requirements",
            f"Priorities: {', '.join(priorities)}",
            f"Scope types: {', '.join(categories)}",
            f"Declared data class: {prd.data_sensitivity.value.replace('_', ' ').title()}",
            f"Approved platforms: {', '.join(value.title() for value in prd.platforms)}",
        )
        milestones.append(
            CustomerMilestoneEstimate(
                item.roadmap_item_id,
                item.milestone,
                item.sequence,
                item.requirement_ids,
                points,
                minimum,
                maximum,
                _band(maximum),
                confidence,
                drivers,
            )
        )
    assumptions = (
        "The estimate covers only the exact locked roadmap and explicit PRD exclusions remain excluded.",
        "One engineering day is a relative effort unit, not a calendar date or delivery commitment.",
        "Team composition, agent assignment, repository condition, external integrations, and production environment are not yet known.",
        "Pricing, billing, taxes, third-party usage charges, contingency reserves, and support operations are not included.",
        "A later approved planning module must review capacity and dependencies before any schedule is proposed.",
    )
    values = tuple(milestones)
    return CustomerDeliveryEstimateDraft(
        estimate_id_for(roadmap.request_id),
        roadmap.customer_id,
        roadmap.request_id,
        roadmap.roadmap_id,
        approval.approval_id,
        roadmap.product_id,
        roadmap.prd_id,
        roadmap.prd_version,
        roadmap.source_request_digest,
        roadmap.requirements_digest,
        roadmap.requirements_approval_digest,
        roadmap.prd_digest,
        roadmap.prd_approval_digest,
        roadmap.digest,
        approval.digest,
        GENERATION_PROFILE,
        f"{prd.title} — Delivery Effort Estimate",
        values,
        sum(value.minimum_effort_days for value in values),
        sum(value.maximum_effort_days for value in values),
        EFFORT_UNIT,
        confidence,
        assumptions,
        generated_at,
    )


def _confidence(prd: CustomerPrdDraft) -> EstimateConfidence:
    if prd.data_sensitivity is DataSensitivity.SENSITIVE_DATA or len(prd.requirements) > 15:
        return EstimateConfidence.LOW
    if prd.data_sensitivity is DataSensitivity.PERSONAL_DATA or len(prd.requirements) > 8:
        return EstimateConfidence.MEDIUM
    return EstimateConfidence.HIGH


def _band(maximum: int) -> EffortBand:
    if maximum <= 10:
        return EffortBand.SMALL
    if maximum <= 25:
        return EffortBand.MEDIUM
    if maximum <= 50:
        return EffortBand.LARGE
    return EffortBand.EXTRA_LARGE
