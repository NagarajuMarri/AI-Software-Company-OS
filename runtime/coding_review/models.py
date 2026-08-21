"""Closed exact-source-bound models for the ASCOS Day 32 coding/review loop."""

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
_ACTION = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")
_BRANCH = re.compile(r"^(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")

VERIFY_CODING_SOURCES = "VERIFY_CODING_SOURCES"
APPLY_BOUNDED_IMPLEMENTATION = "APPLY_BOUNDED_IMPLEMENTATION"
RUN_QA_REVIEW = "RUN_QA_REVIEW"
RUN_SECURITY_REVIEW = "RUN_SECURITY_REVIEW"
ROUTE_FAILED_REVIEW = "ROUTE_FAILED_REVIEW"
REPORT_CODING_REVIEW_STATUS = "REPORT_CODING_REVIEW_STATUS"

CODING_REVIEW_ACTIONS = (
    VERIFY_CODING_SOURCES,
    APPLY_BOUNDED_IMPLEMENTATION,
    RUN_QA_REVIEW,
    RUN_SECURITY_REVIEW,
    ROUTE_FAILED_REVIEW,
    REPORT_CODING_REVIEW_STATUS,
)
CODING_REVIEW_CAPABILITIES = (
    "exact-day31-workspace-binding",
    "role-owned-text-implementation",
    "isolated-product-test-execution",
    "static-security-review",
    "responsible-engineer-failure-routing",
    "review-status-reporting",
)
CODING_REVIEW_TOOL_IDS = (
    "LOCAL_GIT_INSPECTION",
    "CONTROLLED_TEXT_PATCH",
    "ISOLATED_PRODUCT_PYTEST",
    "STATIC_SECURITY_REVIEW",
)

ENGINEERING_ROLES = (
    "BACKEND_ENGINEER",
    "FRONTEND_ENGINEER",
    "AI_ENGINEER",
    "DATA_ENGINEER",
)
QA_ROLE = "QA_ENGINEER"
SECURITY_ROLE = "SECURITY_ENGINEER"
PATCH_ROLES = ENGINEERING_ROLES + (QA_ROLE,)

WORK_ORDER_STATUS = "AUTHORIZED_CODING_REVIEW_ASSIGNMENT"
ARTIFACT_STATUS = "CODING_AND_REVIEWS_PASSED_AWAITING_CONTROLLED_GITHUB_DELIVERY"
SOURCE_STATE = "CLEAN_AND_UNCHANGED"
WORKSPACE_STATE = "DIRTY_REVIEWED_NOT_COMMITTED"
QA_STATE = "PASS"
SECURITY_STATE = "PASS"
DELIVERY_STATE = "NOT_STARTED"
PILOT_STATUS = "NOT_SELECTED"
ROUTE_STATE = "RETURNED_TO_RESPONSIBLE_ENGINEER"


@dataclass(frozen=True)
class CodingAssignment:
    assignment_id: str
    owner_role: str
    objective: str
    allowed_paths: tuple[str, ...]
    acceptance_checks: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.assignment_id, "coding assignment ID")
        if self.owner_role not in ENGINEERING_ROLES:
            raise ValueError("Coding assignment role is invalid")
        _text(self.objective, "coding assignment objective", 500)
        _paths(self.allowed_paths, "coding assignment paths", 1, 8)
        _items(self.acceptance_checks, "coding assignment checks", 2, 8, 300)


