"""Guided customer requirements-refinement use cases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from runtime.customer_application.models import CustomerProductRequest
from runtime.customer_application.service import CustomerProductRequestService
from runtime.customer_requirements.errors import RequirementsDraftConflict, RequirementsDraftLocked
from runtime.customer_requirements.models import (
    ALLOWED_PLATFORMS,
    CustomerRequirementsDraft,
    DataSensitivity,
    DeliveryPriority,
    draft_id_for,
)
from runtime.customer_requirements.persistence import FileCustomerRequirementsStore


class CustomerRequirementsService:
    """Refine one owned immutable product request through append-only drafts."""

    def __init__(
        self,
        store: FileCustomerRequirementsStore,
        requests: CustomerProductRequestService,
        clock: Callable[[], datetime] | None = None,
        is_locked: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._store = store
        self._requests = requests
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock_lookup = is_locked or (lambda _customer_id, _request_id: False)

    def is_locked(self, customer_id: str, request_id: str) -> bool:
        """Return whether an immutable approval now prevents draft changes."""

        return self._lock_lookup(customer_id, request_id)

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[CustomerProductRequest, CustomerRequirementsDraft | None]:
        request = self._requests.get(customer_id, request_id)
        draft = self._store.latest(customer_id, request_id)
        if draft is not None and draft.source_request_digest != request.digest:
            raise RequirementsDraftConflict("Requirements source request changed")
        return request, draft

    def save(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_revision: int,
        primary_user_journey: str,
        desired_outcomes: tuple[str, ...],
        must_have_features: tuple[str, ...],
        success_metrics: tuple[str, ...],
        non_goals: tuple[str, ...],
        platforms: tuple[str, ...],
        data_sensitivity: DataSensitivity,
        delivery_priority: DeliveryPriority,
    ) -> CustomerRequirementsDraft:
        request, latest = self.context(customer_id, request_id)
        if self.is_locked(customer_id, request_id):
            raise RequirementsDraftLocked("Approved requirements cannot be revised")
        current_revision = 0 if latest is None else latest.revision
        if (
            not platforms
            or len(set(platforms)) != len(platforms)
            or not set(platforms).issubset(ALLOWED_PLATFORMS)
        ):
            raise ValueError("Requirements platforms are invalid")
        ordered_platforms = tuple(item for item in ALLOWED_PLATFORMS if item in platforms)
        candidate = CustomerRequirementsDraft(
            draft_id_for(request_id),
            customer_id,
            request_id,
            current_revision + 1,
            request.digest,
            primary_user_journey,
            desired_outcomes,
            must_have_features,
            success_metrics,
            non_goals,
            ordered_platforms,
            data_sensitivity,
            delivery_priority,
            self._clock(),
        )
        if latest is not None and latest.business_content == candidate.business_content:
            return latest
        if isinstance(expected_revision, bool) or expected_revision != current_revision:
            raise RequirementsDraftConflict("Requirements form is stale")
        return self._store.save(candidate)

    def history(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[CustomerRequirementsDraft, ...]:
        request = self._requests.get(customer_id, request_id)
        values = self._store.history(customer_id, request_id)
        if any(value.source_request_digest != request.digest for value in values):
            raise RequirementsDraftConflict("Requirements history source mismatch")
        return values
