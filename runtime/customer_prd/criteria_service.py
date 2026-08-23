"""Customer-governed feature acceptance-criteria refinement."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
import hmac

from runtime.customer_prd.criteria_models import (
    CRITERIA_CONFIRMATION_VERSION,
    CustomerPrdCriteriaEntry,
    CustomerPrdCriteriaRefinement,
    criteria_refinement_id_for,
)
from runtime.customer_prd.criteria_persistence import FileCustomerPrdCriteriaStore
from runtime.customer_prd.errors import CustomerPrdCriteriaConflict, CustomerPrdCriteriaCorrupt
from runtime.customer_prd.models import CustomerPrdDraft
from runtime.customer_prd.service import CustomerPrdService


class CustomerPrdCriteriaService:
    """Lock customer-reviewed criteria against one exact generated PRD."""

    def __init__(
        self,
        store: FileCustomerPrdCriteriaStore,
        prds: CustomerPrdService,
        clock: Callable[[], datetime] | None = None,
        prd_approval_locked: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._store = store
        self._prds = prds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._prd_approval_locked = prd_approval_locked

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[CustomerPrdDraft | None, CustomerPrdCriteriaRefinement | None]:
        _, _, _, prd = self._prds.context(customer_id, request_id)
        refinement = self._store.find(customer_id, request_id)
        if refinement is not None:
            if prd is None or not hmac.compare_digest(refinement.source_prd_digest, prd.digest):
                raise CustomerPrdCriteriaCorrupt(
                    "Customer PRD criteria do not bind the current PRD"
                )
            _validate_coverage(prd, refinement.entries)
        return prd, refinement

    def lock(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_prd_digest: str,
        criteria: Mapping[str, tuple[str, ...]],
        confirmed: bool,
    ) -> CustomerPrdCriteriaRefinement:
        if confirmed is not True:
            raise ValueError("Explicit criteria confirmation is required")
        if self._prd_approval_locked is not None and self._prd_approval_locked(
            customer_id,
            request_id,
        ):
            raise CustomerPrdCriteriaConflict(
                "An approved PRD cannot receive a new criteria baseline"
            )
        prd, existing = self.context(customer_id, request_id)
        if prd is None:
            raise CustomerPrdCriteriaConflict("A generated customer PRD draft is required")
        if (
            not isinstance(expected_prd_digest, str)
            or not hmac.compare_digest(expected_prd_digest, prd.digest)
        ):
            raise CustomerPrdCriteriaConflict("Customer PRD criteria form is stale")
        expected_ids = {
            item.requirement_id for item in _feature_requirements(prd)
        }
        if set(criteria) != expected_ids:
            raise ValueError("Customer PRD criteria fields are incomplete")
        entries = tuple(
            CustomerPrdCriteriaEntry(item.requirement_id, criteria[item.requirement_id])
            for item in _feature_requirements(prd)
        )
        _validate_coverage(prd, entries)
        if existing is not None:
            if existing.entries == entries:
                return existing
            raise CustomerPrdCriteriaConflict(
                "A different customer PRD criteria baseline already exists"
            )
        value = CustomerPrdCriteriaRefinement(
            criteria_refinement_id_for(request_id),
            customer_id,
            request_id,
            prd.digest,
            entries,
            CRITERIA_CONFIRMATION_VERSION,
            self._clock(),
        )
        return self._store.save(value)

    def effective_prd(
        self,
        customer_id: str,
        request_id: str,
        *,
        required: bool = False,
    ) -> CustomerPrdDraft | None:
        prd, refinement = self.context(customer_id, request_id)
        if prd is None:
            return None
        if refinement is None:
            if required:
                raise CustomerPrdCriteriaConflict(
                    "Locked feature acceptance criteria are required"
                )
            return prd
        criteria = {item.requirement_id: item.acceptance_criteria for item in refinement.entries}
        return replace(
            prd,
            requirements=tuple(
                replace(item, acceptance_criteria=criteria[item.requirement_id])
                if item.requirement_id in criteria
                else item
                for item in prd.requirements
            ),
        )

    def is_locked(self, customer_id: str, request_id: str) -> bool:
        return self.context(customer_id, request_id)[1] is not None


def _feature_requirements(prd: CustomerPrdDraft):
    return tuple(
        item for item in prd.requirements if item.requirement_id.startswith("REQ-FEATURE-")
    )


def _validate_coverage(
    prd: CustomerPrdDraft,
    entries: tuple[CustomerPrdCriteriaEntry, ...],
) -> None:
    features = _feature_requirements(prd)
    if tuple(item.requirement_id for item in features) != tuple(
        item.requirement_id for item in entries
    ):
        raise CustomerPrdCriteriaCorrupt("Customer PRD criteria coverage is invalid")
    defaults = {item.requirement_id: item.acceptance_criteria for item in features}
    if any(item.acceptance_criteria == defaults[item.requirement_id] for item in entries):
        raise CustomerPrdCriteriaConflict(
            "Every feature requires customer-refined acceptance criteria"
        )
