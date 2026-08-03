"""Human-reviewed intake service for work implemented before ASCOS adoption."""

from collections.abc import Callable
from datetime import datetime, timezone

from runtime.product_delivery.intake_models import (
    BranchReconciliation,
    ExistingProductDashboard,
    ExistingProductIntakeStage,
    HumanReviewedProductDelivery,
    ImplementationSource,
    VerificationOutcome,
    VerificationResult,
)
from runtime.product_delivery.intake_persistence import ExistingProductDeliveryStore
from runtime.product_delivery.models import ProviderExecutionMode


class ExistingProductIntakeError(ValueError):
    """Raised when existing product work cannot advance safely."""


class ExistingProductIntakeService:
    def __init__(
        self,
        store: ExistingProductDeliveryStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def register(
        self,
        *,
        project_id: str,
        milestone_id: str,
        milestone_title: str,
        repository: str,
        base_branch: str,
        current_branch: str,
        expected_base_sha: str,
        expected_head_sha: str,
        implementation_provider: str,
        implementation_evidence: str,
        knowledge_snapshot: str,
        verification_requirements: tuple[str, ...],
        reconciliation: BranchReconciliation,
        known_limitations: tuple[str, ...] = (),
    ) -> HumanReviewedProductDelivery:
        if self.store.load(project_id) is not None:
            raise ExistingProductIntakeError("Project intake already exists")
        required_text = {
            "project": project_id,
            "milestone": milestone_id,
            "milestone title": milestone_title,
            "repository": repository,
            "base branch": base_branch,
            "current branch": current_branch,
            "implementation provider": implementation_provider,
            "implementation evidence": implementation_evidence,
            "knowledge snapshot": knowledge_snapshot,
        }
        for label, item in required_text.items():
            if not item.strip():
                raise ExistingProductIntakeError(f"{label} is required")
        if not verification_requirements or len(set(verification_requirements)) != len(
            verification_requirements
        ):
            raise ExistingProductIntakeError(
                "Verification requirements must be non-empty and unique"
            )
        identities_match = (
            reconciliation.base_sha == expected_base_sha
            and reconciliation.head_sha == expected_head_sha
            and reconciliation.merge_base_sha == expected_base_sha
            and reconciliation.base_is_ancestor
            and reconciliation.working_tree_clean
            and reconciliation.remote_base_exists
            and reconciliation.remote_head_exists
        )
        delivery = HumanReviewedProductDelivery(
            project_id=project_id,
            milestone_id=milestone_id,
            milestone_title=milestone_title,
            repository=repository,
            base_branch=base_branch,
            current_branch=current_branch,
            expected_base_sha=expected_base_sha,
            expected_head_sha=expected_head_sha,
            execution_mode=ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION,
            implementation_source=ImplementationSource.EXISTING_PRODUCT_BRANCH,
            implementation_provider=implementation_provider,
            implementation_evidence=implementation_evidence,
            knowledge_snapshot=knowledge_snapshot,
            reviewer_identity_required=True,
            verification_requirements=verification_requirements,
            reconciliation=reconciliation,
            stage=(
                ExistingProductIntakeStage.VERIFYING
                if identities_match
                else ExistingProductIntakeStage.RECONCILIATION_REQUIRED
            ),
            pull_request_number=reconciliation.existing_pr_number,
            pull_request_url=reconciliation.existing_pr_url,
            known_limitations=known_limitations,
            created_at=self._utc_now(),
        )
        self.store.save(delivery)
        return delivery

    def record_verification(
        self, project_id: str, gate: str, passed: bool, details: str
    ) -> VerificationResult:
        delivery = self._get(project_id)
        if delivery.stage is not ExistingProductIntakeStage.VERIFYING:
            raise ExistingProductIntakeError("Delivery is not accepting verification")
        if gate not in delivery.verification_requirements:
            raise ExistingProductIntakeError(f"Unknown verification gate: {gate}")
        if any(result.gate == gate for result in delivery.verification_results):
            raise ExistingProductIntakeError(f"Verification gate already recorded: {gate}")
        if not details.strip():
            raise ExistingProductIntakeError("Verification details are required")
        result = VerificationResult(
            gate=gate,
            outcome=(VerificationOutcome.PASSED if passed else VerificationOutcome.FAILED),
            details=details.strip(),
            recorded_at=self._utc_now(),
        )
        delivery.verification_results += (result,)
        self.store.save(delivery)
        return result

    def request_human_review(
        self, project_id: str, reviewer: str
    ) -> HumanReviewedProductDelivery:
        delivery = self._get(project_id)
        if delivery.stage is not ExistingProductIntakeStage.VERIFYING:
            raise ExistingProductIntakeError("Delivery is not ready for review")
        if not reviewer.strip():
            raise ExistingProductIntakeError("Human reviewer identity is required")
        results = {result.gate: result for result in delivery.verification_results}
        missing = set(delivery.verification_requirements) - results.keys()
        if missing:
            raise ExistingProductIntakeError(
                f"Required verification gates are missing: {sorted(missing)}"
            )
        failed = [
            gate
            for gate, result in results.items()
            if result.outcome is VerificationOutcome.FAILED
        ]
        if failed:
            raise ExistingProductIntakeError(
                f"Failed verification blocks human review: {sorted(failed)}"
            )
        delivery.reviewer = reviewer.strip()
        delivery.stage = ExistingProductIntakeStage.WAITING_FOR_HUMAN_REVIEW
        self.store.save(delivery)
        return delivery

    def attach_pull_request(
        self, project_id: str, number: int, url: str
    ) -> HumanReviewedProductDelivery:
        delivery = self._get(project_id)
        if delivery.stage is not ExistingProductIntakeStage.WAITING_FOR_HUMAN_REVIEW:
            raise ExistingProductIntakeError("Verification must pass before PR attachment")
        if number < 1 or not url.strip():
            raise ExistingProductIntakeError("Valid pull request evidence is required")
        if delivery.pull_request_number is not None and (
            delivery.pull_request_number != number or delivery.pull_request_url != url
        ):
            raise ExistingProductIntakeError("Different pull request evidence already exists")
        delivery.pull_request_number = number
        delivery.pull_request_url = url.strip()
        self.store.save(delivery)
        return delivery

    def dashboard(self, project_id: str) -> ExistingProductDashboard:
        delivery = self._get(project_id)
        passed = sum(
            result.outcome is VerificationOutcome.PASSED
            for result in delivery.verification_results
        )
        total = len(delivery.verification_requirements)
        if delivery.stage is ExistingProductIntakeStage.RECONCILIATION_REQUIRED:
            actions = ("reconcile branch identity",)
            progress = 0
        elif delivery.stage is ExistingProductIntakeStage.VERIFYING:
            actions = ("complete required verification",)
            progress = 20 + int(60 * passed / total)
        else:
            actions = ("human review",)
            progress = 80
        return ExistingProductDashboard(
            project=delivery.project_id,
            milestone=delivery.milestone_title,
            branch=delivery.current_branch,
            pull_request=delivery.pull_request_url,
            provider=delivery.implementation_provider,
            review_state=delivery.stage,
            reviewer=delivery.reviewer,
            knowledge_snapshot=delivery.knowledge_snapshot,
            latest_commit=delivery.expected_head_sha,
            pending_actions=actions,
            progress=progress,
        )

    def _get(self, project_id: str) -> HumanReviewedProductDelivery:
        delivery = self.store.load(project_id)
        if delivery is None:
            raise ExistingProductIntakeError(f"Unknown product intake: {project_id}")
        return delivery

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ExistingProductIntakeError("Timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)
