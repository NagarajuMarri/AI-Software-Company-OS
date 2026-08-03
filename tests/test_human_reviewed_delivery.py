from datetime import datetime, timezone

import pytest

from runtime.product_delivery import (
    HumanReviewError,
    HumanReviewService,
    HumanReviewStage,
    InMemoryProductStateStore,
    JsonProductStateStore,
    ProductDeliveryError,
    ProductDeliveryPipeline,
    ProviderExecutionMode,
    ReviewDecisionType,
)


class DeterministicProvider:
    provider_id = "codex-experimental"

    def __init__(self) -> None:
        self.calls = []

    def dispatch(self, plan, mode):
        self.calls.append((plan, mode))
        return "provider-task-1"


class DeterministicMergeProvider:
    def __init__(self) -> None:
        self.calls = []

    def merge(self, pull_request, authorized_by):
        self.calls.append((pull_request, authorized_by))
        return "merge-commit-1"


def pipeline(clock=None, store=None):
    review = HumanReviewService(clock) if clock else None
    return ProductDeliveryPipeline(store or InMemoryProductStateStore(), review)


def implemented_delivery(service, mode=ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION):
    service.plan_milestone("ascos", "13.0", "agent/m13", mode)
    service.capture_knowledge("ascos", "snapshot-13")
    service.record_plan("ascos", "implement human review")
    provider = DeterministicProvider()
    service.dispatch("ascos", provider, "agent-1")
    service.record_implementation("ascos", "abc123", "PR-21")
    return provider


def test_default_pipeline_runs_through_human_review_merge_and_next_milestone():
    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    service = pipeline(lambda: now)
    provider = implemented_delivery(service)
    service.record_verification("ascos", True)
    waiting = service.request_review("ascos", "human-1")

    assert waiting.review_state is HumanReviewStage.WAITING_FOR_HUMAN_REVIEW
    assert provider.calls == [
        ("implement human review", ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION)
    ]
    decision = service.approve("ascos", "human-1", "Reviewed tests and diff")
    assert decision.decision is ReviewDecisionType.APPROVED
    assert decision.decided_at == now
    assert decision.comments == "Reviewed tests and diff"

    service.authorize_merge("ascos", "human-1")
    merger = DeterministicMergeProvider()
    assert service.merge("ascos", merger) == "merge-commit-1"
    assert merger.calls == [("PR-21", "human-1")]
    assert service.dashboard("ascos").current_review_state is HumanReviewStage.MERGED

    next_state = service.create_next_milestone("ascos", "13.1", "agent/m13-1")
    assert next_state.current_milestone == "13.1"
    assert next_state.review_state is HumanReviewStage.PLANNED
    assert next_state.progress == 0


def test_dashboard_tracks_required_product_fields():
    service = pipeline()
    implemented_delivery(service)
    service.record_verification("ascos", True)
    service.request_review("ascos", "human-1")

    dashboard = service.dashboard("ascos")
    assert dashboard.project == "ascos"
    assert dashboard.current_milestone == "13.0"
    assert dashboard.current_branch == "agent/m13"
    assert dashboard.current_pr == "PR-21"
    assert dashboard.current_provider == "codex-experimental"
    assert dashboard.current_review_state is HumanReviewStage.WAITING_FOR_HUMAN_REVIEW
    assert dashboard.current_reviewer == "human-1"
    assert dashboard.knowledge_snapshot == "snapshot-13"
    assert dashboard.latest_commit == "abc123"
    assert dashboard.pending_actions == ("human review",)
    assert dashboard.progress == 80


def test_self_approval_is_prevented_for_implementer_and_provider():
    service = pipeline()
    implemented_delivery(service)
    service.record_verification("ascos", True)
    service.request_review("ascos")

    with pytest.raises(HumanReviewError, match="Self-approval"):
        service.approve("ascos", "agent-1")
    with pytest.raises(HumanReviewError, match="Self-approval"):
        service.approve("ascos", "codex-experimental")
    assert service.dashboard("ascos").current_review_state is HumanReviewStage.WAITING_FOR_HUMAN_REVIEW


def test_assigned_reviewer_is_enforced():
    service = pipeline()
    implemented_delivery(service)
    service.record_verification("ascos", True)
    service.request_review("ascos", "human-1")
    with pytest.raises(HumanReviewError, match="assigned reviewer"):
        service.approve("ascos", "human-2")


