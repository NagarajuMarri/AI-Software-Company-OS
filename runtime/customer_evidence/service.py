"""Govern preview evidence publication and exact customer ACCEPT/REVISE review."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac

from runtime.customer_evidence.errors import CustomerEvidenceConflict, CustomerEvidenceCorrupt
from runtime.customer_evidence.models import (
    REVIEW_CONFIRMATION_VERSION,
    CustomerPreviewEvidencePackage,
    CustomerPreviewReview,
    package_id_for,
    preview_origin,
    review_id_for,
)
from runtime.customer_evidence.persistence import FileCustomerPreviewEvidenceStore
from runtime.customer_progress import (
    CustomerProjectProgressService,
    CustomerProjectProgressSnapshot,
)
from runtime.runtime_acceptance import EvidenceArtifact


class CustomerPreviewEvidenceService:
    """Bind a product preview and evidence to the exact governed customer project."""

    def __init__(
        self,
        store: FileCustomerPreviewEvidenceStore,
        progress: CustomerProjectProgressService,
        allowed_preview_origins: tuple[str, ...],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            not isinstance(allowed_preview_origins, tuple)
            or not allowed_preview_origins
            or len(set(allowed_preview_origins)) != len(allowed_preview_origins)
        ):
            raise ValueError("Preview origin policy is required and must be unique")
        canonical = tuple(preview_origin(f"{value}/") for value in allowed_preview_origins)
        if canonical != allowed_preview_origins:
            raise ValueError("Preview origins must be canonical")
        self._store = store
        self._progress = progress
        self._allowed_preview_origins = frozenset(canonical)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def publish(
        self,
        *,
        customer_id: str,
        request_id: str,
        preview_label: str,
        preview_url: str,
        commit_sha: str,
        evidence: tuple[EvidenceArtifact, ...],
    ) -> CustomerPreviewEvidencePackage:
        """Record an already-produced preview; never create or deploy one."""

        snapshot = self._progress.view(customer_id, request_id)
        if preview_origin(preview_url) not in self._allowed_preview_origins:
            raise CustomerEvidenceConflict("Preview origin is outside customer evidence policy")
        value = CustomerPreviewEvidencePackage(
            package_id_for(request_id),
            customer_id,
            request_id,
            snapshot.product_id,
            snapshot.progress_id,
            snapshot.digest,
            snapshot.roadmap_digest,
            snapshot.estimate_digest,
            preview_label,
            preview_url,
            commit_sha,
            evidence,
            self._now(),
        )
        return self._store.save_package(value)

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[
        CustomerProjectProgressSnapshot,
        CustomerPreviewEvidencePackage | None,
        CustomerPreviewReview | None,
    ]:
        snapshot = self._progress.view(customer_id, request_id)
        package = self._store.find_package(customer_id, request_id)
        review = self._store.find_review(customer_id, request_id)
        if package is None:
            if review is not None:
                raise CustomerEvidenceCorrupt("Preview review exists without its package")
            return snapshot, None, None
        if (
            package.customer_id != customer_id
            or package.request_id != request_id
            or package.product_id != snapshot.product_id
            or package.progress_id != snapshot.progress_id
            or not hmac.compare_digest(package.progress_digest, snapshot.digest)
            or not hmac.compare_digest(package.roadmap_digest, snapshot.roadmap_digest)
            or not hmac.compare_digest(package.estimate_digest, snapshot.estimate_digest)
            or preview_origin(package.preview_url) not in self._allowed_preview_origins
        ):
            raise CustomerEvidenceCorrupt(
                "Preview evidence no longer binds the exact governed project"
            )
        if review is not None and (
            review.package_id != package.package_id
            or not hmac.compare_digest(review.package_digest, package.digest)
            or not hmac.compare_digest(review.progress_digest, snapshot.digest)
            or review.reviewed_at < package.published_at
        ):
            raise CustomerEvidenceCorrupt("Preview review no longer binds its exact package")
        return snapshot, package, review

    def review(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_package_digest: str,
        decision: str,
        comments: str,
        confirmed: bool,
    ) -> CustomerPreviewReview:
        snapshot, package, existing = self.context(customer_id, request_id)
        if package is None:
            raise CustomerEvidenceConflict("No preview evidence package is ready for review")
        if not confirmed or not hmac.compare_digest(
            package.digest,
            expected_package_digest,
        ):
            raise CustomerEvidenceConflict("Preview evidence review is stale or unconfirmed")
        if existing is not None:
            if (
                existing.decision == decision
                and existing.comments == comments.strip()
                and hmac.compare_digest(existing.package_digest, expected_package_digest)
            ):
                return existing
            raise CustomerEvidenceConflict("The exact preview evidence was already reviewed")
        if decision == "ACCEPT" and not package.all_required_evidence_passed:
            raise CustomerEvidenceConflict("Failed required evidence cannot be accepted")
        try:
            value = CustomerPreviewReview(
                review_id_for(request_id),
                package.package_id,
                customer_id,
                request_id,
                package.digest,
                snapshot.digest,
                decision,
                comments.strip(),
                REVIEW_CONFIRMATION_VERSION,
                self._now(),
            )
        except ValueError as error:
            raise CustomerEvidenceConflict("Customer preview decision is invalid") from error
        return self._store.save_review(value)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Customer preview clock must be timezone-aware")
        return value.astimezone(timezone.utc)
