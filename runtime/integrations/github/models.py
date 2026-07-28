from dataclasses import dataclass, replace
from enum import Enum


class PullRequestState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"


class CIStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


@dataclass(frozen=True)
class GitHubRepository:
    reference: str
    default_branch: str = "main"


@dataclass(frozen=True)
class GitHubBranch:
    repository: str
    name: str
    commit_sha: str


@dataclass(frozen=True)
class PullRequest:
    repository: str
    number: int
    title: str
    body: str
    base_branch: str
    head_branch: str
    draft: bool
    state: PullRequestState = PullRequestState.OPEN
    mergeable: bool = True
    ci_status: CIStatus = CIStatus.PENDING


@dataclass(frozen=True)
class CreatePullRequestRequest:
    repository: str
    title: str
    body: str
    base_branch: str
    head_branch: str
    draft: bool = True
