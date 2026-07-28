"""Deterministic GitHub contract implementation for tests."""

from dataclasses import replace

from runtime.integrations.github.exceptions import (
    BranchNotFoundError,
    PullRequestConflictError,
    PullRequestNotMergeableError,
    RepositoryNotFoundError,
)
from runtime.integrations.github.models import (
    CIStatus,
    GitHubBranch,
    GitHubRepository,
    PullRequest,
    PullRequestState,
)


class InMemoryGitHubProvider:
    def __init__(self):
        self._repositories = {}
        self._branches = {}
        self._pull_requests = {}
        self._comments = {}

    def register_repository(self, repository: GitHubRepository):
        self._repositories[repository.reference] = repository
        return repository

    def create_branch(self, repository, name, commit_sha):
        self.get_repository(repository)
        branch = GitHubBranch(repository, name, commit_sha)
        self._branches[(repository, name)] = branch
        return branch

    def get_repository(self, reference):
        try:
            return self._repositories[reference]
        except KeyError as error:
            raise RepositoryNotFoundError(reference) from error

    def get_branch(self, repository, branch):
        try:
            return self._branches[(repository, branch)]
        except KeyError as error:
            raise BranchNotFoundError(branch) from error

    def get_commit(self, repository, sha):
        self.get_repository(repository)
        if not any(
            branch.repository == repository and branch.commit_sha == sha
            for branch in self._branches.values()
        ):
            raise BranchNotFoundError(sha)
        return sha

    def list_pull_requests(self, repository):
        self.get_repository(repository)
        return tuple(
            item for (repo, _), item in self._pull_requests.items()
            if repo == repository
        )

    def get_pull_request(self, repository, number):
        try:
            return self._pull_requests[(repository, number)]
        except KeyError as error:
            raise PullRequestConflictError("Pull request not found") from error

    def create_draft_pull_request(self, request):
        self.get_branch(request.repository, request.base_branch)
        self.get_branch(request.repository, request.head_branch)
        if any(
            item.state == PullRequestState.OPEN
            and item.head_branch == request.head_branch
            for item in self.list_pull_requests(request.repository)
        ):
            raise PullRequestConflictError("Open pull request already exists")
        number = len(self.list_pull_requests(request.repository)) + 1
        pull_request = PullRequest(
            request.repository, number, request.title, request.body,
            request.base_branch, request.head_branch, True,
        )
        self._pull_requests[(request.repository, number)] = pull_request
        return pull_request

    def update_pull_request(self, repository, number, *, title=None, body=None):
        current = self.get_pull_request(repository, number)
        updated = replace(
            current,
            title=current.title if title is None else title,
            body=current.body if body is None else body,
        )
        self._pull_requests[(repository, number)] = updated
        return updated

    def mark_ready_for_review(self, repository, number):
        current = self.get_pull_request(repository, number)
        updated = replace(current, draft=False)
        self._pull_requests[(repository, number)] = updated
        return updated

    def set_ci_status(self, repository, number, status: CIStatus):
        current = self.get_pull_request(repository, number)
        updated = replace(current, ci_status=status)
        self._pull_requests[(repository, number)] = updated
        return updated

    def get_ci_status(self, repository, number):
        return self.get_pull_request(repository, number).ci_status

    def add_comment(self, repository, number, body):
        self.get_pull_request(repository, number)
        self._comments.setdefault((repository, number), []).append(str(body))

    def list_issue_comments(self, repository, number):
        return tuple(self._comments.get((repository, number), ()))

    def merge_pull_request(self, repository, number, *, approved: bool):
        current = self.get_pull_request(repository, number)
        if (
            not approved
            or current.draft
            or current.ci_status != CIStatus.SUCCESS
            or not current.mergeable
        ):
            raise PullRequestNotMergeableError(
                "Explicit approval, ready state, and successful CI are required"
            )
        merged = replace(current, state=PullRequestState.MERGED)
        self._pull_requests[(repository, number)] = merged
        return merged
