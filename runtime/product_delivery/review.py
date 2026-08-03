"""Human review policy and immutable decision recording."""

from collections.abc import Callable
from datetime import datetime, timezone

from runtime.product_delivery.models import (
    HumanReviewStage,
    ProductDeliveryState,
    ReviewDecision,
    ReviewDecisionType,
)


class HumanReviewError(ValueError):
    """Raised when a human-review policy is violated."""


class HumanReviewService:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def request_review(
        self, state: ProductDeliveryState, reviewer: str | None = None
    ) -> None:
        if state.review_state is not HumanReviewStage.IMPLEMENTED:
            raise HumanReviewError("Review requires an implemented milestone")
        if state.verification_status != "PASSED":
            raise HumanReviewError("Review requires successful verification")
        if reviewer is not None:
            self._require_identity(reviewer, "Reviewer")
            if self._same_identity(reviewer, state.implementer):
                raise HumanReviewError("Implementer cannot review their own work")
        state.current_reviewer = reviewer
        state.review_state = HumanReviewStage.WAITING_FOR_HUMAN_REVIEW

    def approve(
        self, state: ProductDeliveryState, reviewer: str, comments: str = ""
    ) -> ReviewDecision:
        return self._record(state, reviewer, ReviewDecisionType.APPROVED, comments)

    def request_changes(
        self, state: ProductDeliveryState, reviewer: str, comments: str
    ) -> ReviewDecision:
        if not comments.strip():
            raise HumanReviewError("Change requests require review comments")
        return self._record(
            state, reviewer, ReviewDecisionType.CHANGES_REQUESTED, comments
        )

    def _record(
        self,
        state: ProductDeliveryState,
        reviewer: str,
        decision: ReviewDecisionType,
        comments: str,
    ) -> ReviewDecision:
        if state.review_state is not HumanReviewStage.WAITING_FOR_HUMAN_REVIEW:
            raise HumanReviewError("A review must be requested before a decision")
        self._require_identity(reviewer, "Reviewer")
        if self._same_identity(reviewer, state.implementer) or self._same_identity(
            reviewer, state.current_provider
        ):
            raise HumanReviewError("Self-approval is not permitted")
        if state.current_reviewer and not self._same_identity(
            reviewer, state.current_reviewer
        ):
            raise HumanReviewError("Decision must be made by the assigned reviewer")
        item = ReviewDecision(reviewer, decision, self._clock(), comments.strip())
        state.review_history.append(item)
        state.current_reviewer = reviewer
        state.review_state = (
            HumanReviewStage.APPROVED
            if decision is ReviewDecisionType.APPROVED
            else HumanReviewStage.CHANGES_REQUESTED
        )
        return item

    @staticmethod
    def _require_identity(value: str, label: str) -> None:
        if not value.strip():
            raise HumanReviewError(f"{label} identity is required")

    @staticmethod
    def _same_identity(first: str, second: str | None) -> bool:
        return second is not None and first.strip().casefold() == second.strip().casefold()
