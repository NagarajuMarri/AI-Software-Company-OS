"""Approve and immutably lock one exact customer roadmap draft."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac

from runtime.customer_application import CustomerProductRequest
from runtime.customer_prd import CustomerPrdApproval, CustomerPrdDraft
from runtime.customer_roadmap.approval_models import (
    ROADMAP_CONFIRMATION_VERSION,
    CustomerRoadmapApproval,
    LockedCustomerRoadmap,
    LockedCustomerRoadmapMilestone,
    roadmap_approval_id_for,
)
from runtime.customer_roadmap.approval_persistence import FileCustomerRoadmapApprovalStore
from runtime.customer_roadmap.errors import CustomerRoadmapApprovalConflict
from runtime.customer_roadmap.models import CustomerRoadmapDraft
from runtime.customer_roadmap.service import CustomerRoadmapService


class CustomerRoadmapApprovalService:
    """Approve and lock exactly one customer-owned roadmap version."""

    def __init__(
        self,
        store: FileCustomerRoadmapApprovalStore,
        roadmaps: CustomerRoadmapService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._roadmaps = roadmaps
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
        CustomerRoadmapApproval | None,
    ]:
        request, prd, prd_approval, roadmap = self._roadmaps.context(
            customer_id,
            request_id,
        )
        receipt = self._store.find(customer_id, request_id)
        if receipt is not None:
            if (
                roadmap is None
                or prd is None
                or prd_approval is None
                or receipt.customer_id != customer_id
                or receipt.request_id != request_id
                or receipt.roadmap_id != roadmap.roadmap_id
                or receipt.product_id != roadmap.product_id
                or receipt.prd_id != roadmap.prd_id
                or receipt.prd_version != roadmap.prd_version
                or not hmac.compare_digest(
                    receipt.source_request_digest,
                    roadmap.source_request_digest,
                )
                or not hmac.compare_digest(
                    receipt.requirements_digest,
                    roadmap.requirements_digest,
                )
                or not hmac.compare_digest(
                    receipt.requirements_approval_digest,
                    roadmap.requirements_approval_digest,
                )
                or not hmac.compare_digest(receipt.prd_digest, roadmap.prd_digest)
                or not hmac.compare_digest(
                    receipt.prd_approval_digest,
                    roadmap.prd_approval_digest,
                )
                or not hmac.compare_digest(receipt.roadmap_digest, roadmap.digest)
            ):
                raise CustomerRoadmapApprovalConflict(
                    "Roadmap approval does not bind the current customer roadmap"
                )
            locked = governed_locked_roadmap(roadmap, receipt)
            if (
                locked.status != "LOCKED"
                or locked.approved_by != customer_id
                or locked.locked_at != receipt.approved_at
                or locked.source_roadmap_digest != roadmap.digest
                or locked.approval_digest != receipt.digest
                or locked.requirement_ids != roadmap.requirement_ids
                or any(item.status != "LOCKED" for item in locked.milestones)
            ):
                raise CustomerRoadmapApprovalConflict(
                    "Roadmap approval failed governed lock validation"
                )
        return request, prd, prd_approval, roadmap, receipt

    def approve(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_roadmap_digest: str,
        confirmed: bool,
    ) -> CustomerRoadmapApproval:
        if confirmed is not True:
            raise ValueError("Explicit customer roadmap confirmation is required")
        _, _, _, roadmap, existing = self.context(customer_id, request_id)
        if roadmap is None:
            raise CustomerRoadmapApprovalConflict("A customer roadmap draft is required")
        if (
            not isinstance(expected_roadmap_digest, str)
            or not hmac.compare_digest(expected_roadmap_digest, roadmap.digest)
        ):
            raise CustomerRoadmapApprovalConflict("Customer roadmap approval form is stale")
        if existing is not None:
            return existing
        value = CustomerRoadmapApproval(
            roadmap_approval_id_for(request_id),
            customer_id,
            request_id,
            roadmap.roadmap_id,
            roadmap.product_id,
            roadmap.prd_id,
            roadmap.prd_version,
            roadmap.source_request_digest,
            roadmap.requirements_digest,
            roadmap.requirements_approval_digest,
            roadmap.prd_digest,
            roadmap.prd_approval_digest,
            roadmap.digest,
            ROADMAP_CONFIRMATION_VERSION,
            self._clock(),
        )
        governed_locked_roadmap(roadmap, value)
        return self._store.save(value)

    def is_locked(self, customer_id: str, request_id: str) -> bool:
        return self._store.is_locked(customer_id, request_id)

    def governed_roadmap(
        self,
        customer_id: str,
        request_id: str,
    ) -> LockedCustomerRoadmap:
        _, _, _, roadmap, receipt = self.context(customer_id, request_id)
        if roadmap is None or receipt is None:
            raise CustomerRoadmapApprovalConflict("A locked customer roadmap is required")
        return governed_locked_roadmap(roadmap, receipt)


def governed_locked_roadmap(
    roadmap: CustomerRoadmapDraft,
    receipt: CustomerRoadmapApproval,
) -> LockedCustomerRoadmap:
    """Project one exact approval receipt into a terminal locked roadmap."""

    if (
        receipt.customer_id != roadmap.customer_id
        or receipt.request_id != roadmap.request_id
        or receipt.roadmap_id != roadmap.roadmap_id
        or receipt.product_id != roadmap.product_id
        or receipt.prd_id != roadmap.prd_id
        or receipt.prd_version != roadmap.prd_version
        or not hmac.compare_digest(
            receipt.source_request_digest,
            roadmap.source_request_digest,
        )
        or not hmac.compare_digest(receipt.requirements_digest, roadmap.requirements_digest)
        or not hmac.compare_digest(
            receipt.requirements_approval_digest,
            roadmap.requirements_approval_digest,
        )
        or not hmac.compare_digest(receipt.prd_digest, roadmap.prd_digest)
        or not hmac.compare_digest(
            receipt.prd_approval_digest,
            roadmap.prd_approval_digest,
        )
        or not hmac.compare_digest(receipt.roadmap_digest, roadmap.digest)
    ):
        raise CustomerRoadmapApprovalConflict(
            "Roadmap approval receipt does not bind this roadmap"
        )
    milestones = tuple(
        LockedCustomerRoadmapMilestone(
            item.roadmap_item_id,
            item.milestone,
            item.sequence,
            item.requirement_ids,
            item.priorities,
        )
        for item in roadmap.milestones
    )
    return LockedCustomerRoadmap(
        roadmap.roadmap_id,
        roadmap.customer_id,
        roadmap.request_id,
        roadmap.product_id,
        roadmap.prd_id,
        roadmap.prd_version,
        roadmap.title,
        roadmap.digest,
        receipt.approval_id,
        receipt.digest,
        receipt.customer_id,
        receipt.approved_at,
        milestones,
    )
