"""Domain models for human-reviewed product delivery."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class HumanReviewStage(str, Enum):
    PLANNED = "PLANNED"
    IMPLEMENTING = "IMPLEMENTING"
    IMPLEMENTED = "IMPLEMENTED"
    WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    MERGED = "MERGED"
    CANCELLED = "CANCELLED"


class ProviderExecutionMode(str, Enum):
    PLANNING_ONLY = "PLANNING_ONLY"
    IMPLEMENTATION_ONLY = "IMPLEMENTATION_ONLY"
    HUMAN_REVIEWED_IMPLEMENTATION = "HUMAN_REVIEWED_IMPLEMENTATION"
    AUTONOMOUS_IMPLEMENTATION = "AUTONOMOUS_IMPLEMENTATION"

    @property
    def permits_implementation(self) -> bool:
        return self is not ProviderExecutionMode.PLANNING_ONLY

    @property
    def requires_human_review(self) -> bool:
        return self is ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION


class ReviewDecisionType(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


@dataclass(frozen=True)
class ReviewDecision:
    reviewer: str
    decision: ReviewDecisionType
    decided_at: datetime
    comments: str


@dataclass
class ProductDeliveryState:
    project: str
    current_milestone: str
    current_branch: str
    current_pr: str | None = None
    current_provider: str | None = None
    execution_mode: ProviderExecutionMode = (
        ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION
    )
    review_state: HumanReviewStage = HumanReviewStage.PLANNED
    current_reviewer: str | None = None
    review_history: list[ReviewDecision] = field(default_factory=list)
    knowledge_snapshot: str | None = None
    implementation_plan: str | None = None
    latest_commit: str | None = None
    verification_status: str = "NOT_RUN"
    pending_actions: list[str] = field(default_factory=lambda: ["capture knowledge"])
    progress: int = 0
    implementer: str | None = None
    merge_authorized_by: str | None = None
    next_milestone: str | None = None


@dataclass(frozen=True)
class ProductDashboard:
    project: str
    current_milestone: str
    current_branch: str
    current_pr: str | None
    current_provider: str | None
    current_review_state: HumanReviewStage
    current_reviewer: str | None
    knowledge_snapshot: str | None
    latest_commit: str | None
    pending_actions: tuple[str, ...]
    progress: int
