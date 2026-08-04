"""Immutable Release Management domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReleaseStatus(str, Enum):
    PLANNED = "PLANNED"
    RELEASE_CANDIDATE = "RELEASE_CANDIDATE"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    RELEASED = "RELEASED"
    ROLLED_BACK = "ROLLED_BACK"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class ReleaseKind(str, Enum):
    STABLE = "STABLE"
    HOTFIX = "HOTFIX"


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int
    release_candidate: int | None = None

    @classmethod
    def parse(cls, value: str) -> "Version":
        match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-rc\.(0|[1-9]\d*))?", value)
        if not match:
            raise ValueError("Version must use major.minor.patch or major.minor.patch-rc.N")
        major, minor, patch, candidate = match.groups()
        return cls(int(major), int(minor), int(patch),
                   int(candidate) if candidate is not None else None)

    def __str__(self) -> str:
        stable = f"{self.major}.{self.minor}.{self.patch}"
        return stable if self.release_candidate is None else f"{stable}-rc.{self.release_candidate}"


@dataclass(frozen=True)
class ReleaseCandidate:
    candidate_id: str
    version: Version
    commit_sha: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class ReleaseApproval:
    approval_id: str
    approver: str
    decision: str
    rationale: str
    timestamp: datetime


@dataclass(frozen=True)
class ReleaseNotes:
    title: str
    summary: str
    requirements: tuple[str, ...]
    milestones: tuple[str, ...]
    commits: tuple[str, ...]
    pull_requests: tuple[str, ...]
    decisions: tuple[str, ...]


@dataclass(frozen=True)
class Changelog:
    entries: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseArtifact:
    artifact_id: str
    name: str
    digest: str
    media_type: str
    uri: str


@dataclass(frozen=True)
class RollbackRecord:
    rollback_id: str
    reason: str
    initiated_by: str
    target_version: str
    timestamp: datetime


@dataclass(frozen=True)
class ReleaseDecision:
    decision_id: str
    decision: str
    rationale: str
    approver: str
    requirement_ids: tuple[str, ...]
    timestamp: datetime


@dataclass(frozen=True)
class DeploymentRecord:
    deployment_id: str
    environment: str
    status: str
    artifact_ids: tuple[str, ...]
    deployed_by: str
    timestamp: datetime


@dataclass(frozen=True)
class Release:
    release_id: str
    product_ids: tuple[str, ...]
    version: Version
    kind: ReleaseKind
    status: ReleaseStatus
    title: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    requirement_ids: tuple[str, ...] = ()
    milestone_ids: tuple[str, ...] = ()
    commit_shas: tuple[str, ...] = ()
    pull_request_urls: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    candidates: tuple[ReleaseCandidate, ...] = ()
    approvals: tuple[ReleaseApproval, ...] = ()
    notes: ReleaseNotes | None = None
    changelog: Changelog | None = None
    artifacts: tuple[ReleaseArtifact, ...] = ()
    rollbacks: tuple[RollbackRecord, ...] = ()
    decisions: tuple[ReleaseDecision, ...] = ()
    deployments: tuple[DeploymentRecord, ...] = ()
    supersedes: str | None = None
    superseded_by: str | None = None
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.release_id, self.title, self.created_by):
            if not value.strip(): raise ValueError("Release identity fields are required")
        if not self.product_ids: raise ValueError("Release requires at least one managed product")
        for timestamp in (self.created_at, self.updated_at, self.released_at):
            if timestamp is not None and (timestamp.tzinfo is None or timestamp.utcoffset() is None):
                raise ValueError("Release timestamps must be timezone aware")
        for sha in self.commit_shas:
            if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
                raise ValueError("Release commits require full hexadecimal SHAs")


@dataclass(frozen=True)
class ReleaseComparison:
    from_version: str
    to_version: str
    added_requirements: tuple[str, ...]
    removed_requirements: tuple[str, ...]
    added_commits: tuple[str, ...]
    added_pull_requests: tuple[str, ...]
    added_decisions: tuple[str, ...]
