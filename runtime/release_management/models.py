"""Immutable Release Management domain objects."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
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

    def precedence(self) -> tuple[int, int, int, int, int]:
        stable = 1 if self.release_candidate is None else 0
        return (self.major, self.minor, self.patch, stable, self.release_candidate or 0)

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version): return NotImplemented
        return self.precedence() < other.precedence()


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
    evidence_digest: str = ""


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
class ReleaseReadiness:
    ready: bool
    blockers: tuple[str, ...]
    accepted_capability_ids: tuple[str, ...]
    acceptance_run_ids: tuple[str, ...]


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
    locked_capability_ids: tuple[str, ...] = ()
    runtime_acceptance_run_ids: tuple[str, ...] = ()
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
        timestamps = [self.created_at,self.updated_at,self.released_at]
        timestamps += [item.created_at for item in self.candidates]
        timestamps += [item.timestamp for item in self.approvals+self.rollbacks+self.decisions+self.deployments]
        for timestamp in timestamps:
            if timestamp is not None:
                offset=timestamp.utcoffset()
                if timestamp.tzinfo is None or offset is None or offset.total_seconds()!=0:
                    raise ValueError("Release timestamps must use UTC")
        for approval in self.approvals:
            if not approval.approver.strip() or not approval.rationale.strip(): raise ValueError("Approval identity and rationale are required")
            if approval.decision not in {"APPROVE","REJECT","REQUEST_CHANGES"}: raise ValueError("Unknown approval decision")
        for rollback in self.rollbacks:
            if not rollback.reason.strip() or not rollback.initiated_by.strip() or not rollback.target_version.strip():
                raise ValueError("Rollback reason, actor, and previous release are required")
        for sha in self.commit_shas:
            if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
                raise ValueError("Release commits require full hexadecimal SHAs")
        for values, label in (
            (self.locked_capability_ids, "locked capability IDs"),
            (self.runtime_acceptance_run_ids, "runtime acceptance run IDs"),
        ):
            if len(values) != len(set(values)) or any(not item.strip() for item in values):
                raise ValueError(f"{label} must be unique and non-empty")


@dataclass(frozen=True)
class ReleaseComparison:
    from_version: str
    to_version: str
    added_requirements: tuple[str, ...]
    removed_requirements: tuple[str, ...]
    added_commits: tuple[str, ...]
    added_pull_requests: tuple[str, ...]
    added_decisions: tuple[str, ...]
