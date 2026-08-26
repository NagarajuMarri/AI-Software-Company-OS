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
    LEGACY_GENERATION_PROFILE,
    CustomerRoadmapDraft,
    CustomerRoadmapMilestone,
    roadmap_id_for,
)
from runtime.customer_roadmap.persistence import FileCustomerRoadmapStore
from runtime.product_requirements import (
    ProductRequirement,
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
        roadmap_approval_locked: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._store = store
        self._prd_approvals = prd_approvals
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._roadmap_approval_locked = roadmap_approval_locked

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
            expected = (
                _legacy_milestones(locked)
                if roadmap.generation_profile == LEGACY_GENERATION_PROFILE
                else _milestones(locked)
            )
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
        if existing is not None and existing.generation_profile == GENERATION_PROFILE:
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
        if existing is not None:
            if self._roadmap_approval_locked is None or self._roadmap_approval_locked(
                customer_id,
                request_id,
            ):
                raise CustomerRoadmapConflict(
                    "An approved or unverifiable legacy roadmap cannot be regenerated"
                )
            return self._store.replace_legacy(existing, value)
        return self._store.save(value)


def _milestones(locked: ProductRequirementsDocument) -> tuple[CustomerRoadmapMilestone, ...]:
    if locked.status is not RequirementStatus.LOCKED or validate_prd(locked):
        raise CustomerRoadmapConflict("A valid locked governed PRD is required")
    requirements = tuple(locked.requirements)
    guardrails = tuple(
        item
        for item in requirements
        if item.requirement_id.startswith(("REQ-CONSTRAINT-", "REQ-DATA-", "REQ-PLATFORM-"))
    )
    journeys = tuple(
        item for item in requirements if item.requirement_id.startswith("REQ-JOURNEY-")
    )
    capabilities = tuple(
        item
        for item in requirements
        if item.requirement_id.startswith("REQ-FEATURE-")
    )
    selected = {item.requirement_id for item in (*guardrails, *journeys, *capabilities)}
    remaining = tuple(item for item in requirements if item.requirement_id not in selected)

    groups: list[tuple[str, tuple[ProductRequirement, ...]]] = []
    for index, chunk in enumerate(_chunks(guardrails, 8), 1):
        title = (
            "Platform, data, and delivery foundation"
            if index == 1
            else f"Security and governance guardrails {index - 1}"
        )
        groups.append((title, chunk))
    for index, chunk in enumerate(_chunks(capabilities, 5), 1):
        lead = chunk[0].title
        available = 260 - len(str(index))
        groups.append((f"Capability increment {index} — {lead[:available]}", chunk))
    for index, chunk in enumerate(_chunks(remaining, 5), 1):
        groups.append((f"Operational and release requirements {index}", chunk))
    if journeys:
        groups.append(("End-to-end journey and release acceptance", journeys))
    if not groups:
        raise CustomerRoadmapConflict("Locked PRD did not produce governed milestones")

    result = tuple(
        CustomerRoadmapMilestone(
            f"roadmap-{locked.product_id}-{sequence:03d}",
            title,
            sequence,
            tuple(item.requirement_id for item in items),
            tuple(item.priority for item in items),
        )
        for sequence, (title, items) in enumerate(groups, 1)
    )
    expected = {requirement.requirement_id for requirement in requirements}
    mapped = [requirement for milestone in result for requirement in milestone.requirement_ids]
    if len(mapped) != len(set(mapped)) or set(mapped) != expected:
        raise CustomerRoadmapConflict("Governed roadmap mapping is incomplete")
    return result


def _legacy_milestones(
    locked: ProductRequirementsDocument,
) -> tuple[CustomerRoadmapMilestone, ...]:
    """Reconstruct v1 exactly so existing immutable drafts remain readable."""

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


def _chunks(
    values: tuple[ProductRequirement, ...],
    size: int,
) -> tuple[tuple[ProductRequirement, ...], ...]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))
