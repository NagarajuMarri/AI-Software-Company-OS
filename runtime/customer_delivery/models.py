"""Immutable Completion Module 4 review and draft-delivery records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
from pathlib import Path
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_BRANCH = re.compile(
    r"^(?![-/.])(?!.*(?:\.\.|//|@\{|[~^:?*\[\\]))"
    r"(?!.*(?:/\.|\.lock(?:/|$)))[A-Za-z0-9._/-]{1,200}(?<![/.])$"
)


class CustomerDeliveryStatus(str, Enum):
    AWAITING_REVIEW = "AWAITING_REVIEW"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    DELIVERY_IN_PROGRESS = "DELIVERY_IN_PROGRESS"
    DRAFT_PR_CREATED = "DRAFT_PR_CREATED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class CustomerDeliveryConfiguration:
    """Operator-owned repository policy; browser forms cannot populate it."""

    workspace_root: Path
    repository_full_name: str
    base_branch: str
    remote_name: str = "origin"
    enabled: bool = False
    product_write_confirmed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_root, Path):
            raise ValueError("Delivery workspace must be a Path")
        if not _REPOSITORY.fullmatch(self.repository_full_name):
            raise ValueError("Delivery repository must use owner/name form")
        if not _BRANCH.fullmatch(self.base_branch):
            raise ValueError("Delivery base branch is invalid")
        if not _REMOTE.fullmatch(self.remote_name):
            raise ValueError("Delivery remote name is invalid")
        if self.product_write_confirmed and not self.enabled:
            raise ValueError("Repository-write confirmation requires enabled delivery")


@dataclass(frozen=True)
class ReviewedFile:
    path: str
    content_digest: str

    def __post_init__(self) -> None:
        _path(self.path)
        _digest(self.content_digest, "reviewed file digest")


@dataclass(frozen=True)
class CustomerDeliveryReview:
    delivery_id: str
    customer_id: str
    request_id: str
    product_id: str
    execution_plan_id: str
    execution_plan_digest: str
    execution_scope_digest: str
    provider_operation_id: str
    provider_task_id: str
    patch_manifest_digest: str
    git_diff_digest: str
    workspace_id: str
    workspace_branch: str
    workspace_commit_before_turn: str
    repository_full_name: str
    base_branch: str
    reviewed_files: tuple[ReviewedFile, ...]
    additions: int
    deletions: int
    commit_message: str
    pull_request_title: str
    pull_request_body: str
    pull_request_body_digest: str
    created_at: datetime
    updated_at: datetime
    status: CustomerDeliveryStatus = CustomerDeliveryStatus.AWAITING_REVIEW
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    commit_sha: str | None = None
    tree_sha: str | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    failure_classification: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.delivery_id, "delivery ID"),
            (self.customer_id, "delivery customer ID"),
            (self.request_id, "delivery request ID"),
            (self.product_id, "delivery product ID"),
            (self.execution_plan_id, "execution plan ID"),
            (self.provider_operation_id, "provider operation ID"),
            (self.provider_task_id, "provider task ID"),
            (self.workspace_id, "delivery workspace ID"),
        ):
            _id(value, label)
        for value, label in (
            (self.execution_plan_digest, "execution plan digest"),
            (self.execution_scope_digest, "execution scope digest"),
            (self.patch_manifest_digest, "patch manifest digest"),
            (self.git_diff_digest, "Git diff digest"),
            (self.pull_request_body_digest, "pull-request body digest"),
        ):
            _digest(value, label)
        if not _BRANCH.fullmatch(self.workspace_branch) or not self.workspace_branch.startswith(
            "agent/"
        ):
            raise ValueError("Delivery head must be an agent/* branch")
        if not _COMMIT.fullmatch(self.workspace_commit_before_turn):
            raise ValueError("Delivery base commit is invalid")
        if not _REPOSITORY.fullmatch(self.repository_full_name):
            raise ValueError("Delivery repository is invalid")
        if not _BRANCH.fullmatch(self.base_branch) or self.base_branch == self.workspace_branch:
            raise ValueError("Delivery base/head branches are invalid")
        if (
            not self.reviewed_files
            or len(self.reviewed_files) > 100
            or len({item.path for item in self.reviewed_files}) != len(self.reviewed_files)
        ):
            raise ValueError("Reviewed files are invalid")
        for count, label in ((self.additions, "additions"), (self.deletions, "deletions")):
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(f"Delivery {label} are invalid")
        _text(self.commit_message, "delivery commit message", 300)
        _text(self.pull_request_title, "delivery pull-request title", 300)
        _text(self.pull_request_body, "delivery pull-request body", 10_000)
        if text_digest(self.pull_request_body) != self.pull_request_body_digest:
            raise ValueError("Delivery pull-request body digest is invalid")
        _utc(self.created_at, "delivery creation time")
        _utc(self.updated_at, "delivery update time")
        if self.updated_at < self.created_at:
            raise ValueError("Delivery time regressed")
        if not isinstance(self.status, CustomerDeliveryStatus):
            raise ValueError("Delivery status is invalid")
        if self.reviewed_at is not None:
            _utc(self.reviewed_at, "delivery review time")
        if (self.reviewed_at is None) != (self.reviewed_by is None):
            raise ValueError("Delivery review identity is incomplete")
        if self.reviewed_by is not None:
            _id(self.reviewed_by, "delivery reviewer")
        for optional_commit, label in (
            (self.commit_sha, "delivery commit"),
            (self.tree_sha, "delivery tree"),
        ):
            if optional_commit is not None and not _COMMIT.fullmatch(optional_commit):
                raise ValueError(f"{label} is invalid")
        if self.pull_request_number is not None and (
            not isinstance(self.pull_request_number, int)
            or isinstance(self.pull_request_number, bool)
            or self.pull_request_number < 1
        ):
            raise ValueError("Delivery pull-request number is invalid")
        if self.pull_request_url is not None:
            _text(self.pull_request_url, "delivery pull-request URL", 1_000)
            if not self.pull_request_url.startswith("https://github.com/"):
                raise ValueError("Delivery pull-request URL is invalid")
        if (self.pull_request_number is None) != (self.pull_request_url is None):
            raise ValueError("Delivery pull-request identity is incomplete")
        if self.failure_classification is not None:
            _text(self.failure_classification, "delivery failure classification", 200)
        if self.status is CustomerDeliveryStatus.AWAITING_REVIEW and self.reviewed_at is not None:
            raise ValueError("Awaiting delivery review cannot be approved")
        if self.status in {
            CustomerDeliveryStatus.REVIEW_APPROVED,
            CustomerDeliveryStatus.DELIVERY_IN_PROGRESS,
            CustomerDeliveryStatus.DRAFT_PR_CREATED,
        } and self.reviewed_at is None:
            raise ValueError("Delivery transition requires exact human review")
        delivery_receipt = (
            self.commit_sha,
            self.tree_sha,
            self.pull_request_number,
            self.pull_request_url,
        )
        if self.status is CustomerDeliveryStatus.DRAFT_PR_CREATED:
            if any(value is None for value in delivery_receipt):
                raise ValueError("Draft delivery receipt is incomplete")
        elif any(value is not None for value in delivery_receipt):
            raise ValueError("Repository receipt exists before draft delivery")
        if (
            self.status is CustomerDeliveryStatus.RECONCILIATION_REQUIRED
        ) != (self.failure_classification is not None):
            raise ValueError("Delivery reconciliation classification is invalid")

    @property
    def review_digest(self) -> str:
        return _hash(
            {
                "delivery_id": self.delivery_id,
                "customer_id": self.customer_id,
                "request_id": self.request_id,
                "product_id": self.product_id,
                "execution_plan_id": self.execution_plan_id,
                "execution_plan_digest": self.execution_plan_digest,
                "execution_scope_digest": self.execution_scope_digest,
                "provider_operation_id": self.provider_operation_id,
                "provider_task_id": self.provider_task_id,
                "patch_manifest_digest": self.patch_manifest_digest,
                "git_diff_digest": self.git_diff_digest,
                "workspace_id": self.workspace_id,
                "workspace_branch": self.workspace_branch,
                "workspace_commit_before_turn": self.workspace_commit_before_turn,
                "repository_full_name": self.repository_full_name,
                "base_branch": self.base_branch,
                "reviewed_files": tuple(asdict(item) for item in self.reviewed_files),
                "additions": self.additions,
                "deletions": self.deletions,
                "commit_message": self.commit_message,
                "pull_request_title": self.pull_request_title,
                "pull_request_body": self.pull_request_body,
                "pull_request_body_digest": self.pull_request_body_digest,
            }
        )

    @property
    def digest(self) -> str:
        return _hash(asdict(self))


def delivery_id_for(request_id: str) -> str:
    _id(request_id, "delivery request ID")
    value = hashlib.sha256(f"customer-delivery:{request_id}".encode()).hexdigest()
    return f"customer-delivery-{value[:24]}"


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json).encode("utf-8")
    ).hexdigest()


def _json(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Cannot encode {type(value).__name__}")


def _id(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
    ):
        raise ValueError(f"{label} is invalid")


def _path(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or len(value) > 500
    ):
        raise ValueError("Reviewed file path is invalid")


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")
