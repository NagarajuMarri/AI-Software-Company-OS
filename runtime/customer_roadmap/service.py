"""Generate one deterministic roadmap draft from an exact locked customer PRD."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac

from runtime.customer_application import CustomerProductRequest
from runtime.customer_prd import (
    CustomerPrdApproval,
    CustomerPrdApprovalService,
    CustomerPrdDraft,
)
from runtime.customer_roadmap.errors import CustomerRoadmapConflict
from runtime.customer_roadmap.models import (
    GENERATION_PROFILE,
    CustomerRoadmapDraft,
    CustomerRoadmapMilestone,
    roadmap_id_for,
)
from runtime.customer_roadmap.persistence import FileCustomerRoadmapStore
from runtime.product_requirements import (
    ProductRequirementsDocument,
    ProductRequirementsService,
    RequirementStatus,
    validate_prd,
)


class CustomerRoadmapService:
    """Create and reopen exactly one customer-owned roadmap draft."""

    def __init__(
        self,
        store: FileCustomerRoadmapStore,
        prd_approvals: CustomerPrdApprovalService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._prd_approvals = prd_approvals
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[
        CustomerProductRequest,
        CustomerPrdDraft | None,
        CustomerPrdApproval | None,
        CustomerRoadmapDraft | None,
    ]:
        request, _, _, prd, approval = self._prd_approvals.context(customer_id, request_id)
        roadmap = self._store.find(customer_id, request_id)
        if roadmap is not None:
            if prd is None or approval is None:
                raise CustomerRoadmapConflict("Roadmap does not have locked PRD authority")
            locked = self._prd_approvals.governed_document(customer_id, request_id)
            expected = _milestones(locked)
            if (
                roadmap.customer_id != customer_id
                or roadmap.request_id != request_id
                or roadmap.product_id != prd.product_id
                or roadmap.prd_id != prd.prd_id
                or roadmap.prd_version != prd.version
                or not hmac.compare_digest(
                    roadmap.source_request_digest, prd.source_request_digest
                )
                or not hmac.compare_digest(roadmap.requirements_digest, prd.requirements_digest)
                or not hmac.compare_digest(
                    roadmap.requirements_approval_digest, prd.approval_digest
                )
                or not hmac.compare_digest(roadmap.prd_digest, prd.digest)
                or roadmap.prd_approval_id != approval.approval_id
                or not hmac.compare_digest(roadmap.prd_approval_digest, approval.digest)
                or roadmap.milestones != expected
                or set(roadmap.requirement_ids)
                != {requirement.requirement_id for requirement in locked.requirements}
            ):
                raise CustomerRoadmapConflict(
                    "Roadmap does not bind the current locked customer PRD"
                )
        return request, prd, approval, roadmap

    def generate(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_prd_approval_digest: str,
    ) -> CustomerRoadmapDraft:
        _, prd, approval, existing = self.context(customer_id, request_id)
        if prd is None or approval is None:
            raise CustomerRoadmapConflict("A locked customer PRD is required")
        if (
            not isinstance(expected_prd_approval_digest, str)
            or not hmac.compare_digest(expected_prd_approval_digest, approval.digest)
        ):
            raise CustomerRoadmapConflict("Customer roadmap form is stale")
        if existing is not None:
            return existing
        locked = self._prd_approvals.governed_document(customer_id, request_id)
        milestones = _milestones(locked)
        value = CustomerRoadmapDraft(
            roadmap_id_for(request_id),
            customer_id,
            request_id,
            prd.product_id,
            prd.prd_id,
            prd.version,
            prd.source_request_digest,
            prd.requirements_digest,
            prd.approval_digest,
            prd.digest,
            approval.approval_id,
            approval.digest,
            GENERATION_PROFILE,
            f"{prd.title} — Delivery Roadmap",
            milestones,
            self._clock(),
        )
        return self._store.save(value)


def _milestones(locked: ProductRequirementsDocument) -> tuple[CustomerRoadmapMilestone, ...]:
    if locked.status is not RequirementStatus.LOCKED or validate_prd(locked):
        raise CustomerRoadmapConflict("A valid locked governed PRD is required")
    grouped = ProductRequirementsService.roadmap(locked)
    items = ProductRequirementsService.roadmap_items(locked)
    if not grouped or len(grouped) != len(items):
        raise CustomerRoadmapConflict("Locked PRD did not produce a governed roadmap")
    result = tuple(
        CustomerRoadmapMilestone(
            item.roadmap_item_id,
            item.milestone,
            sequence,
            item.requirement_ids,
            group.priorities,
        )
        for sequence, (group, item) in enumerate(zip(grouped, items, strict=True), 1)
        if item.product_id == locked.product_id
        and item.milestone == group.milestone
        and item.requirement_ids == group.requirement_ids
    )
    expected = {requirement.requirement_id for requirement in locked.requirements}
    mapped = [requirement for milestone in result for requirement in milestone.requirement_ids]
    if len(result) != len(items) or len(mapped) != len(set(mapped)) or set(mapped) != expected:
        raise CustomerRoadmapConflict("Governed roadmap mapping is incomplete")
    return result
