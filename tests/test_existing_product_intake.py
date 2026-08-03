import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from runtime.product_delivery import (
    BranchReconciliation,
    ExistingProductIntakeError,
    ExistingProductIntakeService,
    ExistingProductIntakeStage,
    ImplementationSource,
    InMemoryExistingProductDeliveryStore,
    JsonExistingProductDeliveryStore,
    ProviderExecutionMode,
)

NOW = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)
REQUIRED_GATES = (
    "tests",
    "migration_sql",
    "migration_cycle",
    "compilation",
    "ai_example",
    "voice_example",
    "secret_scan",
    "diff_check",
)


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path):
    target = tmp_path / "product"
    target.mkdir()
    git(target, "init", "-b", "main")
    git(target, "config", "user.email", "fixture@example.invalid")
    git(target, "config", "user.name", "Fixture")
    (target / "README.md").write_text("base\n", encoding="utf-8")
    git(target, "add", "README.md")
    git(target, "commit", "-m", "base")
    base = git(target, "rev-parse", "HEAD")
    git(target, "checkout", "-b", "product/milestone-7")
    (target / "feature.py").write_text("VALUE = 7\n", encoding="utf-8")
    git(target, "add", "feature.py")
    git(target, "commit", "-m", "milestone 7")
    head = git(target, "rev-parse", "HEAD")
    return target, base, head


def reconciliation(repository: Path, base: str, head: str, **changes):
    paths = tuple(git(repository, "diff", "--name-only", f"{base}...{head}").splitlines())
    value = BranchReconciliation(
        base_sha=base,
        head_sha=head,
        merge_base_sha=git(repository, "merge-base", base, head),
        base_is_ancestor=True,
        commit_count=int(git(repository, "rev-list", "--count", f"{base}..{head}")),
        changed_paths=paths,
        changed_path_digest=hashlib.sha256("\n".join(paths).encode()).hexdigest(),
        diff_digest=hashlib.sha256(
            git(repository, "diff", "--binary", f"{base}...{head}").encode()
        ).hexdigest(),
        additions=1,
        deletions=0,
        working_tree_clean=not git(repository, "status", "--porcelain"),
        remote_base_exists=True,
        remote_head_exists=True,
    )
    return BranchReconciliation(**{**value.__dict__, **changes})


def register(service, repository: Path, base: str, head: str, **changes):
    return service.register(
        project_id="spoken-english-ai",
        milestone_id="product-milestone-7",
        milestone_title="Product Milestone 7 — Provider-Neutral AI Conversation and Voice Tutor",
        repository="NagarajuMarri/spoken-english-ai",
        base_branch="main",
        current_branch="product/milestone-7-ai-conversation-voice",
        expected_base_sha=base,
        expected_head_sha=head,
        implementation_provider="historical direct Codex-assisted implementation",
        implementation_evidence=(
            "Existing branch adopted for ASCOS validation; not originally implemented by ASCOS"
        ),
        knowledge_snapshot="knowledge:fixture",
        verification_requirements=REQUIRED_GATES,
        reconciliation=reconciliation(repository, base, head, **changes),
        known_limitations=("Synthetic pronunciation is not acoustic assessment",),
    )


def passing_service(repository, store=None):
    target, base, head = repository
    service = ExistingProductIntakeService(
        store or InMemoryExistingProductDeliveryStore(), lambda: NOW
    )
    delivery = register(service, target, base, head)
    for gate in REQUIRED_GATES:
        service.record_verification("spoken-english-ai", gate, True, f"{gate} passed")
    return service, delivery


def test_existing_product_branch_intake_binds_exact_base_and_head(repository):
    service, delivery = passing_service(repository)
    assert delivery.expected_base_sha == repository[1]
    assert delivery.expected_head_sha == repository[2]
    assert delivery.reconciliation.changed_paths == ("feature.py",)
    assert delivery.execution_mode is ProviderExecutionMode.HUMAN_REVIEWED_IMPLEMENTATION
    assert delivery.implementation_source is ImplementationSource.EXISTING_PRODUCT_BRANCH
    assert "not originally implemented by ASCOS" in delivery.implementation_evidence
    assert service.dashboard("spoken-english-ai").latest_commit == repository[2]


@pytest.mark.parametrize("field", ["base_sha", "head_sha", "merge_base_sha"])
def test_branch_identity_mismatch_requires_reconciliation(repository, field):
    target, base, head = repository
    service = ExistingProductIntakeService(InMemoryExistingProductDeliveryStore())
    delivery = register(service, target, base, head, **{field: "different"})
    assert delivery.stage is ExistingProductIntakeStage.RECONCILIATION_REQUIRED
    with pytest.raises(ExistingProductIntakeError, match="not accepting"):
        service.record_verification("spoken-english-ai", "tests", True, "passed")


def test_verification_failure_blocks_review_and_duplicate_results(repository):
    target, base, head = repository
    service = ExistingProductIntakeService(InMemoryExistingProductDeliveryStore())
    register(service, target, base, head)
    service.record_verification("spoken-english-ai", "tests", False, "one failure")
    with pytest.raises(ExistingProductIntakeError, match="already recorded"):
        service.record_verification("spoken-english-ai", "tests", True, "retry")
    for gate in REQUIRED_GATES[1:]:
        service.record_verification("spoken-english-ai", gate, True, "passed")
    with pytest.raises(ExistingProductIntakeError, match="Failed verification"):
        service.request_human_review("spoken-english-ai", "NagarajuMarri")


