import pytest

from runtime.integrations.github import (
    CIStatus, CreatePullRequestRequest, GitHubRepository,
    InMemoryGitHubProvider, PullRequestState,
)
from runtime.integrations.github.exceptions import PullRequestNotMergeableError
from runtime.integrations.github.exceptions import PullRequestConflictError


def configured():
    provider = InMemoryGitHubProvider()
    provider.register_repository(GitHubRepository("org/repo"))
    provider.create_branch("org/repo", "main", "a" * 40)
    provider.create_branch("org/repo", "agent/task", "b" * 40)
    return provider


def test_draft_pr_update_ready_comments_and_ci():
    provider = configured()
    pr = provider.create_draft_pull_request(CreatePullRequestRequest(
        "org/repo", "Title", "Body", "main", "agent/task"
    ))
    pr = provider.update_pull_request("org/repo", pr.number, body="Updated")
    provider.add_comment("org/repo", pr.number, "Review")
    pr = provider.mark_ready_for_review("org/repo", pr.number)
    pr = provider.set_ci_status("org/repo", pr.number, CIStatus.SUCCESS)
    assert not pr.draft and pr.body == "Updated"
    assert provider.list_issue_comments("org/repo", pr.number) == ("Review",)


def test_merge_requires_explicit_approval_ready_and_ci():
    provider = configured()
    pr = provider.create_draft_pull_request(CreatePullRequestRequest(
        "org/repo", "Title", "Body", "main", "agent/task"
    ))
    with pytest.raises(PullRequestNotMergeableError):
        provider.merge_pull_request("org/repo", pr.number, approved=False)
    provider.mark_ready_for_review("org/repo", pr.number)
    provider.set_ci_status("org/repo", pr.number, CIStatus.SUCCESS)
    assert provider.merge_pull_request(
        "org/repo", pr.number, approved=True
    ).state == PullRequestState.MERGED


def test_duplicate_open_head_pull_request_is_rejected():
    provider = configured()
    request = CreatePullRequestRequest(
        "org/repo", "Title", "Body", "main", "agent/task"
    )
    provider.create_draft_pull_request(request)
    with pytest.raises(PullRequestConflictError):
        provider.create_draft_pull_request(request)
