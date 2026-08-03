"""Models for adopting existing product work into human-reviewed delivery."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from runtime.product_delivery.models import ProviderExecutionMode


class ImplementationSource(str, Enum):
    EXISTING_PRODUCT_BRANCH = "EXISTING_PRODUCT_BRANCH"


class ExistingProductIntakeStage(str, Enum):
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    VERIFYING = "VERIFYING"
    WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"


class VerificationOutcome(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BranchReconciliation:
    base_sha: str
    head_sha: str
    merge_base_sha: str
    base_is_ancestor: bool
    commit_count: int
    changed_paths: tuple[str, ...]
    changed_path_digest: str
    diff_digest: str
    additions: int
    deletions: int
    working_tree_clean: bool
    remote_base_exists: bool
    remote_head_exists: bool
    existing_pr_number: int | None = None
    existing_pr_url: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    gate: str
    outcome: VerificationOutcome
    details: str
    recorded_at: datetime


@dataclass
class HumanReviewedProductDelivery:
    project_id: str
    milestone_id: str
    milestone_title: str
    repository: str
    base_branch: str
    current_branch: str
    expected_base_sha: str
    expected_head_sha: str
    execution_mode: ProviderExecutionMode
    implementation_source: ImplementationSource
    implementation_provider: str
    implementation_evidence: str
    knowledge_snapshot: str
    reviewer_identity_required: bool
    verification_requirements: tuple[str, ...]
    reconciliation: BranchReconciliation
    stage: ExistingProductIntakeStage
    verification_results: tuple[VerificationResult, ...] = ()
    reviewer: str | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    known_limitations: tuple[str, ...] = ()
    created_at: datetime | None = None


@dataclass(frozen=True)
class ExistingProductDashboard:
    project: str
    milestone: str
    branch: str
    pull_request: str | None
    provider: str
    review_state: ExistingProductIntakeStage
    reviewer: str | None
    knowledge_snapshot: str
    latest_commit: str
    pending_actions: tuple[str, ...]
    progress: int