@dataclass(frozen=True)
class CodingReviewWorkOrder:
    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    orchestration_artifact_digest: str
    orchestration_source_set_digest: str
    workspace_artifact_digest: str
    qa_artifact_digest: str
    security_artifact_digest: str
    repository_id: str
    repository_identity: str
    workspace_id: str
    base_branch: str
    base_commit: str
    base_tree: str
    feature_branch: str
    assignments: tuple[CodingAssignment, ...]
    qa_test_paths: tuple[str, ...]
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
            _identifier(value, f"Coding-review {label} ID")
        for value, label in (
            (self.orchestration_artifact_digest, "orchestration artifact digest"),
            (self.orchestration_source_set_digest, "orchestration source-set digest"),
            (self.workspace_artifact_digest, "workspace artifact digest"),
            (self.qa_artifact_digest, "QA artifact digest"),
            (self.security_artifact_digest, "Security artifact digest"),
        ):
            _digest(value, label)
        _repository(self.repository_identity)
        _identifier(self.workspace_id, "coding-review workspace ID")
        _branch(self.base_branch, "base branch", protected_allowed=True)
        _branch(self.feature_branch, "feature branch", protected_allowed=False)
        if not self.feature_branch.startswith("agent/"):
            raise ValueError("Coding-review feature branch must use agent/")
        _commit(self.base_commit, "base commit")
        _commit(self.base_tree, "base tree")
        _typed(self.assignments, CodingAssignment, "coding assignments", 4, 4)
        if tuple(item.owner_role for item in self.assignments) != ENGINEERING_ROLES:
            raise ValueError("Coding assignment role order is invalid")
        engineering_paths = tuple(path for item in self.assignments for path in item.allowed_paths)
        if len(set(engineering_paths)) != len(engineering_paths):
            raise ValueError("Coding assignment paths overlap")
        _paths(self.qa_test_paths, "QA test paths", 1, 4)
        if set(engineering_paths) & set(self.qa_test_paths):
            raise ValueError("QA and Engineering paths overlap")
        _items(self.objectives, "coding-review objectives", 4, 10, 300)
        _items(self.acceptance_checks, "coding-review acceptance checks", 7, 16, 300)
        _items(self.constraints, "coding-review constraints", 7, 16, 300)
        _utc(self.issued_at, "coding-review work-order issue time")
        if self.status != WORK_ORDER_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Coding-review work-order state is invalid")

    @property
    def allowed_paths(self) -> tuple[str, ...]:
        return tuple(path for item in self.assignments for path in item.allowed_paths) + self.qa_test_paths

    def owner_for(self, path: str) -> str:
        if path in self.qa_test_paths:
            return QA_ROLE
        for assignment in self.assignments:
            if path in assignment.allowed_paths:
                return assignment.owner_role
        raise ValueError("Path does not belong to a coding assignment")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class CodingReviewAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    work_order_digest: str
    workspace_artifact_digest: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_review_rounds: int = 3
    max_file_writes: int = 16
    max_tool_calls: int = 64
    live_provider_allowed: bool = False
    network_allowed: bool = False
    credentials_allowed: bool = False
    source_file_writes_allowed: bool = False
    workspace_text_writes_allowed: bool = True
    commit_allowed: bool = False
    push_allowed: bool = False
    pull_request_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
        ):
            _identifier(value, f"Coding-review {label} ID")
        _digest(self.work_order_digest, "authority work-order digest")
        _digest(self.workspace_artifact_digest, "authority workspace digest")
        _actions(self.allowed_action_ids)
        if self.allowed_action_ids != CODING_REVIEW_ACTIONS:
            raise ValueError("Coding-review authority action profile is invalid")
        if self.allowed_tool_ids != CODING_REVIEW_TOOL_IDS:
            raise ValueError("Coding-review authority tool profile is invalid")
        _utc(self.issued_at, "coding-review authority issue time")
        _utc(self.expires_at, "coding-review authority expiry time")
        if self.expires_at <= self.issued_at:
            raise ValueError("Coding-review authority expiry is invalid")
        if not 1 <= self.max_review_rounds <= 5:
            raise ValueError("Coding-review round budget is invalid")
        if not 6 <= self.max_file_writes <= 32 or not 16 <= self.max_tool_calls <= 96:
            raise ValueError("Coding-review effect budget is invalid")
        if (
            self.live_provider_allowed
            or self.network_allowed
            or self.credentials_allowed
            or self.source_file_writes_allowed
            or not self.workspace_text_writes_allowed
            or self.commit_allowed
            or self.push_allowed
            or self.pull_request_allowed
        ):
            raise ValueError("Coding-review authority exceeds Day 32")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class TextPatch:
    owner_role: str
    path: str
    content: str

    def __post_init__(self) -> None:
        if self.owner_role not in PATCH_ROLES:
            raise ValueError("Text patch owner role is invalid")
        _path(self.path, "text patch path")
        if (
            not isinstance(self.content, str)
            or "\0" in self.content
            or len(self.content.encode("utf-8")) > 128_000
        ):
            raise ValueError("Text patch content is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class CodingRoundPlan:
    round_number: int
    patches: tuple[TextPatch, ...]
    resolves_feedback_codes: tuple[str, ...]
    failure_owner_role: str

    def __post_init__(self) -> None:
        if not isinstance(self.round_number, int) or isinstance(self.round_number, bool) or self.round_number < 1:
            raise ValueError("Coding round number is invalid")
        _typed(self.patches, TextPatch, "text patches", 1, 16)
        paths = tuple(item.path for item in self.patches)
        if len(set(paths)) != len(paths):
            raise ValueError("Coding round contains duplicate paths")
        _items(self.resolves_feedback_codes, "resolved feedback codes", 0, 8, 128)
        if self.failure_owner_role not in ENGINEERING_ROLES:
            raise ValueError("Coding round failure owner is invalid")


@dataclass(frozen=True)
class ReviewFinding:
    code: str
    reviewer_role: str
    responsible_role: str
    path: str
    severity: str
    summary: str

    def __post_init__(self) -> None:
        _identifier(self.code, "review finding code")
        if self.reviewer_role not in {QA_ROLE, SECURITY_ROLE}:
            raise ValueError("Review finding reviewer is invalid")
        if self.responsible_role not in ENGINEERING_ROLES:
            raise ValueError("Review finding responsible role is invalid")
        _path(self.path, "review finding path")
        if self.severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("Review finding severity is invalid")
        _text(self.summary, "review finding summary", 500)


@dataclass(frozen=True)
class CodingRoundRecord:
    round_number: int
    resolved_feedback_codes: tuple[str, ...]
    changed_paths: tuple[str, ...]
    qa_status: str
    qa_test_count: int
    qa_result_digest: str
    security_status: str
    findings: tuple[ReviewFinding, ...]
    diff_digest: str
    file_write_count: int
    specialized_command_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.round_number, int) or isinstance(self.round_number, bool) or self.round_number < 1:
            raise ValueError("Coding round record number is invalid")
        _items(self.resolved_feedback_codes, "round resolved feedback", 0, 8, 128)
        _paths(self.changed_paths, "round changed paths", 1, 16)
        if self.qa_status not in {"PASS", "FAIL"}:
            raise ValueError("Coding round QA state is invalid")
        if self.security_status not in {"PASS", "FAIL", "NOT_RUN_QA_FAILED"}:
            raise ValueError("Coding round Security state is invalid")
        if not isinstance(self.qa_test_count, int) or isinstance(self.qa_test_count, bool) or self.qa_test_count < 0:
            raise ValueError("Coding round QA test count is invalid")
        for value, label in ((self.qa_result_digest, "QA result"), (self.diff_digest, "round diff")):
            _digest(value, label)
        _typed(self.findings, ReviewFinding, "review findings", 0, 8)
        if self.qa_status == "FAIL":
            if self.security_status != "NOT_RUN_QA_FAILED" or not self.findings:
                raise ValueError("Failed QA round must route findings before Security")
            if any(item.reviewer_role != QA_ROLE for item in self.findings):
                raise ValueError("Failed QA round findings are invalid")
        elif self.security_status == "FAIL":
            if not self.findings or any(item.reviewer_role != SECURITY_ROLE for item in self.findings):
                raise ValueError("Failed Security round findings are invalid")
        elif self.security_status == "PASS" and self.findings:
            raise ValueError("Passing review round cannot contain findings")
        if not 1 <= self.file_write_count <= 16 or self.specialized_command_count not in {1, 2}:
            raise ValueError("Coding round effect counts are invalid")

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.findings)


