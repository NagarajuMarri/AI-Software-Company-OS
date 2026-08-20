"""Explicit customer approval and immutable requirements locking."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac

from runtime.customer_application.models import CustomerProductRequest
from runtime.customer_requirements.approval_models import (
    CONFIRMATION_VERSION,
    CustomerRequirementsApproval,
    approval_id_for,
)
from runtime.customer_requirements.approval_persistence import (
    FileCustomerRequirementsApprovalStore,
)
from runtime.customer_requirements.errors import RequirementsApprovalConflict
from runtime.customer_requirements.models import CustomerRequirementsDraft
from runtime.customer_requirements.service import CustomerRequirementsService


class CustomerRequirementsApprovalService:
    """Approve exactly one current customer-owned requirements draft."""

    def __init__(
        self,
        store: FileCustomerRequirementsApprovalStore,
        requirements: CustomerRequirementsService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._requirements = requirements
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[
        CustomerProductRequest,
        CustomerRequirementsDraft | None,
        CustomerRequirementsApproval | None,
    ]:
        request, draft = self._requirements.context(customer_id, request_id)
        approval = self._store.find(customer_id, request_id)
        if approval is not None:
            if (
                draft is None
                or approval.customer_id != customer_id
                or approval.request_id != request_id
                or approval.draft_id != draft.draft_id
                or approval.draft_revision != draft.revision
                or not hmac.compare_digest(approval.source_request_digest, request.digest)
                or not hmac.compare_digest(approval.requirements_digest, draft.digest)
            ):
                raise RequirementsApprovalConflict("Approval does not bind the current requirements")
        return request, draft, approval

    def approve(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_revision: int,
        expected_digest: str,
        confirmed: bool,
    ) -> CustomerRequirementsApproval:
        if confirmed is not True:
            raise ValueError("Explicit requirements confirmation is required")
        request, draft, existing = self.context(customer_id, request_id)
        if draft is None:
            raise RequirementsApprovalConflict("A saved requirements draft is required")
        if (
            isinstance(expected_revision, bool)
            or expected_revision != draft.revision
            or not isinstance(expected_digest, str)
            or not hmac.compare_digest(expected_digest, draft.digest)
        ):
            raise RequirementsApprovalConflict("Requirements approval form is stale")
        if existing is not None:
            return existing
        value = CustomerRequirementsApproval(
            approval_id_for(request_id),
            customer_id,
            request_id,
            draft.draft_id,
            draft.revision,
            request.digest,
            draft.digest,
            CONFIRMATION_VERSION,
            self._clock(),
        )
        return self._store.save(value)

    def is_locked(self, customer_id: str, request_id: str) -> bool:
        return self._store.is_locked(customer_id, request_id)
