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


class Provider:
    provider_id = "codex"

    def dispatch(self, plan, mode):
        return f"{self.provider_id}:{mode.value}:{plan}"


class Merger:
    def __init__(self):
        self.calls = []

    def merge(self, pull_request, authorized_by):
        self.calls.append((pull_request, authorized_by))
        return "merge-commit"


def pipeline(store=None):
    clock = lambda: datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    return ProductDeliveryPipeline(
        store or InMemoryProductStateStore(), HumanReviewService(clock)
    )


def implemented_delivery(service, *, mode=ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION):
    service.plan_milestone("ascos", "13.0", "agent/m13", mode)
    service.capture_knowledge("ascos", "knowledge:v1")
    service.record_plan("ascos", "implement milestone")
    assert service.dispatch("ascos", Provider(), "builder") == (
        f"codex:{mode.value}:implement milestone"
    )
    service.record_implementation("ascos", "abc123", "PR-13")
    return service.record_verification("ascos", True)


def test_human_reviewed_delivery_reaches_merge_and_next_milestone():
    service = pipeline()
    implemented_delivery(service)
    waiting = service.request_review("ascos", "reviewer")
    assert waiting.review_state is HumanReviewStage.WAITING_FOR_HUMAN_REVIEW
    decision = service.approve("ascos", "reviewer", "Ready to ship")
    assert decision.decision is ReviewDecisionType.APPROVED
    assert decision.decided_at == datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    service.authorize_merge("ascos", "reviewer")
    merger = Merger()
    assert service.merge("ascos", merger) == "merge-commit"
    assert merger.calls == [("PR-13", "reviewer")]
    dashboard = service.dashboard("ascos")
    assert dashboard.current_review_state is HumanReviewStage.MERGED
    assert dashboard.progress == 100
    assert dashboard.pending_actions == ("create next milestone",)
    next_state = service.create_next_milestone("ascos", "13.1", "agent/m13-1")
    assert next_state.current_milestone == "13.1"
    assert next_state.review_state is HumanReviewStage.PLANNED


def test_change_request_records_comments_and_supports_reimplementation():
    service = pipeline()
    implemented_delivery(service)
    service.request_review("ascos", "reviewer")
    decision = service.request_changes("ascos", "reviewer", "Add a regression test")
    assert decision.comments == "Add a regression test"
    state = service.record_implementation("ascos", "def456", "PR-13")
    assert state.latest_commit == "def456"
    assert len(state.review_history) == 1


@pytest.mark.parametrize("reviewer", ["builder", "BUILDER"])
def test_implementer_cannot_review_or_approve_their_own_work(reviewer):
    service = pipeline()
    implemented_delivery(service)
    with pytest.raises(HumanReviewError, match="own work"):
        service.request_review("ascos", reviewer)
    service.request_review("ascos", "human-reviewer")
    with pytest.raises(HumanReviewError, match="Self-approval"):
        service.approve("ascos", reviewer)


def test_review_requires_verification_and_assigned_reviewer():
    service = pipeline()
    service.plan_milestone("ascos", "13.0", "agent/m13")
    service.capture_knowledge("ascos", "snapshot")
    service.record_plan("ascos", "plan")
    service.dispatch("ascos", Provider(), "builder")
    service.record_implementation("ascos", "def456", "PR-13")
    with pytest.raises(HumanReviewError, match="verification"):
        service.request_review("ascos", "reviewer")
    service.record_verification("ascos", True)
    service.request_review("ascos", "alice")
    with pytest.raises(HumanReviewError, match="assigned reviewer"):
        service.approve("ascos", "bob")
    with pytest.raises(HumanReviewError, match="comments"):
        service.request_changes("ascos", "alice", "  ")


def test_merge_requires_approval_and_human_authorizer():
    service = pipeline()
    implemented_delivery(service)
    with pytest.raises(ProductDeliveryError, match="approval"):
        service.authorize_merge("ascos", "reviewer")
    service.request_review("ascos", "reviewer")
    service.approve("ascos", "reviewer")
    state = service.authorize_merge("ascos", "release-manager")
    assert state.merge_authorized_by == "release-manager"