@dataclass(frozen=True)
class FailureRoute:
    route_id: str
    round_number: int
    finding_code: str
    reviewer_role: str
    responsible_role: str
    state: str = ROUTE_STATE

    def __post_init__(self) -> None:
        _identifier(self.route_id, "failure route ID")
        if not isinstance(self.round_number, int) or isinstance(self.round_number, bool) or self.round_number < 1:
            raise ValueError("Failure route round is invalid")
        _identifier(self.finding_code, "failure route finding code")
        if self.reviewer_role not in {QA_ROLE, SECURITY_ROLE}:
            raise ValueError("Failure route reviewer is invalid")
        if self.responsible_role not in ENGINEERING_ROLES or self.state != ROUTE_STATE:
            raise ValueError("Failure route target or state is invalid")


@dataclass(frozen=True)
class ObservedProductFile:
    path: str
    owner_role: str
    content_digest: str

    def __post_init__(self) -> None:
        _path(self.path, "observed product path")
        if self.owner_role not in PATCH_ROLES:
            raise ValueError("Observed product owner is invalid")
        _digest(self.content_digest, "observed product content digest")


@dataclass(frozen=True)
class CodingReviewObservation:
    provider_id: str
    rounds: tuple[CodingRoundRecord, ...]
    failure_routes: tuple[FailureRoute, ...]
    final_changed_paths: tuple[str, ...]
    final_files: tuple[ObservedProductFile, ...]
    final_diff_digest: str
    qa_execution_count: int
    security_execution_count: int
    product_file_write_count: int
    specialized_command_count: int
    network_call_count: int = 0
    general_command_count: int = 0
    credential_access_count: int = 0
    commit_count: int = 0
    push_count: int = 0
    pull_request_count: int = 0

    def __post_init__(self) -> None:
        _identifier(self.provider_id, "coding-review provider ID")
        _typed(self.rounds, CodingRoundRecord, "coding rounds", 1, 5)
        if tuple(item.round_number for item in self.rounds) != tuple(range(1, len(self.rounds) + 1)):
            raise ValueError("Coding review round order is invalid")
        if self.rounds[-1].qa_status != QA_STATE or self.rounds[-1].security_status != SECURITY_STATE:
            raise ValueError("Coding review did not finish with QA and Security pass")
        _typed(self.failure_routes, FailureRoute, "failure routes", 0, 16)
        expected_routes = tuple(
            (record.round_number, finding.code, finding.reviewer_role, finding.responsible_role)
            for record in self.rounds
            for finding in record.findings
        )
        actual_routes = tuple(
            (item.round_number, item.finding_code, item.reviewer_role, item.responsible_role)
            for item in self.failure_routes
        )
        if actual_routes != expected_routes:
            raise ValueError("Coding review failure routes are incomplete")
        _paths(self.final_changed_paths, "final changed paths", 1, 32)
        _typed(self.final_files, ObservedProductFile, "final files", 1, 32)
        if tuple(item.path for item in self.final_files) != self.final_changed_paths:
            raise ValueError("Final file evidence does not match changed paths")
        _digest(self.final_diff_digest, "final diff digest")
        expected_qa = len(self.rounds)
        expected_security = sum(item.security_status != "NOT_RUN_QA_FAILED" for item in self.rounds)
        if self.qa_execution_count != expected_qa or self.security_execution_count != expected_security:
            raise ValueError("Coding review execution counts are invalid")
        if self.product_file_write_count != sum(item.file_write_count for item in self.rounds):
            raise ValueError("Coding review file-write count is invalid")
        if self.specialized_command_count != sum(item.specialized_command_count for item in self.rounds):
            raise ValueError("Coding review command count is invalid")
        for value, label in (
            (self.network_call_count, "network"),
            (self.general_command_count, "general command"),
            (self.credential_access_count, "credential"),
            (self.commit_count, "commit"),
            (self.push_count, "push"),
            (self.pull_request_count, "pull-request"),
        ):
            if value != 0:
                raise ValueError(f"Coding review {label} count must be zero")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class CodingReviewArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    orchestration_artifact_id: str
    orchestration_artifact_digest: str
    orchestration_source_set_digest: str
    workspace_artifact_id: str
    workspace_artifact_digest: str
    qa_artifact_id: str
    qa_artifact_digest: str
    security_artifact_id: str
    security_artifact_digest: str
    repository_id: str
    repository_identity: str
    workspace_id: str
    base_branch: str
    base_commit: str
    base_tree: str
    feature_branch: str
    provider_id: str
    authority_digest: str
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    rounds: tuple[CodingRoundRecord, ...]
    failure_routes: tuple[FailureRoute, ...]
    final_changed_paths: tuple[str, ...]
    final_files: tuple[ObservedProductFile, ...]
    final_diff_digest: str
    qa_execution_count: int
    security_execution_count: int
    product_file_write_count: int
    specialized_command_count: int
    git_inspection_count: int
    provider_output_digest: str
    generated_at: datetime
    network_call_count: int = 0
    general_command_count: int = 0
    credential_access_count: int = 0
    staged_path_count: int = 0
    commit_count: int = 0
    push_count: int = 0
    pull_request_count: int = 0
    source_state: str = SOURCE_STATE
    workspace_state: str = WORKSPACE_STATE
    qa_state: str = QA_STATE
    security_state: str = SECURITY_STATE
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
            (self.orchestration_artifact_id, "orchestration artifact"),
            (self.workspace_artifact_id, "workspace artifact"),
            (self.qa_artifact_id, "QA artifact"),
            (self.security_artifact_id, "Security artifact"),
            (self.repository_id, "repository"),
            (self.workspace_id, "workspace"),
            (self.provider_id, "provider"),
        ):
            _identifier(value, f"Coding-review {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order digest"),
            (self.orchestration_artifact_digest, "orchestration artifact digest"),
            (self.orchestration_source_set_digest, "orchestration source-set digest"),
            (self.workspace_artifact_digest, "workspace artifact digest"),
            (self.qa_artifact_digest, "QA artifact digest"),
            (self.security_artifact_digest, "Security artifact digest"),
            (self.authority_digest, "authority digest"),
            (self.final_diff_digest, "final diff digest"),
            (self.provider_output_digest, "provider output digest"),
        ):
            _digest(value, label)
        _repository(self.repository_identity)
        _branch(self.base_branch, "artifact base branch", protected_allowed=True)
        _branch(self.feature_branch, "artifact feature branch", protected_allowed=False)
        _commit(self.base_commit, "artifact base commit")
        _commit(self.base_tree, "artifact base tree")
        if (
            self.capability_ids != CODING_REVIEW_CAPABILITIES
            or self.action_ids != CODING_REVIEW_ACTIONS
            or self.tool_ids != CODING_REVIEW_TOOL_IDS
        ):
            raise ValueError("Coding-review artifact profile is invalid")
        observation = CodingReviewObservation(
            provider_id=self.provider_id,
            rounds=self.rounds,
            failure_routes=self.failure_routes,
            final_changed_paths=self.final_changed_paths,
            final_files=self.final_files,
            final_diff_digest=self.final_diff_digest,
            qa_execution_count=self.qa_execution_count,
            security_execution_count=self.security_execution_count,
            product_file_write_count=self.product_file_write_count,
            specialized_command_count=self.specialized_command_count,
            network_call_count=self.network_call_count,
            general_command_count=self.general_command_count,
            credential_access_count=self.credential_access_count,
            commit_count=self.commit_count,
            push_count=self.push_count,
            pull_request_count=self.pull_request_count,
        )
        if not 8 <= self.git_inspection_count <= 32:
            raise ValueError("Coding-review Git inspection count is invalid")
        _utc(self.generated_at, "coding-review generation time")
        if (
            observation.digest != self.provider_output_digest
            or self.staged_path_count != 0
            or self.source_state != SOURCE_STATE
            or self.workspace_state != WORKSPACE_STATE
            or self.qa_state != QA_STATE
            or self.security_state != SECURITY_STATE
            or self.delivery_state != DELIVERY_STATE
            or self.status != ARTIFACT_STATUS
            or self.pilot_status != PILOT_STATUS
        ):
            raise ValueError("Coding-review artifact state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        return canonical_digest(payload)


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "coding-review execution ID")
    return "coding-review-" + hashlib.sha256(execution_id.encode()).hexdigest()[:24]


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"Coding-review {label} is invalid")


