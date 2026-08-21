"""Closed exact-source-bound models for ASCOS Day 31 workspaces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ACTION = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")
_BRANCH = re.compile(r"^(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")

VERIFY_EXACT_BASE = "VERIFY_EXACT_BASE"
CREATE_ISOLATED_WORKTREE = "CREATE_ISOLATED_WORKTREE"
CREATE_FEATURE_BRANCH = "CREATE_FEATURE_BRANCH"
VERIFY_SOURCE_UNCHANGED = "VERIFY_SOURCE_UNCHANGED"
REPORT_WORKSPACE_STATUS = "REPORT_WORKSPACE_STATUS"

WORKSPACE_ACTIONS = (
    VERIFY_EXACT_BASE,
    CREATE_ISOLATED_WORKTREE,
    CREATE_FEATURE_BRANCH,
    VERIFY_SOURCE_UNCHANGED,
    REPORT_WORKSPACE_STATUS,
)
WORKSPACE_CAPABILITIES = (
    "exact-base-verification",
    "isolated-git-worktree-preparation",
    "protected-feature-branch-creation",
    "source-repository-preservation",
    "workspace-status-reporting",
)
WORKSPACE_TOOL_IDS = ("LOCAL_GIT_WORKTREE",)

WORK_ORDER_STATUS = "AUTHORIZED_ISOLATED_PRODUCT_WORKSPACE_ASSIGNMENT"
ARTIFACT_STATUS = "ISOLATED_WORKSPACE_READY_FOR_AUTHORIZED_CODING"
WORKSPACE_STATE = "READY_NOT_USED"
BRANCH_STATE = "FEATURE_BRANCH_READY_AT_EXACT_BASE"
SOURCE_STATE = "CLEAN_AND_UNCHANGED"
PILOT_STATUS = "NOT_SELECTED"


@dataclass(frozen=True)
class ProductWorkspaceWorkOrder:
    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    orchestration_artifact_digest: str
    repository_id: str
    repository_identity: str
    base_branch: str
    expected_base_commit: str
    feature_branch: str
    workspace_id: str
    objectives: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    status: str = WORK_ORDER_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for identifier_value, label in (
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.assignment_id, "assignment"),
            (self.repository_id, "repository"),
            (self.workspace_id, "workspace"),
        ):
            _identifier(identifier_value, f"Product workspace {label} ID")
        _digest(self.orchestration_artifact_digest, "orchestration artifact digest")
        _text(self.repository_identity, "repository identity", 500)
        if (
            not self.repository_identity.startswith("https://")
            or any(marker in self.repository_identity for marker in ("\n", "\r", "@"))
        ):
            raise ValueError("Product workspace repository identity is unsafe")
        _branch(self.base_branch, "base branch", protected_allowed=True)
        _commit(self.expected_base_commit, "expected base commit")
        _branch(self.feature_branch, "feature branch", protected_allowed=False)
        if not self.feature_branch.startswith("agent/"):
            raise ValueError("Product workspace feature branch must use the agent/ namespace")
        _items(self.objectives, "objectives", 4, 10, 300)
        _items(self.acceptance_checks, "acceptance checks", 6, 14, 300)
        _items(self.constraints, "constraints", 5, 14, 300)
        _utc(self.issued_at, "work-order issue time")
        if self.status != WORK_ORDER_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Product workspace work-order state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class ProductWorkspaceAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    work_order_digest: str
    orchestration_artifact_digest: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_workspaces: int = 1
    max_tool_calls: int = 24
    network_allowed: bool = False
    source_file_writes_allowed: bool = False
    workspace_file_mutation_allowed: bool = False

    def __post_init__(self) -> None:
        for identifier_value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
        ):
            _identifier(identifier_value, f"Product workspace {label} ID")
        _digest(self.work_order_digest, "authority work-order digest")
        _digest(self.orchestration_artifact_digest, "authority orchestration digest")
        _actions(self.allowed_action_ids)
        if self.allowed_action_ids != WORKSPACE_ACTIONS:
            raise ValueError("Product workspace authority action profile is invalid")
        if self.allowed_tool_ids != WORKSPACE_TOOL_IDS:
            raise ValueError("Product workspace authority tool profile is invalid")
        _utc(self.issued_at, "authority issue time")
        _utc(self.expires_at, "authority expiry time")
        if self.expires_at <= self.issued_at:
            raise ValueError("Product workspace authority expiry is invalid")
        if self.max_workspaces != 1 or not 12 <= self.max_tool_calls <= 32:
            raise ValueError("Product workspace authority budget is invalid")
        if (
            self.network_allowed
            or self.source_file_writes_allowed
            or self.workspace_file_mutation_allowed
        ):
            raise ValueError("Product workspace authority exceeds Day 31")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class WorkspacePreparationObservation:
    provider_id: str
    workspace_relative_path: str
    source_branch_before: str
    source_branch_after: str
    source_head_before: str
    source_head_after: str
    source_tree_before: str
    source_tree_after: str
    workspace_branch: str
    workspace_head: str
    workspace_tree: str
    source_clean_before: bool
    source_clean_after: bool
    workspace_clean: bool
    branch_created: bool
    workspace_created: bool
    git_command_count: int
    network_call_count: int
    general_command_count: int
    product_file_write_count: int
    unrelated_path_change_count: int
    source_state: str = SOURCE_STATE
    workspace_state: str = WORKSPACE_STATE
    branch_state: str = BRANCH_STATE

    def __post_init__(self) -> None:
        _identifier(self.provider_id, "workspace provider ID")
        _relative_workspace(self.workspace_relative_path)
        _branch(self.source_branch_before, "source branch before", protected_allowed=True)
        _branch(self.source_branch_after, "source branch after", protected_allowed=True)
        _branch(self.workspace_branch, "workspace branch", protected_allowed=False)
        for commit_value, label in (
            (self.source_head_before, "source head before"),
            (self.source_head_after, "source head after"),
            (self.workspace_head, "workspace head"),
        ):
            _commit(commit_value, label)
        for tree_value, label in (
            (self.source_tree_before, "source tree before"),
            (self.source_tree_after, "source tree after"),
            (self.workspace_tree, "workspace tree"),
        ):
            _commit(tree_value, label)
        for bool_value, label in (
            (self.source_clean_before, "source clean before"),
            (self.source_clean_after, "source clean after"),
            (self.workspace_clean, "workspace clean"),
            (self.branch_created, "branch created"),
            (self.workspace_created, "workspace created"),
        ):
            if not isinstance(bool_value, bool):
                raise ValueError(f"Product workspace {label} is invalid")
        for count_value, label, maximum in (
            (self.git_command_count, "Git command count", 32),
            (self.network_call_count, "network call count", 0),
            (self.general_command_count, "general command count", 0),
            (self.product_file_write_count, "product file write count", 0),
            (self.unrelated_path_change_count, "unrelated path change count", 0),
        ):
            if (
                not isinstance(count_value, int)
                or isinstance(count_value, bool)
                or not 0 <= count_value <= maximum
            ):
                raise ValueError(f"Product workspace {label} is invalid")
        if self.git_command_count < 12:
            raise ValueError("Product workspace Git verification is incomplete")
        if not all((
            self.source_clean_before,
            self.source_clean_after,
            self.workspace_clean,
            self.branch_created,
            self.workspace_created,
        )):
            raise ValueError("Product workspace preparation is incomplete")
        if (
            self.source_state != SOURCE_STATE
            or self.workspace_state != WORKSPACE_STATE
            or self.branch_state != BRANCH_STATE
        ):
            raise ValueError("Product workspace state is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class ProductWorkspaceArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    orchestration_artifact_id: str
    orchestration_artifact_digest: str
    repository_id: str
    repository_identity: str
    provider_id: str
    authority_digest: str
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    workspace_id: str
    workspace_relative_path: str
    base_branch: str
    base_commit: str
    base_tree: str
    feature_branch: str
    workspace_head: str
    workspace_tree: str
    git_command_count: int
    network_call_count: int
    general_command_count: int
    product_file_write_count: int
    unrelated_path_change_count: int
    provider_output_digest: str
    generated_at: datetime
    source_state: str = SOURCE_STATE
    workspace_state: str = WORKSPACE_STATE
    branch_state: str = BRANCH_STATE
    status: str = ARTIFACT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for identifier_value, label in (
            (self.artifact_id, "artifact"),
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.execution_id, "execution"),
            (self.assignment_id, "assignment"),
            (self.orchestration_artifact_id, "orchestration artifact"),
            (self.repository_id, "repository"),
            (self.provider_id, "provider"),
            (self.workspace_id, "workspace"),
        ):
            _identifier(identifier_value, f"Product workspace {label} ID")
        for digest_value, label in (
            (self.work_order_digest, "work-order digest"),
            (self.orchestration_artifact_digest, "orchestration artifact digest"),
            (self.authority_digest, "authority digest"),
            (self.provider_output_digest, "provider output digest"),
        ):
            _digest(digest_value, label)
        _text(self.repository_identity, "repository identity", 500)
        if (
            not self.repository_identity.startswith("https://")
            or any(marker in self.repository_identity for marker in ("\n", "\r", "@"))
        ):
            raise ValueError("Product workspace repository identity is unsafe")
        if (
            self.capability_ids != WORKSPACE_CAPABILITIES
            or self.action_ids != WORKSPACE_ACTIONS
            or self.tool_ids != WORKSPACE_TOOL_IDS
        ):
            raise ValueError("Product workspace profile is invalid")
        _relative_workspace(self.workspace_relative_path)
        _branch(self.base_branch, "artifact base branch", protected_allowed=True)
        _branch(self.feature_branch, "artifact feature branch", protected_allowed=False)
        for commit_value, label in (
            (self.base_commit, "artifact base commit"),
            (self.base_tree, "artifact base tree"),
            (self.workspace_head, "artifact workspace head"),
            (self.workspace_tree, "artifact workspace tree"),
        ):
            _commit(commit_value, label)
        for count_value, label, maximum in (
            (self.git_command_count, "Git command count", 32),
            (self.network_call_count, "network call count", 0),
            (self.general_command_count, "general command count", 0),
            (self.product_file_write_count, "product file write count", 0),
            (self.unrelated_path_change_count, "unrelated path change count", 0),
        ):
            if (
                not isinstance(count_value, int)
                or isinstance(count_value, bool)
                or not 0 <= count_value <= maximum
            ):
                raise ValueError(f"Product workspace {label} is invalid")
        _utc(self.generated_at, "artifact generation time")
        if (
            self.source_state != SOURCE_STATE
            or self.workspace_state != WORKSPACE_STATE
            or self.branch_state != BRANCH_STATE
            or self.status != ARTIFACT_STATUS
            or self.pilot_status != PILOT_STATUS
        ):
            raise ValueError("Product workspace artifact state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        return canonical_digest(payload)


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "product workspace execution ID")
    return "product-workspace-" + hashlib.sha256(execution_id.encode()).hexdigest()[:24]


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"Product workspace {label} is invalid")


def _commit(value: object, label: str) -> None:
    if not isinstance(value, str) or not _COMMIT.fullmatch(value):
        raise ValueError(f"Product workspace {label} is invalid")


def _branch(value: object, label: str, *, protected_allowed: bool) -> None:
    if (
        not isinstance(value, str)
        or not _BRANCH.fullmatch(value)
        or value.endswith(("/", "."))
        or value.lower() in {"head", "refs/heads/head"}
    ):
        raise ValueError(f"Product workspace {label} is invalid")
    if not protected_allowed and value in {"main", "master"}:
        raise ValueError("Product workspace feature branch is protected")


def _actions(values: object) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError("Product workspace actions are invalid")
    if any(not isinstance(value, str) or not _ACTION.fullmatch(value) for value in values):
        raise ValueError("Product workspace actions are invalid")
    if len(set(values)) != len(values):
        raise ValueError("Product workspace actions contain duplicates")


def _relative_workspace(value: object) -> None:
    if (
        not isinstance(value, str)
        or not _IDENTIFIER.fullmatch(value)
        or "/" in value
        or "\\" in value
        or value in {".", ".."}
    ):
        raise ValueError("Product workspace relative path is invalid")


def _items(values: object, label: str, minimum: int, maximum: int, item_maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"Product workspace {label} are invalid")
    for value in values:
        _text(value, f"{label} item", item_maximum)
    if len(set(values)) != len(values):
        raise ValueError(f"Product workspace {label} contain duplicates")


def _text(value: object, label: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Product workspace {label} is invalid")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"Product workspace {label} must be timezone-aware UTC")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"Product workspace {label} must use UTC")