def test_review_evidence_waits_for_named_human_without_approval_or_merge(repository):
    service, _ = passing_service(repository)
    delivery = service.request_human_review("spoken-english-ai", "NagarajuMarri")
    assert delivery.stage is ExistingProductIntakeStage.WAITING_FOR_HUMAN_REVIEW
    assert delivery.reviewer == "NagarajuMarri"
    assert not hasattr(delivery, "approval")
    assert not hasattr(delivery, "merge_authorization")
    dashboard = service.dashboard("spoken-english-ai")
    assert dashboard.review_state is ExistingProductIntakeStage.WAITING_FOR_HUMAN_REVIEW
    assert dashboard.pending_actions == ("human review",)
    assert dashboard.progress == 80


def test_existing_pr_is_reused_and_pr_evidence_persists(repository, tmp_path):
    target, base, head = repository
    store = JsonExistingProductDeliveryStore(tmp_path / "state")
    service = ExistingProductIntakeService(store, lambda: NOW)
    delivery = register(
        service,
        target,
        base,
        head,
        existing_pr_number=7,
        existing_pr_url="https://example.invalid/pull/7",
    )
    for gate in REQUIRED_GATES:
        service.record_verification("spoken-english-ai", gate, True, "passed")
    service.request_human_review("spoken-english-ai", "NagarajuMarri")
    reused = service.attach_pull_request(
        "spoken-english-ai",
        7,
        "https://example.invalid/pull/7",
        base="main",
        head="product/milestone-7-ai-conversation-voice",
        head_sha=head,
        draft=True,
        mergeable=True,
    )
    assert reused.pull_request_number == 7
    restarted = ExistingProductIntakeService(store)
    restored = restarted.store.load("spoken-english-ai")
    assert restored is not None
    assert restored.expected_base_sha == base
    assert restored.expected_head_sha == head
    assert restored.pull_request_url == "https://example.invalid/pull/7"
    assert len(restored.verification_results) == len(REQUIRED_GATES)
    assert restarted.dashboard("spoken-english-ai").pull_request.endswith("/7")


def test_pr_creation_is_blocked_until_all_gates_pass(repository):
    target, base, head = repository
    service = ExistingProductIntakeService(InMemoryExistingProductDeliveryStore())
    register(service, target, base, head)
    with pytest.raises(ExistingProductIntakeError, match="before PR"):
        service.attach_pull_request(
            "spoken-english-ai",
            8,
            "https://example.invalid/8",
            base="main",
            head="product/milestone-7-ai-conversation-voice",
            head_sha=head,
            draft=True,
            mergeable=True,
        )
    with pytest.raises(ExistingProductIntakeError, match="missing"):
        service.request_human_review("spoken-english-ai", "NagarajuMarri")


def test_new_pr_evidence_can_be_attached_once(repository):
    service, _ = passing_service(repository)
    service.request_human_review("spoken-english-ai", "NagarajuMarri")
    service.attach_pull_request(
        "spoken-english-ai",
        8,
        "https://example.invalid/8",
        base="main",
        head="product/milestone-7-ai-conversation-voice",
        head_sha=repository[2],
        draft=True,
        mergeable=True,
    )
    with pytest.raises(ExistingProductIntakeError, match="Different"):
        service.attach_pull_request(
            "spoken-english-ai",
            9,
            "https://example.invalid/9",
            base="main",
            head="product/milestone-7-ai-conversation-voice",
            head_sha=repository[2],
            draft=True,
            mergeable=True,
        )


def test_reviewer_dashboard_contains_authoritative_evidence(repository):
    service, _ = passing_service(repository)
    service.request_human_review("spoken-english-ai", "NagarajuMarri")
    service.attach_pull_request(
        "spoken-english-ai",
        6,
        "https://example.invalid/pull/6",
        base="main",
        head="product/milestone-7-ai-conversation-voice",
        head_sha=repository[2],
        draft=True,
        mergeable=True,
    )
    dashboard = service.reviewer_dashboard("spoken-english-ai")
    assert dashboard.product_repository == "NagarajuMarri/spoken-english-ai"
    assert dashboard.commit == repository[2]
    assert dashboard.merge_base == repository[1]
    assert dashboard.pull_request_number == 6
    assert dashboard.draft is True
    assert dashboard.mergeable is True
    assert dashboard.reviewer == "NagarajuMarri"
    assert dashboard.approval_status == "NOT_APPROVED"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"base": "other"}, "refs"),
        ({"head": "other"}, "refs"),
        ({"head_sha": "other"}, "head commit"),
        ({"draft": False}, "draft and mergeable"),
        ({"mergeable": False}, "draft and mergeable"),
    ],
)
def test_pull_request_evidence_must_match_delivery(repository, changes, message):
    service, _ = passing_service(repository)
    service.request_human_review("spoken-english-ai", "NagarajuMarri")
    evidence = {
        "base": "main",
        "head": "product/milestone-7-ai-conversation-voice",
        "head_sha": repository[2],
        "draft": True,
        "mergeable": True,
    }
    evidence.update(changes)
    with pytest.raises(ExistingProductIntakeError, match=message):
        service.attach_pull_request(
            "spoken-english-ai", 6, "https://example.invalid/pull/6", **evidence
        )


def test_corrupt_restart_state_does_not_replace_valid_in_memory_delivery(
    repository, tmp_path
):
    memory = InMemoryExistingProductDeliveryStore()
    service, _ = passing_service(repository, memory)
    valid_before = service.store.load("spoken-english-ai")
    target = tmp_path / "state"
    target.mkdir()
    (target / "spoken-english-ai.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        JsonExistingProductDeliveryStore(target).load("spoken-english-ai")
    assert service.store.load("spoken-english-ai") == valid_before