def _commit(value: object, label: str) -> None:
    if not isinstance(value, str) or not _COMMIT.fullmatch(value):
        raise ValueError(f"Coding-review {label} is invalid")


def _branch(value: object, label: str, *, protected_allowed: bool) -> None:
    if (
        not isinstance(value, str)
        or not _BRANCH.fullmatch(value)
        or value.endswith(("/", "."))
        or value.lower() in {"head", "refs/heads/head"}
    ):
        raise ValueError(f"Coding-review {label} is invalid")
    if not protected_allowed and value in {"main", "master"}:
        raise ValueError("Coding-review feature branch is protected")


def _repository(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("https://")
        or any(marker in value for marker in ("\n", "\r", "@"))
        or len(value) > 500
    ):
        raise ValueError("Coding-review repository identity is unsafe")


def _path(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    path = PurePosixPath(value.replace("\\", "/"))
    if (
        path.is_absolute()
        or ".." in path.parts
        or str(path) in {"", ".", ".git"}
        or str(path).startswith(".git/")
        or len(str(path)) > 240
    ):
        raise ValueError(f"{label} is invalid")


def _paths(values: object, label: str, minimum: int, maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label} are invalid")
    for value in values:
        _path(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contain duplicates")


def _actions(values: object) -> None:
    if (
        not isinstance(values, tuple)
        or not values
        or any(not isinstance(value, str) or not _ACTION.fullmatch(value) for value in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError("Coding-review actions are invalid")


def _items(values: object, label: str, minimum: int, maximum: int, item_maximum: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label} are invalid")
    for value in values:
        _text(value, label, item_maximum)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contain duplicates")


def _typed(values: object, kind: type, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or any(not isinstance(value, kind) for value in values)
    ):
        raise ValueError(f"{label} are invalid")


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{label} is invalid")


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must use UTC")
