from dataclasses import replace
from pathlib import Path
import hashlib
import subprocess

from runtime.managed_product_implementation.models import (
    CleanupPolicy,
    CommitResult,
    HumanReviewDecision,
    HumanReviewDecisionPackage,
    ImplementationState,
    ManagedProductTask,
    ProviderImplementationResult,
    PullRequestResult,
    PushResult,
    VerificationStatus,
    VerificationStep,
    VerificationStepResult,
    WorkspaceResult,
    utc_now,
)
from runtime.managed_product_implementation.persistence import (
    InMemoryManagedProductTaskStore,
    JsonManagedProductTaskStore,
)
from runtime.managed_product_implementation.pipeline import ManagedProductImplementationPipeline
from runtime.managed_product_implementation.pull_requests import InMemoryPullRequestService
from runtime.managed_product_implementation.services import (
    CommitService,
    GitPushService,
    VerificationService,
)
from runtime.managed_product_implementation.workspace import (
    DisposableWorkspaceManager,
    WorkspacePreparationError,
)


def git(path: Path, *args: str) -> str:
    result = subprocess.run(("git", *args), cwd=path, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "feature")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test")
    (source / "README.md").write_text("original\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "initial")
    return source, git(source, "rev-parse", "HEAD")


def task(repo: str = "repo", sha: str = "a" * 40) -> ManagedProductTask:
    return ManagedProductTask(
        "task-1", "project", repo, "feature", sha, "13.2", "Implement infrastructure", "fake"
    )


def test_workspace_clone_sha_remote_and_cleanup(tmp_path: Path):
    source, sha = repository(tmp_path)
    manager = DisposableWorkspaceManager(tmp_path / "workspaces", remove_remotes=True)
    result = manager.prepare(task(str(source), sha))
    assert Path(result.path).is_dir() and result.commit_sha == sha
    assert git(Path(result.path), "remote") == ""
    assert (source / "README.md").read_text(encoding="utf-8") == "original\n"
    manager.cleanup(result)
    assert not Path(result.path).exists()


def test_workspace_rejects_wrong_sha(tmp_path: Path):
    source, _ = repository(tmp_path)
    manager = DisposableWorkspaceManager(tmp_path / "workspaces")
    try:
        manager.prepare(task(str(source), "0" * 40))
    except WorkspacePreparationError:
        pass
    else:
        raise AssertionError("wrong SHA accepted")


def test_task_rejects_workspace_path_traversal():
    try:
        replace(task(), project_id="../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("workspace traversal accepted")


def test_verification_stops_on_first_failure(tmp_path: Path):
    steps = (
        VerificationStep("pass", ("python", "-c", "print('ok')")),
        VerificationStep("fail", ("python", "-c", "raise SystemExit(2)")),
        VerificationStep("never", ("python", "-c", "print('bad')")),
    )
    results = VerificationService().run(tmp_path, steps)
    assert [x.name for x in results] == ["pass", "fail"]
    assert results[-1].status is VerificationStatus.FAIL


def test_verification_redacts_and_rejects_unapproved_executable(tmp_path: Path):
    result = VerificationService(redacted_values=("sensitive-value",)).run(
        tmp_path,
        (
            VerificationStep(
                "redact",
                ("python", "-c", "print('sensitive-value')"),
            ),
            VerificationStep("blocked", ("custom-script",)),
        ),
    )
    assert "sensitive-value" not in result[0].output
    assert result[1].status is VerificationStatus.FAIL


def test_commit_records_sha_and_validates_paths(tmp_path: Path):
    source, _ = repository(tmp_path)
    (source / "README.md").write_text("changed\n", encoding="utf-8")
    result = CommitService().commit(source, ("README.md",), "13.2")
    assert result.commit_sha == git(source, "rev-parse", "HEAD")
    try:
        CommitService().commit(source, ("../escape",), "13.2")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe path accepted")


def test_push_validations(tmp_path: Path):
    source, _ = repository(tmp_path)
    service = GitPushService()
    assert service.push(source, "main").error_code == "PROTECTED_BRANCH"
    assert service.push(source, "feature").error_code == "REMOTE_MISSING"


def test_commit_rejects_protected_branch(tmp_path: Path):
    source, _ = repository(tmp_path)
    git(source, "branch", "-m", "main")
    (source / "README.md").write_text("changed\n", encoding="utf-8")
    try:
        CommitService().commit(source, ("README.md",), "13.2")
    except ValueError:
        pass
    else:
        raise AssertionError("protected branch commit accepted")


class WorkspaceFake:
    def __init__(self, path: Path):
        self.path, self.cleaned = path, False

    def prepare(self, value):
        return WorkspaceResult(
            value.task_id,
            str(self.path),
            value.repository,
            value.branch,
            value.expected_commit_sha,
            False,
            utc_now(),
        )

    def cleanup(self, value):
        self.cleaned = True


class ProviderFake:
    provider_id = "fake"

    def implement(self, value, workspace):
        return ProviderImplementationResult(
            "exec-1", "Implemented", ("README.md",), ("Review risk",), ("Human review",)
        )


class VerificationFake:
    fail = False

    def run(self, workspace, steps):
        status = VerificationStatus.FAIL if self.fail else VerificationStatus.PASS
        return (
            VerificationStepResult(
                "pytest",
                status,
                ("pytest",),
                1 if self.fail else 0,
                "report",
                utc_now(),
                utc_now(),
                "a" * 40,
                hashlib.sha256(b"").hexdigest(),
            ),
        )


class CommitFake:
    def commit(self, workspace, paths, milestone, *, approved_paths=()):
        return CommitResult("b" * 40, "Implement 13.2", paths)


class PushFake:
    def push(self, workspace, branch, remote="origin", **kwargs):
        return PushResult(
            True,
            branch,
            remote,
            f"origin/{branch}",
            remote_head_sha=kwargs.get("expected_commit_sha"),
        )


def pipeline(tmp_path: Path, store=None, verification=None, prs=None):
    return ManagedProductImplementationPipeline(
        store or InMemoryManagedProductTaskStore(),
        WorkspaceFake(tmp_path),
        ProviderFake(),
        verification or VerificationFake(),
        CommitFake(),
        PushFake(),
        prs or InMemoryPullRequestService(),
        (VerificationStep("pytest", ("pytest",)),),
        CleanupPolicy.KEEP,
    )


def test_pipeline_persists_and_stops_for_human_review(tmp_path: Path):
    store = InMemoryManagedProductTaskStore()
    service = pipeline(tmp_path, store)
    service.request(task())
    result = service.run("task-1")
    assert result.state is ImplementationState.WAITING_FOR_HUMAN_REVIEW
    assert result.review_status == "WAITING_FOR_HUMAN_REVIEW"
    assert result.pull_request_id == 1 and result.review_package is not None
    assert service.run("task-1") == result


def test_completion_requires_explicit_human_and_is_immutable(tmp_path: Path):
    store = InMemoryManagedProductTaskStore()
    service = pipeline(tmp_path, store)
    service.request(task())
    service.run("task-1")
    completed = service.record_human_approval("task-1", "reviewer")
    assert completed.state is ImplementationState.COMPLETED
    try:
        store.save(replace(completed, failure="mutation"))
    except ValueError:
        pass
    else:
        raise AssertionError("completed task was mutable")


def test_verification_failure_recovery_and_resume(tmp_path: Path):
    verify = VerificationFake()
    verify.fail = True
    store = InMemoryManagedProductTaskStore()
    service = pipeline(tmp_path, store, verify)
    service.request(task())
    failed = service.run("task-1")
    assert failed.state is ImplementationState.VERIFICATION_FAILED
    verify.fail = False
    service.recover("task-1")
    assert service.run("task-1").state is ImplementationState.WAITING_FOR_HUMAN_REVIEW


def test_json_resume_information_round_trip(tmp_path: Path):
    store = JsonManagedProductTaskStore(tmp_path / "state")
    value = replace(
        task(), state=ImplementationState.VERIFYING, resume_from=ImplementationState.VERIFYING
    )
    store.save(value)
    loaded = store.load("task-1")
    assert loaded is not None and loaded.resume_from is ImplementationState.VERIFYING


def test_draft_pr_create_update_attaches_evidence():
    service = InMemoryPullRequestService()
    value = replace(task(), commit_sha="a" * 40)
    review = __import__(
        "runtime.managed_product_implementation.models", fromlist=["ReviewPackage"]
    ).ReviewPackage("s", (), "t", ("x",), "a" * 40, "pending", (), ())
    created = service.create_draft(value, review)
    updated = service.update_draft(created.number, review)
    assert created.draft and dict(updated.metadata)["evidence"] == "updated"


def test_task_identity_and_scope_are_immutable():
    store = InMemoryManagedProductTaskStore()
    value = task()
    store.save(value)
    try:
        store.save(replace(value, repository="different"))
    except ValueError:
        pass
    else:
        raise AssertionError("task identity changed")


def test_required_unknown_blocks_commit(tmp_path: Path):
    class UnknownVerification(VerificationFake):
        def run(self, workspace, steps):
            return (
                VerificationStepResult(
                    "pytest",
                    VerificationStatus.UNKNOWN,
                    ("pytest",),
                    None,
                    "unknown",
                    utc_now(),
                    utc_now(),
                    "a" * 40,
                    hashlib.sha256(b"").hexdigest(),
                ),
            )

    store = InMemoryManagedProductTaskStore()
    service = pipeline(tmp_path, store, UnknownVerification())
    service.request(task())
    assert service.run("task-1").state is ImplementationState.VERIFICATION_FAILED


def test_provider_cannot_escape_approved_scope(tmp_path: Path):
    store = InMemoryManagedProductTaskStore()
    service = pipeline(tmp_path, store)
    service.request(replace(task(), allowed_paths=("src",)))
    assert service.run("task-1").state is ImplementationState.PROVIDER_FAILED


def test_human_gate_rejects_self_approval(tmp_path: Path):
    store = InMemoryManagedProductTaskStore()
    service = pipeline(tmp_path, store)
    service.request(replace(task(), implementation_actor="reviewer"))
    service.run("task-1")
    try:
        service.record_human_approval("task-1", "reviewer")
    except ValueError:
        pass
    else:
        raise AssertionError("self approval accepted")


def test_duplicate_draft_pr_is_rejected():
    service = InMemoryPullRequestService()
    value = replace(task(), commit_sha="a" * 40)
    review = __import__(
        "runtime.managed_product_implementation.models", fromlist=["ReviewPackage"]
    ).ReviewPackage("s", (), "t", ("x",), "a" * 40, "pending", (), ())
    service.create_draft(value, review)
    try:
        service.create_draft(value, review)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate draft PR created")


def test_human_review_decision_package_cannot_record_approval():
    package = HumanReviewDecisionPackage(
        "spoken-english-m7-review-v1",
        "Spoken English AI",
        "Product Milestone 7",
        "a" * 40,
        "b" * 40,
        59,
        1586,
        0,
        ("Provider-neutral voice tutor",),
        ("107 tests passed",),
        ("No live provider invoked",),
        ("Synthetic pronunciation only",),
        ("Review architecture and evidence",),
        tuple(HumanReviewDecision),
        ImplementationState.WAITING_FOR_HUMAN_REVIEW,
        "NagarajuMarri",
        False,
    )
    assert package.available_decisions[-1] is HumanReviewDecision.REJECT
