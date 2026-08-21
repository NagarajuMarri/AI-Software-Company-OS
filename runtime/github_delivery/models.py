"""Closed exact-review-bound models for ASCOS Day 33 GitHub delivery."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import PurePosixPath
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_BRANCH = re.compile(r"^(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_REPOSITORY = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?$"
)
_FULL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")

VERIFY_REVIEWED_DELIVERY = "VERIFY_REVIEWED_DELIVERY"
STAGE_REVIEWED_FILES = "STAGE_REVIEWED_FILES"
CREATE_REVIEWED_COMMIT = "CREATE_REVIEWED_COMMIT"
PUSH_FEATURE_BRANCH = "PUSH_FEATURE_BRANCH"
OPEN_DRAFT_PULL_REQUEST = "OPEN_DRAFT_PULL_REQUEST"
REPORT_DELIVERY_STATUS = "REPORT_DELIVERY_STATUS"

GITHUB_DELIVERY_ACTIONS = (
    VERIFY_REVIEWED_DELIVERY,
    STAGE_REVIEWED_FILES,
    CREATE_REVIEWED_COMMIT,
    PUSH_FEATURE_BRANCH,
    OPEN_DRAFT_PULL_REQUEST,
    REPORT_DELIVERY_STATUS,
)
GITHUB_DELIVERY_CAPABILITIES = (
    "exact-day32-review-binding",
    "reviewed-path-only-staging",
    "single-parent-reviewed-commit",
    "non-force-feature-branch-push",
    "draft-pull-request-creation",
    "delivery-status-reporting",
)
GITHUB_DELIVERY_TOOL_IDS = (
    "CONTROLLED_LOCAL_GIT_DELIVERY",
    "SCOPED_GITHUB_DRAFT_PR",
)

WORK_ORDER_STATUS = "AUTHORIZED_CONTROLLED_GITHUB_DELIVERY"
ARTIFACT_STATUS = "DRAFT_PULL_REQUEST_OPEN_AWAITING_HUMAN_REVIEW"
SOURCE_STATE = "CLEAN_AND_UNCHANGED"
WORKSPACE_STATE = "CLEAN_COMMITTED_AND_PUSHED"
BRANCH_STATE = "FEATURE_BRANCH_PUSHED_AT_EXACT_REVIEWED_COMMIT"
PULL_REQUEST_STATE = "OPEN_DRAFT_UNMERGED"
DELIVERY_STATE = "DRAFT_PR_OPEN"
PILOT_STATUS = "NOT_SELECTED"


@dataclass(frozen=True)
class ReviewedFileBinding:
    path: str
    owner_role: str
    content_digest: str

    def __post_init__(self) -> None:
        _path(self.path, "reviewed file path")
        _identifier(self.owner_role, "reviewed file owner")
        _digest(self.content_digest, "reviewed file digest")


@dataclass(frozen=True)
class GitHubDeliveryWorkOrder:
    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    coding_review_artifact_digest: str
    workspace_artifact_digest: str
    repository_id: str
    repository_identity: str
    repository_full_name: str
    workspace_id: str
    base_branch: str
    base_commit: str
    base_tree: str
    feature_branch: str
    reviewed_files: tuple[ReviewedFileBinding, ...]
    final_diff_digest: str
    commit_message: str
    pull_request_title: str
    pull_request_body: str
    objectives: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = WORK_ORDER_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.assignment_id, "assignment"),
            (self.repository_id, "repository"),
            (self.workspace_id, "workspace"),
        ):
            _identifier(value, f"GitHub-delivery {label} ID")
        _digest(self.coding_review_artifact_digest, "coding-review artifact digest")
        _digest(self.workspace_artifact_digest, "workspace artifact digest")
        _digest(self.final_diff_digest, "reviewed diff digest")
        if repository_full_name_for(self.repository_identity) != self.repository_full_name:
            raise ValueError("GitHub repository identity and full name do not match")
        _branch(self.base_branch, "base branch", protected_allowed=True)
        _branch(self.feature_branch, "feature branch", protected_allowed=False)
        if not self.feature_branch.startswith("agent/") or self.feature_branch == self.base_branch:
            raise ValueError("GitHub delivery feature branch is invalid")
        _commit(self.base_commit, "base commit")
        _commit(self.base_tree, "base tree")
        _typed(self.reviewed_files, ReviewedFileBinding, "reviewed files", 1, 32)
        paths = tuple(item.path for item in self.reviewed_files)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("Reviewed file bindings must be unique and sorted")
        _single_line(self.commit_message, "commit message", 200)
        _single_line(self.pull_request_title, "pull-request title", 200)
        _text(self.pull_request_body, "pull-request body", 12_000)
        _items(self.objectives, "delivery objectives", 4, 10, 400)
        _items(self.acceptance_checks, "delivery acceptance checks", 8, 18, 400)
        _items(self.constraints, "delivery constraints", 8, 18, 400)
        _utc(self.issued_at, "delivery work-order issue time")
        if self.status != WORK_ORDER_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("GitHub delivery work-order state is invalid")

    @property
    def reviewed_paths(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.reviewed_files)

    @property
    def pull_request_body_digest(self) -> str:
        return hashlib.sha256(self.pull_request_body.encode("utf-8")).hexdigest()

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class GitHubDeliveryAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    work_order_digest: str
    coding_review_artifact_digest: str
    repository_id: str
    workspace_id: str
    base_branch: str
    feature_branch: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_reviewed_paths: int = 32
    max_git_commands: int = 64
    max_controlled_network_calls: int = 8
    repository_write_allowed: bool = True
    controlled_network_allowed: bool = True
    scoped_credential_handle_allowed: bool = True
    commit_allowed: bool = True
    push_allowed: bool = True
    pull_request_allowed: bool = True
    draft_only: bool = True
    force_push_allowed: bool = False
    merge_allowed: bool = False
    deployment_allowed: bool = False
    release_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
            (self.repository_id, "repository"),
            (self.workspace_id, "workspace"),
        ):
            _identifier(value, f"GitHub-delivery {label} ID")
        _digest(self.work_order_digest, "authority work-order digest")
        _digest(self.coding_review_artifact_digest, "authority coding-review digest")
        _branch(self.base_branch, "authority base branch", protected_allowed=True)
        _branch(self.feature_branch, "authority feature branch", protected_allowed=False)
        if self.allowed_action_ids != GITHUB_DELIVERY_ACTIONS:
            raise ValueError("GitHub delivery authority action profile is invalid")
        if self.allowed_tool_ids != GITHUB_DELIVERY_TOOL_IDS:
            raise ValueError("GitHub delivery authority tool profile is invalid")
        _utc(self.issued_at, "delivery authority issue time")
        _utc(self.expires_at, "delivery authority expiry time")
        if self.expires_at <= self.issued_at or self.expires_at - self.issued_at > timedelta(hours=24):
            raise ValueError("GitHub delivery authority expiry is invalid")
        if not 1 <= self.max_reviewed_paths <= 32:
            raise ValueError("GitHub delivery reviewed-path budget is invalid")
        if not 12 <= self.max_git_commands <= 96:
            raise ValueError("GitHub delivery Git-command budget is invalid")
        if not 3 <= self.max_controlled_network_calls <= 12:
            raise ValueError("GitHub delivery network budget is invalid")
        if not (
            self.repository_write_allowed
            and self.controlled_network_allowed
            and self.scoped_credential_handle_allowed
            and self.commit_allowed
            and self.push_allowed
            and self.pull_request_allowed
            and self.draft_only
        ):
            raise ValueError("GitHub delivery authority is incomplete")
        if self.force_push_allowed or self.merge_allowed or self.deployment_allowed or self.release_allowed:
            raise ValueError("GitHub delivery authority exceeds Day 33")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class DraftPullRequestReceipt:
    number: int
    url: str
    repository_full_name: str
    base_branch: str
    head_branch: str
    base_commit: str
    head_commit: str
    title: str
    body_digest: str
    draft: bool = True
    state: str = "OPEN"
    merged: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.number, int) or isinstance(self.number, bool) or self.number < 1:
            raise ValueError("Draft pull-request number is invalid")
        if not _FULL_NAME.fullmatch(self.repository_full_name):
            raise ValueError("Draft pull-request repository is invalid")
        expected_prefix = f"https://github.com/{self.repository_full_name}/pull/"
        if self.url != f"{expected_prefix}{self.number}":
            raise ValueError("Draft pull-request URL is invalid")
        _branch(self.base_branch, "pull-request base branch", protected_allowed=True)
        _branch(self.head_branch, "pull-request head branch", protected_allowed=False)
        _commit(self.base_commit, "pull-request base commit")
        _commit(self.head_commit, "pull-request head commit")
        _single_line(self.title, "pull-request title", 200)
        _digest(self.body_digest, "pull-request body digest")
        if not self.draft or self.state != "OPEN" or self.merged:
            raise ValueError("Pull request must remain open, draft, and unmerged")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class GitHubDeliveryObservation:
    provider_id: str
    staged_paths: tuple[str, ...]
    committed_paths: tuple[str, ...]
    commit_parent: str
    commit_sha: str
    commit_tree: str
    remote_branch_sha: str
    pull_request: DraftPullRequestReceipt
    git_command_count: int
    controlled_network_call_count: int
    credential_handle_count: int = 0
    secret_value_exposure_count: int = 0
    unapproved_network_call_count: int = 0
    unrelated_path_count: int = 0
    general_command_count: int = 0
    force_push_count: int = 0
    commit_count: int = 1
    push_count: int = 1
    pull_request_count: int = 1
    merge_count: int = 0
    deployment_count: int = 0
    release_count: int = 0

    def __post_init__(self) -> None:
        _identifier(self.provider_id, "delivery provider ID")
        _paths(self.staged_paths, "staged paths", 1, 32)
        _paths(self.committed_paths, "committed paths", 1, 32)
        if self.staged_paths != self.committed_paths:
            raise ValueError("Staged and committed paths differ")
        for value, label in (
            (self.commit_parent, "commit parent"),
            (self.commit_sha, "commit SHA"),
            (self.commit_tree, "commit tree"),
            (self.remote_branch_sha, "remote branch SHA"),
        ):
            _commit(value, label)
        if self.remote_branch_sha != self.commit_sha:
            raise ValueError("Remote branch does not match reviewed commit")
        if not isinstance(self.pull_request, DraftPullRequestReceipt):
            raise ValueError("Delivery pull-request receipt is invalid")
        if self.pull_request.head_commit != self.commit_sha:
            raise ValueError("Pull request is not bound to the reviewed commit")
        if not 1 <= self.git_command_count <= 96:
            raise ValueError("Delivery Git-command count is invalid")
        if not 3 <= self.controlled_network_call_count <= 12:
            raise ValueError("Delivery controlled-network count is invalid")
        if not 0 <= self.credential_handle_count <= 2:
            raise ValueError("Delivery credential-handle count is invalid")
        zero_fields = (
            self.secret_value_exposure_count,
            self.unapproved_network_call_count,
            self.unrelated_path_count,
            self.general_command_count,
            self.force_push_count,
            self.merge_count,
            self.deployment_count,
            self.release_count,
        )
        if any(value != 0 for value in zero_fields):
            raise ValueError("Delivery observation crossed a prohibited boundary")
        if (self.commit_count, self.push_count, self.pull_request_count) != (1, 1, 1):
            raise ValueError("Delivery must perform exactly one commit, push, and draft PR")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class GitHubDeliveryArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    coding_review_artifact_id: str
    coding_review_artifact_digest: str
    workspace_artifact_digest: str
    orchestration_artifact_digest: str
    qa_artifact_digest: str
    security_artifact_digest: str
    repository_id: str
    repository_identity: str
    repository_full_name: str
    workspace_id: str
    base_branch: str
    base_commit: str
    base_tree: str
    feature_branch: str
    reviewed_files: tuple[ReviewedFileBinding, ...]
    final_diff_digest: str
    commit_message: str
    pull_request_title: str
    pull_request_body_digest: str
    provider_id: str
    authority_digest: str
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    staged_paths: tuple[str, ...]
    committed_paths: tuple[str, ...]
    commit_parent: str
    commit_sha: str
    commit_tree: str
    remote_branch_sha: str
    pull_request: DraftPullRequestReceipt
    git_command_count: int
    controlled_network_call_count: int
    credential_handle_count: int
    provider_output_digest: str
    generated_at: datetime
    secret_value_exposure_count: int = 0
    unapproved_network_call_count: int = 0
    unrelated_path_count: int = 0
    general_command_count: int = 0
    force_push_count: int = 0
    commit_count: int = 1
    push_count: int = 1
    pull_request_count: int = 1
    merge_count: int = 0
    deployment_count: int = 0
    release_count: int = 0
    source_state: str = SOURCE_STATE
    workspace_state: str = WORKSPACE_STATE
    branch_state: str = BRANCH_STATE
    pull_request_state: str = PULL_REQUEST_STATE
    delivery_state: str = DELIVERY_STATE
    status: str = ARTIFACT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.artifact_id, "artifact"),
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.execution_id, "execution"),
            (self.assignment_id, "assignment"),
            (self.coding_review_artifact_id, "coding-review artifact"),
            (self.repository_id, "repository"),
            (self.workspace_id, "workspace"),
            (self.provider_id, "provider"),
        ):
            _identifier(value, f"GitHub-delivery {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order digest"),
            (self.coding_review_artifact_digest, "coding-review artifact digest"),
            (self.workspace_artifact_digest, "workspace artifact digest"),
            (self.orchestration_artifact_digest, "orchestration artifact digest"),
            (self.qa_artifact_digest, "QA artifact digest"),
            (self.security_artifact_digest, "Security artifact digest"),
            (self.final_diff_digest, "reviewed diff digest"),
            (self.pull_request_body_digest, "pull-request body digest"),
            (self.authority_digest, "authority digest"),
            (self.provider_output_digest, "provider output digest"),
        ):
            _digest(value, label)
        if repository_full_name_for(self.repository_identity) != self.repository_full_name:
            raise ValueError("Delivery artifact repository identity is invalid")
        _branch(self.base_branch, "artifact base branch", protected_allowed=True)
        _branch(self.feature_branch, "artifact feature branch", protected_allowed=False)
        _commit(self.base_commit, "artifact base commit")
        _commit(self.base_tree, "artifact base tree")
        _typed(self.reviewed_files, ReviewedFileBinding, "artifact reviewed files", 1, 32)
        _single_line(self.commit_message, "artifact commit message", 200)
        _single_line(self.pull_request_title, "artifact pull-request title", 200)
        if (
            self.capability_ids != GITHUB_DELIVERY_CAPABILITIES
            or self.action_ids != GITHUB_DELIVERY_ACTIONS
            or self.tool_ids != GITHUB_DELIVERY_TOOL_IDS
        ):
            raise ValueError("GitHub delivery artifact profile is invalid")
        observation = GitHubDeliveryObservation(
            provider_id=self.provider_id,
            staged_paths=self.staged_paths,
            committed_paths=self.committed_paths,
            commit_parent=self.commit_parent,
            commit_sha=self.commit_sha,
            commit_tree=self.commit_tree,
            remote_branch_sha=self.remote_branch_sha,
            pull_request=self.pull_request,
            git_command_count=self.git_command_count,
            controlled_network_call_count=self.controlled_network_call_count,
            credential_handle_count=self.credential_handle_count,
            secret_value_exposure_count=self.secret_value_exposure_count,
            unapproved_network_call_count=self.unapproved_network_call_count,
            unrelated_path_count=self.unrelated_path_count,
            general_command_count=self.general_command_count,
            force_push_count=self.force_push_count,
            commit_count=self.commit_count,
            push_count=self.push_count,
            pull_request_count=self.pull_request_count,
            merge_count=self.merge_count,
            deployment_count=self.deployment_count,
            release_count=self.release_count,
        )
        _utc(self.generated_at, "delivery generation time")
        if observation.digest != self.provider_output_digest:
            raise ValueError("Delivery provider output digest is invalid")
        if (
            self.source_state != SOURCE_STATE
            or self.workspace_state != WORKSPACE_STATE
            or self.branch_state != BRANCH_STATE
            or self.pull_request_state != PULL_REQUEST_STATE
            or self.delivery_state != DELIVERY_STATE
            or self.status != ARTIFACT_STATUS
            or self.pilot_status != PILOT_STATUS
        ):
            raise ValueError("GitHub delivery artifact state is invalid")

    @property
    def reviewed_paths(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.reviewed_files)

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        return canonical_digest(payload)


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "delivery execution ID")
    return f"github-delivery-{hashlib.sha256(execution_id.encode()).hexdigest()[:24]}"


def repository_full_name_for(identity: str) -> str:
    if not isinstance(identity, str):
        raise ValueError("GitHub repository identity is invalid")
    match = _REPOSITORY.fullmatch(identity)
    if match is None:
        raise ValueError("GitHub repository identity must be an exact HTTPS GitHub repository")
    return f"{match.group(1)}/{match.group(2)}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _commit(value: object, label: str) -> None:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _branch(value: object, label: str, *, protected_allowed: bool) -> None:
    if not isinstance(value, str) or _BRANCH.fullmatch(value) is None or value.endswith(("/", ".")):
        raise ValueError(f"{label} is invalid")
    if value.startswith("-") or value in {"HEAD", "FETCH_HEAD", "ORIG_HEAD"}:
        raise ValueError(f"{label} is invalid")
    if not protected_allowed and value in {"main", "master", "production", "release"}:
        raise ValueError(f"{label} is protected")


def _path(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        raise ValueError(f"{label} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", "..", ".git"} for part in path.parts):
        raise ValueError(f"{label} is invalid")
    if len(value) > 240:
        raise ValueError(f"{label} is invalid")


def _paths(values: object, label: str, minimum: int, maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label} are invalid")
    for value in values:
        _path(value, label)
    if len(set(values)) != len(values) or values != tuple(sorted(values)):
        raise ValueError(f"{label} must be unique and sorted")


def _typed(values: object, expected: type, label: str, minimum: int, maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label} are invalid")
    if any(not isinstance(item, expected) for item in values):
        raise ValueError(f"{label} contain an invalid value")


def _single_line(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or any(marker in value for marker in ("\0", "\n", "\r"))
        or len(value) > maximum
    ):
        raise ValueError(f"{label} is invalid")


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\0" in value
        or len(value.encode("utf-8")) > maximum
    ):
        raise ValueError(f"{label} is invalid")


def _items(
    values: object,
    label: str,
    minimum: int,
    maximum: int,
    item_maximum: int,
) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label} are invalid")
    for value in values:
        _text(value, label, item_maximum)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contain duplicates")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be timezone-aware UTC")
