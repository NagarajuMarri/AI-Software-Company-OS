"""Customer product-request use cases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from runtime.customer_application.errors import ProductRequestConflict, ProductRequestNotFound
from runtime.customer_application.models import CustomerProductRequest, ProductRequestStage
from runtime.customer_application.persistence import FileCustomerProductRequestStore


class CustomerProductRequestService:
    """Submit and read customer-owned immutable product briefs."""

    def __init__(
        self,
        store: FileCustomerProductRequestStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def submit(
        self,
        *,
        request_id: str,
        customer_id: str,
        product_name: str,
        product_summary: str,
        target_users: str,
        features: tuple[str, ...],
        constraints: tuple[str, ...],
    ) -> CustomerProductRequest:
        candidate = CustomerProductRequest(
            request_id,
            customer_id,
            product_name,
            product_summary,
            target_users,
            features,
            constraints,
            ProductRequestStage.SUBMITTED,
            self._clock(),
        )
        try:
            existing = self._store.load(customer_id, request_id)
        except ProductRequestNotFound:
            try:
                return self._store.save(candidate)
            except ProductRequestConflict:
                existing = self._store.load(customer_id, request_id)
        if existing.business_identity == candidate.business_identity:
            return existing
        raise ProductRequestConflict(
            "Product request identity already has different immutable content"
        )

    def get(self, customer_id: str, request_id: str) -> CustomerProductRequest:
        return self._store.load(customer_id, request_id)

    def dashboard(self, customer_id: str) -> tuple[CustomerProductRequest, ...]:
        return self._store.list_for_customer(customer_id)
