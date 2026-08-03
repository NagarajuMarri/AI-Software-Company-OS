"""Default human-reviewed product delivery pipeline."""

from typing import Protocol

from runtime.product_delivery.models import (
    HumanReviewStage,
    ProductDashboard,
    ProductDeliveryState,
    ProviderExecutionMode,
    ReviewDecision,
)
from runtime.product_delivery.persistence import ProductStateStore
from runtime.product_delivery.review import HumanReviewError, HumanReviewService


class ProductDeliveryError(ValueError):
    """Raised when product delivery order or policy is violated."""


class ImplementationProvider(Protocol):
    provider_id: str

    def dispatch(self, plan: str, mode: ProviderExecutionMode) -> str: ...


class MergeProvider(Protocol):
    def merge(self, pull_request: str, authorized_by: str) -> str: ...


class ProductDeliveryPipeline:
    """Project-to-next-milestone pipeline with mandatory human review."""

    def __init__(
        self,
        store: ProductStateStore,
        review_service: HumanReviewService | None = None,
    ) -> None:
        self.store = store
        self.review_service = review_service or HumanReviewService()

    def plan_milestone(
        self,
        project: str,
        milestone: str,
        branch: str,
        mode: ProviderExecutionMode = ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION,
    ) -> ProductDeliveryState:
        if mode is ProviderExecutionMode.AUTONOMOUS_IMPLEMENTATION:
            raise ProductDeliveryError("Autonomous implementation is disabled")
        self._require_text(project, "Project")
        self._require_text(milestone, "Milestone")
        self._require_text(branch, "Branch")
        if self.store.load(project) is not None:
            raise ProductDeliveryError("Project already has delivery state")
        state = ProductDeliveryState(project, milestone, branch, execution_mode=mode)
        self._save(state)
        return state

    def capture_knowledge(self, project: str, snapshot: str) -> ProductDeliveryState:
        state = self._get(project)
        self._require_active(state)
        self._require_text(snapshot, "Knowledge snapshot")
        state.knowledge_snapshot = snapshot
        state.pending_actions = ["create implementation plan"]
        state.progress = 10
        return self._save(state)

    def record_plan(self, project: str, plan: str) -> ProductDeliveryState:
        state = self._get(project)
        self._require_active(state)
        if state.knowledge_snapshot is None:
            raise ProductDeliveryError("Knowledge snapshot is required before planning")
        self._require_text(plan, "Implementation plan")
        state.implementation_plan = plan
        state.pending_actions = ["dispatch provider"]
        state.progress = 20
        return self._save(state)

    def dispatch(
        self, project: str, provider: ImplementationProvider, implementer: str
    ) -> str:
        state = self._get(project)
        if state.implementation_plan is None:
            raise ProductDeliveryError("Implementation plan is required before dispatch")
        if not state.execution_mode.permits_implementation:
            raise ProductDeliveryError("Planning-only mode cannot dispatch implementation")
        if state.review_state is not HumanReviewStage.PLANNED:
            raise ProductDeliveryError("Milestone is not ready for provider dispatch")
        self._require_text(implementer, "Implementer")
        state.review_state = HumanReviewStage.IMPLEMENTING
        state.current_provider = provider.provider_id
        state.implementer = implementer
        state.pending_actions = ["complete implementation"]
        state.progress = 35
        self._save(state)
        return provider.dispatch(state.implementation_plan, state.execution_mode)

    def record_implementation(
        self, project: str, commit: str, pull_request: str
    ) -> ProductDeliveryState:
        state = self._get(project)
        if state.review_state not in {
            HumanReviewStage.IMPLEMENTING,
            HumanReviewStage.IMPLEMENTED,
            HumanReviewStage.CHANGES_REQUESTED,
        }:
            raise ProductDeliveryError("Provider dispatch or requested changes are required")
        self._require_text(commit, "Commit")
        self._require_text(pull_request, "Pull request")
        state.latest_commit = commit
        state.current_pr = pull_request
        state.review_state = HumanReviewStage.IMPLEMENTED
        state.verification_status = "NOT_RUN"
        state.pending_actions = ["run verification"]
        state.progress = 55
        return self._save(state)

    def record_verification(self, project: str, passed: bool) -> ProductDeliveryState:
        state = self._get(project)
        if state.review_state is not HumanReviewStage.IMPLEMENTED:
            raise ProductDeliveryError("Implementation is required before verification")
        state.verification_status = "PASSED" if passed else "FAILED"
        state.pending_actions = ["request human review"] if passed else ["fix verification"]
        state.progress = 70 if passed else 55
        return self._save(state)

    def request_review(
        self, project: str, reviewer: str | None = None
    ) -> ProductDeliveryState:
        state = self._get(project)
        if not state.execution_mode.requires_human_review:
            raise ProductDeliveryError("Execution mode does not include human review")
        self.review_service.request_review(state, reviewer)
        state.pending_actions = ["human review"]
        state.progress = 80
        return self._save(state)

    def approve(
        self, project: str, reviewer: str, comments: str = ""
    ) -> ReviewDecision:
        state = self._get(project)
        result = self.review_service.approve(state, reviewer, comments)
        state.pending_actions = ["authorize merge"]
        state.progress = 90
        self._save(state)
        return result

    def request_changes(
        self, project: str, reviewer: str, comments: str
    ) -> ReviewDecision:
        state = self._get(project)
        result = self.review_service.request_changes(state, reviewer, comments)
        state.pending_actions = ["implement requested changes"]
        state.progress = 55
        self._save(state)
        return result

    def authorize_merge(self, project: str, human: str) -> ProductDeliveryState:
        state = self._get(project)
        if state.review_state is not HumanReviewStage.APPROVED:
            raise ProductDeliveryError("Human approval is required before merge authorization")
        self._require_text(human, "Merge authorizer")
        if state.implementer and human.strip().casefold() == state.implementer.casefold():
            raise HumanReviewError("Self-authorization is not permitted")
        state.merge_authorized_by = human
        state.pending_actions = ["merge pull request"]
        state.progress = 95
        return self._save(state)

    def merge(self, project: str, provider: MergeProvider) -> str:
        state = self._get(project)
        if state.merge_authorized_by is None or state.current_pr is None:
            raise ProductDeliveryError("Explicit merge authorization is required")
        result = provider.merge(state.current_pr, state.merge_authorized_by)
        state.review_state = HumanReviewStage.MERGED
        state.pending_actions = ["create next milestone"]
        state.progress = 100
        self._save(state)
        return result

    def create_next_milestone(
        self, project: str, milestone: str, branch: str
    ) -> ProductDeliveryState:
        previous = self._get(project)
        if previous.review_state is not HumanReviewStage.MERGED:
            raise ProductDeliveryError("Current milestone must be merged first")
        self._require_text(milestone, "Milestone")
        self._require_text(branch, "Branch")
        state = ProductDeliveryState(
            project,
            milestone,
            branch,
            execution_mode=previous.execution_mode,
        )
        self.store.save(state)
        return state

    def cancel(self, project: str) -> ProductDeliveryState:
        state = self._get(project)
        if state.review_state is HumanReviewStage.MERGED:
            raise ProductDeliveryError("Merged delivery cannot be cancelled")
        state.review_state = HumanReviewStage.CANCELLED
        state.pending_actions = []
        return self._save(state)

    def dashboard(self, project: str) -> ProductDashboard:
        state = self._get(project)
        return ProductDashboard(
            state.project,
            state.current_milestone,
            state.current_branch,
            state.current_pr,
            state.current_provider,
            state.review_state,
            state.current_reviewer,
            state.knowledge_snapshot,
            state.latest_commit,
            tuple(state.pending_actions),
            state.progress,
        )

    def _get(self, project: str) -> ProductDeliveryState:
        state = self.store.load(project)
        if state is None:
            raise ProductDeliveryError(f"Unknown project: {project}")
        return state

    def _save(self, state: ProductDeliveryState) -> ProductDeliveryState:
        self.store.save(state)
        return state

    @staticmethod
    def _require_active(state: ProductDeliveryState) -> None:
        if state.review_state is HumanReviewStage.CANCELLED:
            raise ProductDeliveryError("Cancelled delivery cannot be modified")

    @staticmethod
    def _require_text(value: str, label: str) -> None:
        if not value.strip():
            raise ProductDeliveryError(f"{label} is required")
