from dataclasses import replace
from pathlib import Path
import subprocess

from runtime.managed_product_implementation.models import (
    CleanupPolicy,
    CommitResult,
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


def test_verification_stops_on_first_failure(tmp_path: Path):
    steps = (
        VerificationStep("pass", ("python", "-c", "print('ok')")),
        VerificationStep("fail", ("python", "-c", "raise SystemExit(2)")),
        VerificationStep("never", ("python", "-c", "print('bad')")),
    )
    results = VerificationService().run(tmp_path, steps)
    assert [x.name for x in results] == ["pass", "fail"]
    assert results[-1].status is VerificationStatus.FAIL


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
                "pytest", status, ("pytest",), 1 if self.fail else 0, "report", utc_now(), utc_now()
            ),
        )


class CommitFake:
    def commit(self, workspace, paths, milestone):
        return CommitResult("b" * 40, "Implement 13.2", paths)


class PushFake:
    def push(self, workspace, branch, remote="origin"):
        return PushResult(True, branch, remote, f"origin/{branch}")


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
    value = task()
    review = __import__(
        "runtime.managed_product_implementation.models", fromlist=["ReviewPackage"]
    ).ReviewPackage("s", (), "t", ("x",), "a", "pending", (), ())
    created = service.create_draft(value, review)
    updated = service.update_draft(created.number, review)
    assert created.draft and dict(updated.metadata)["evidence"] == "updated"