def test_execution_modes_are_explicit_and_autonomous_is_disabled():
    planning = pipeline()
    planning.plan_milestone(
        "planning", "13.0", "agent/plan", ProviderExecutionMode.PLANNING_ONLY
    )
    planning.capture_knowledge("planning", "snapshot")
    planning.record_plan("planning", "plan")
    with pytest.raises(ProductDeliveryError, match="Planning-only"):
        planning.dispatch("planning", Provider(), "builder")

    implementation = pipeline()
    implemented_delivery(
        implementation, mode=ProviderExecutionMode.IMPLEMENTATION_ONLY
    )
    with pytest.raises(ProductDeliveryError, match="does not include human review"):
        implementation.request_review("ascos", "reviewer")

    with pytest.raises(ProductDeliveryError, match="disabled"):
        pipeline().plan_milestone(
            "auto", "13.0", "agent/auto", ProviderExecutionMode.AUTONOMOUS_IMPLEMENTATION
        )


def test_dashboard_exposes_delivery_status():
    service = pipeline()
    implemented_delivery(service)
    dashboard = service.dashboard("ascos")
    assert dashboard.project == "ascos"
    assert dashboard.current_milestone == "13.0"
    assert dashboard.current_branch == "agent/m13"
    assert dashboard.current_pr == "PR-13"
    assert dashboard.current_provider == "codex"
    assert dashboard.knowledge_snapshot == "knowledge:v1"
    assert dashboard.latest_commit == "abc123"


def test_json_store_round_trips_all_product_state(tmp_path):
    store = JsonProductStateStore(tmp_path)
    service = pipeline(store)
    implemented_delivery(service)
    service.request_review("ascos", "reviewer")
    service.approve("ascos", "reviewer", "approved")
    restored = store.load("ascos")
    assert restored is not None
    assert restored.current_milestone == "13.0"
    assert restored.current_provider == "codex"
    assert restored.verification_status == "PASSED"
    assert restored.pending_actions == ["authorize merge"]
    assert restored.review_history[0].comments == "approved"
    assert restored.review_history[0].decided_at.tzinfo is not None


@pytest.mark.parametrize("project", ["", "..", "../outside", "folder/project"])
def test_json_store_rejects_unsafe_project_identifiers(tmp_path, project):
    with pytest.raises(ValueError, match="filesystem-safe"):
        JsonProductStateStore(tmp_path).load(project)


def test_invalid_transition_and_cancellation_are_rejected():
    service = pipeline()
    service.plan_milestone("ascos", "13.0", "agent/m13")
    with pytest.raises(ProductDeliveryError, match="Knowledge snapshot"):
        service.record_plan("ascos", "plan")
    cancelled = service.cancel("ascos")
    assert cancelled.review_state is HumanReviewStage.CANCELLED
    with pytest.raises(ProductDeliveryError, match="PLANNED"):
        service.capture_knowledge("ascos", "snapshot")


def test_review_and_merge_authorization_are_bound_to_verified_commit():
    service = pipeline()
    implemented_delivery(service)
    service.request_review("ascos", "reviewer")
    decision = service.approve("ascos", "reviewer")
    assert decision.reviewed_commit == "abc123"
    state = service.store.load("ascos")
    assert state is not None
    state.latest_commit = "changed-after-review"
    service.store.save(state)
    with pytest.raises(ProductDeliveryError, match="stale"):
        service.authorize_merge("ascos", "release-manager")


def test_review_clock_must_be_timezone_aware():
    clock = lambda: datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc).replace(
        tzinfo=None
    )
    service = ProductDeliveryPipeline(
        InMemoryProductStateStore(), HumanReviewService(clock)
    )
    implemented_delivery(service)
    service.request_review("ascos", "reviewer")
    with pytest.raises(HumanReviewError, match="timezone-aware"):
        service.approve("ascos", "reviewer")


def test_merge_is_terminal_and_cannot_execute_twice():
    service = pipeline()
    implemented_delivery(service)
    service.request_review("ascos", "reviewer")
    service.approve("ascos", "reviewer")
    service.authorize_merge("ascos", "release-manager")
    service.merge("ascos", Merger())
    with pytest.raises(ProductDeliveryError, match="Approved delivery"):
        service.merge("ascos", Merger())


def test_planning_inputs_cannot_change_after_dispatch():
    service = pipeline()
    implemented_delivery(service)
    with pytest.raises(ProductDeliveryError, match="PLANNED"):
        service.capture_knowledge("ascos", "replacement")
    with pytest.raises(ProductDeliveryError, match="PLANNED"):
        service.record_plan("ascos", "replacement")
