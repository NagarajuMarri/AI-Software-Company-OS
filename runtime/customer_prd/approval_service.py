"""Explicit customer approval and immutable locking for an exact PRD draft."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import hmac

from runtime.customer_application.models import CustomerProductRequest
from runtime.customer_prd.approval_models import (
    PRD_CONFIRMATION_VERSION,
    CustomerPrdApproval,
    prd_approval_id_for,
)
from runtime.customer_prd.approval_persistence import FileCustomerPrdApprovalStore
from runtime.customer_prd.errors import CustomerPrdApprovalConflict
from runtime.customer_prd.models import CustomerPrdDraft
from runtime.customer_prd.service import CustomerPrdService
from runtime.customer_requirements import (
    CustomerRequirementsApproval,
    CustomerRequirementsDraft,
)
from runtime.product_requirements import (
    ProductRequirementsDocument,
    RequirementApproval,
    RequirementStatus,
    RevisionRecord,
    validate_prd,
)
from runtime.product_requirements.lifecycle import transition_requirement


class CustomerPrdApprovalService:
    """Approve and lock exactly one customer-owned PRD version."""

    def __init__(
        self,
        store: FileCustomerPrdApprovalStore,
        prds: CustomerPrdService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._prds = prds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[
        CustomerProductRequest,
        CustomerRequirementsDraft | None,
        CustomerRequirementsApproval | None,
        CustomerPrdDraft | None,
        CustomerPrdApproval | None,
    ]:
        request, draft, requirements_approval, prd = self._prds.context(
            customer_id,
            request_id,
        )
        receipt = self._store.find(customer_id, request_id)
        if receipt is not None:
            if (
                prd is None
                or receipt.customer_id != customer_id
                or receipt.request_id != request_id
                or receipt.artifact_id != prd.artifact_id
                or receipt.product_id != prd.product_id
                or receipt.prd_id != prd.prd_id
                or receipt.prd_version != prd.version
                or not hmac.compare_digest(
                    receipt.source_request_digest,
                    prd.source_request_digest,
                )
                or not hmac.compare_digest(receipt.requirements_digest, prd.requirements_digest)
                or not hmac.compare_digest(
                    receipt.requirements_approval_digest,
                    prd.approval_digest,
                )
                or not hmac.compare_digest(receipt.prd_digest, prd.digest)
            ):
                raise CustomerPrdApprovalConflict(
                    "PRD approval does not bind the current customer PRD"
                )
            locked = governed_locked_document(prd, receipt)
            if (
                locked.status is not RequirementStatus.LOCKED
                or locked.approver != customer_id
                or locked.locked_at != receipt.approved_at
                or any(item.status is not RequirementStatus.LOCKED for item in locked.requirements)
                or validate_prd(locked)
            ):
                raise CustomerPrdApprovalConflict(
                    "PRD approval failed governed lifecycle validation"
                )
        return request, draft, requirements_approval, prd, receipt

    def approve(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_prd_digest: str,
        confirmed: bool,
    ) -> CustomerPrdApproval:
        if confirmed is not True:
            raise ValueError("Explicit customer PRD confirmation is required")
        _, _, requirements_approval, prd, existing = self.context(customer_id, request_id)
        if prd is None or requirements_approval is None:
            raise CustomerPrdApprovalConflict("A generated customer PRD draft is required")
        if (
            not isinstance(expected_prd_digest, str)
            or not hmac.compare_digest(expected_prd_digest, prd.digest)
        ):
            raise CustomerPrdApprovalConflict("Customer PRD approval form is stale")
        if existing is not None:
            return existing
        value = CustomerPrdApproval(
            prd_approval_id_for(request_id),
            customer_id,
            request_id,
            prd.artifact_id,
            prd.product_id,
            prd.prd_id,
            prd.version,
            prd.source_request_digest,
            prd.requirements_digest,
            prd.approval_digest,
            prd.digest,
            PRD_CONFIRMATION_VERSION,
            self._clock(),
        )
        locked = governed_locked_document(prd, value)
        if validate_prd(locked):
            raise CustomerPrdApprovalConflict(
                "Customer PRD failed governed lifecycle validation"
            )
        return self._store.save(value)

    def is_locked(self, customer_id: str, request_id: str) -> bool:
        return self._store.is_locked(customer_id, request_id)

    def governed_document(
        self,
        customer_id: str,
        request_id: str,
    ) -> ProductRequirementsDocument:
        _, _, _, prd, receipt = self.context(customer_id, request_id)
        if prd is None or receipt is None:
            raise CustomerPrdApprovalConflict("A locked customer PRD is required")
        return governed_locked_document(prd, receipt)


def governed_locked_document(
    prd: CustomerPrdDraft,
    receipt: CustomerPrdApproval,
) -> ProductRequirementsDocument:
    """Project one exact receipt through the governed review/approve/lock lifecycle."""

    if (
        receipt.customer_id != prd.customer_id
        or receipt.request_id != prd.request_id
        or receipt.artifact_id != prd.artifact_id
        or receipt.product_id != prd.product_id
        or receipt.prd_id != prd.prd_id
        or receipt.prd_version != prd.version
        or not hmac.compare_digest(receipt.source_request_digest, prd.source_request_digest)
        or not hmac.compare_digest(receipt.requirements_digest, prd.requirements_digest)
        or not hmac.compare_digest(
            receipt.requirements_approval_digest,
            prd.approval_digest,
        )
        or not hmac.compare_digest(receipt.prd_digest, prd.digest)
    ):
        raise CustomerPrdApprovalConflict("PRD approval receipt does not bind this PRD")
    actor = receipt.customer_id
    draft = prd.to_governed_document()
    reviewed_requirements = tuple(
        transition_requirement(item, RequirementStatus.UNDER_REVIEW, actor, receipt.approved_at)
        for item in draft.requirements
    )
    approved_requirements = tuple(
        transition_requirement(item, RequirementStatus.APPROVED, actor, receipt.approved_at)
        for item in reviewed_requirements
    )
    locked_requirements = tuple(
        transition_requirement(item, RequirementStatus.LOCKED, actor, receipt.approved_at)
        for item in approved_requirements
    )
    history = draft.revision_history + (
        RevisionRecord(
            prd.version,
            actor,
            RequirementStatus.UNDER_REVIEW.value,
            "Customer submitted the exact PRD for final review",
            receipt.approved_at,
        ),
        RevisionRecord(
            prd.version,
            actor,
            RequirementStatus.APPROVED.value,
            "Customer approved the exact PRD scope",
            receipt.approved_at,
        ),
        RevisionRecord(
            prd.version,
            actor,
            RequirementStatus.LOCKED.value,
            "Customer-approved PRD version frozen",
            receipt.approved_at,
        ),
    )
    approval = RequirementApproval(
        receipt.approval_id,
        tuple(item.requirement_id for item in locked_requirements),
        actor,
        "APPROVED_AND_LOCKED",
        "Customer reviewed and locked the exact PRD version",
        receipt.approved_at,
    )
    return replace(
        draft,
        status=RequirementStatus.LOCKED,
        approver=actor,
        requirements=locked_requirements,
        updated_at=receipt.approved_at,
        locked_at=receipt.approved_at,
        revision_history=history,
        approval_history=(approval,),
    )