def test_changes_requested_requires_comments_and_supports_reimplementation():
    service = pipeline()
    implemented_delivery(service)
    service.record_verification("ascos", True)
    service.request_review("ascos", "human-1")
    with pytest.raises(HumanReviewError, match="comments"):
        service.request_changes("ascos", "human-1", "  ")

    decision = service.request_changes("ascos", "human-1", "Add an audit test")
    assert decision.decision is ReviewDecisionType.CHANGES_REQUESTED
    service.record_implementation("ascos", "def456", "PR-21")
    service.record_verification("ascos", True)
    service.request_review("ascos", "human-2")
    service.approve("ascos", "human-2")

    state = service.store.load("ascos")
    assert state is not None
    assert [item.decision for item in state.review_history] == [
        ReviewDecisionType.CHANGES_REQUESTED,
        ReviewDecisionType.APPROVED,
    ]
    assert state.latest_commit == "def456"


def test_verification_is_required_before_review_and_approval_before_merge():
    service = pipeline()
    implemented_delivery(service)
    with pytest.raises(HumanReviewError, match="verification"):
        service.request_review("ascos")
    service.record_verification("ascos", False)
    with pytest.raises(HumanReviewError, match="verification"):
        service.request_review("ascos")
    with pytest.raises(ProductDeliveryError, match="approval"):
        service.authorize_merge("ascos", "release-manager")


@pytest.mark.parametrize(
    "mode",
    [
        ProviderExecutionMode.IMPLEMENTATION_ONLY,
        ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION,
    ],
)
def test_enabled_implementation_modes_dispatch(mode):
    service = pipeline()
    provider = implemented_delivery(service, mode)
    assert provider.calls[0][1] is mode


def test_planning_only_mode_stops_before_implementation():
    service = pipeline()
    service.plan_milestone(
        "ascos", "13.0", "agent/m13", ProviderExecutionMode.PLANNING_ONLY
    )
    service.capture_knowledge("ascos", "snapshot")
    service.record_plan("ascos", "plan")
    with pytest.raises(ProductDeliveryError, match="Planning-only"):
        service.dispatch("ascos", DeterministicProvider(), "agent-1")


def test_autonomous_mode_is_disabled():
    service = pipeline()
    with pytest.raises(ProductDeliveryError, match="disabled"):
        service.plan_milestone(
            "ascos",
            "13.0",
            "agent/m13",
            ProviderExecutionMode.AUTONOMOUS_IMPLEMENTATION,
        )


def test_json_state_survives_restart_with_review_history(tmp_path):
    store = JsonProductStateStore(tmp_path)
    first = pipeline(store=store)
    implemented_delivery(first)
    first.record_verification("ascos", True)
    first.request_review("ascos", "human-1")
    first.request_changes("ascos", "human-1", "Document the boundary")

    restarted = pipeline(store=JsonProductStateStore(tmp_path))
    state = restarted.store.load("ascos")
    assert state is not None
    assert state.current_milestone == "13.0"
    assert state.current_branch == "agent/m13"
    assert state.current_pr == "PR-21"
    assert state.review_state is HumanReviewStage.CHANGES_REQUESTED
    assert state.knowledge_snapshot == "snapshot-13"
    assert state.current_provider == "codex-experimental"
    assert state.verification_status == "PASSED"
    assert state.pending_actions == ["implement requested changes"]
    assert state.review_history[0].comments == "Document the boundary"


def test_pipeline_rejects_out_of_order_operations():
    service = pipeline()
    service.plan_milestone("ascos", "13.0", "agent/m13")
    with pytest.raises(ProductDeliveryError, match="snapshot"):
        service.record_plan("ascos", "plan")
    with pytest.raises(ProductDeliveryError, match="plan"):
        service.dispatch("ascos", DeterministicProvider(), "agent-1")
    with pytest.raises(ProductDeliveryError, match="dispatch"):
        service.record_implementation("ascos", "abc", "PR-21")


def test_cancel_is_terminal_for_active_delivery():
    service = pipeline()
    service.plan_milestone("ascos", "13.0", "agent/m13")
    state = service.cancel("ascos")
    assert state.review_state is HumanReviewStage.CANCELLED
    assert state.pending_actions == []
