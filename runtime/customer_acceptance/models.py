"""Immutable Completion Module 5 preview and browser acceptance records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import re
from urllib.parse import urlsplit

from runtime.managed_product_browser import (
    BrowserInputBinding,
    BrowserJourneySpecification,
)


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_BRANCH = re.compile(
    r"^(?![-/.])(?!.*(?:\.\.|//|@\{|[~^:?*\[\\]))"
    r"(?!.*(?:/\.|\.lock(?:/|$)))[A-Za-z0-9._/-]{1,200}(?<![/.])$"
)
_WORKFLOW = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]*preview[A-Za-z0-9_.-]*\.ya?ml$")


class CustomerAcceptanceStatus(str, Enum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTION_IN_PROGRESS = "EXECUTION_IN_PROGRESS"
    EVIDENCE_READY = "EVIDENCE_READY"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class CustomerAcceptanceConfiguration:
    """Operator-owned preview/browser policy; browser forms cannot populate it."""

    preview_environment_id: str
    preview_url: str
    workflow_file: str
    automated_test_job: str
    security_job: str
    acceptance_profile_id: str
    acceptance_profile_version: str
    allowed_origins: tuple[str, ...]
    journeys: tuple[BrowserJourneySpecification, ...]
    inputs: tuple[BrowserInputBinding, ...] = ()
    browser_cdp_reference: str | None = None
    enabled: bool = False
    preview_deployment_confirmed: bool = False
    browser_execution_confirmed: bool = False
    workflow_timeout_seconds: int = 900

    def __post_init__(self) -> None:
        _id(self.preview_environment_id, "preview environment ID")
        if not self.preview_environment_id.startswith("preview-"):
            raise ValueError("Preview environment must use a preview-* identity")
        _origin(self.preview_url, "preview URL")
        if not _WORKFLOW.fullmatch(self.workflow_file):
            raise ValueError("Preview workflow must be a preview-only GitHub workflow file")
        _text(self.automated_test_job, "automated-test job", 200)
        _text(self.security_job, "security job", 200)
        if self.automated_test_job == self.security_job:
            raise ValueError("Test and security workflow jobs must be distinct")
        _id(self.acceptance_profile_id, "acceptance profile ID")
        _text(self.acceptance_profile_version, "acceptance profile version", 128)
        if (
            not self.allowed_origins
            or self.allowed_origins != tuple(sorted(set(self.allowed_origins)))
            or self.preview_url not in self.allowed_origins
        ):
            raise ValueError("Allowed preview origins must be canonical, sorted, and complete")
        for value in self.allowed_origins:
            _origin(value, "allowed browser origin")
        if (
            not self.journeys
            or len(self.journeys) > 50
            or any(not isinstance(value, BrowserJourneySpecification) for value in self.journeys)
            or len({value.journey_id for value in self.journeys}) != len(self.journeys)
        ):
            raise ValueError("Acceptance journeys are invalid")
        if (
            len(self.inputs) > 100
            or any(not isinstance(value, BrowserInputBinding) for value in self.inputs)
            or len({value.input_id for value in self.inputs}) != len(self.inputs)
        ):
            raise ValueError("Acceptance browser inputs are invalid")
        used = {
            step.input_id
            for journey in self.journeys
            for step in journey.steps
            if step.input_id
        }
        if used != {value.input_id for value in self.inputs}:
            raise ValueError("Acceptance browser inputs must be referenced exactly")
        if self.browser_cdp_reference is not None:
            _id(self.browser_cdp_reference, "cloud browser CDP reference")
        if not isinstance(self.enabled, bool) or not isinstance(
            self.preview_deployment_confirmed, bool
        ) or not isinstance(self.browser_execution_confirmed, bool):
            raise ValueError("Acceptance enablement values must be boolean")
        if (self.preview_deployment_confirmed or self.browser_execution_confirmed) and not self.enabled:
            raise ValueError("Acceptance effect confirmation requires enablement")
        if self.preview_deployment_confirmed != self.browser_execution_confirmed:
            raise ValueError("Preview deployment and browser execution require separate confirmation")
        if (
            isinstance(self.workflow_timeout_seconds, bool)
            or not 60 <= self.workflow_timeout_seconds <= 3_600
        ):
            raise ValueError("Preview workflow timeout is outside policy")

    @property
    def live_enabled(self) -> bool:
        return (
            self.enabled
            and self.preview_deployment_confirmed
            and self.browser_execution_confirmed
        )

    @property
    def digest(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class AcceptanceJourneySummary:
    journey_id: str
    capability_id: str
    title: str
    start_path: str
    step_count: int

    def __post_init__(self) -> None:
        _id(self.journey_id, "acceptance journey ID")
        _id(self.capability_id, "acceptance capability ID")
        _text(self.title, "acceptance journey title", 512)
        if not self.start_path.startswith("/") or "?" in self.start_path or "#" in self.start_path:
            raise ValueError("Acceptance journey start path is invalid")
        if not isinstance(self.step_count, int) or isinstance(self.step_count, bool) or not 1 <= self.step_count <= 100:
            raise ValueError("Acceptance journey step count is invalid")


@dataclass(frozen=True)
class WorkflowJobReceipt:
    job_id: int
    name: str
    conclusion: str
    url: str

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, int) or isinstance(self.job_id, bool) or self.job_id < 1:
            raise ValueError("Workflow job ID is invalid")
        _text(self.name, "workflow job name", 200)
        if self.conclusion != "SUCCESS":
            raise ValueError("Required workflow job did not succeed")
        _github_url(self.url, "workflow job URL")


@dataclass(frozen=True)
class PreviewDeploymentReceipt:
    provider_id: str
    workflow_run_id: int
    workflow_run_url: str
    repository_full_name: str
    branch: str
    commit_sha: str
    tree_sha: str
    preview_environment_id: str
    preview_url: str
    deployment_revision: str
    health_status_code: int
    health_digest: str
    jobs: tuple[WorkflowJobReceipt, ...]
    deployed_at: datetime

    def __post_init__(self) -> None:
        _id(self.provider_id, "preview provider ID")
        if (
            not isinstance(self.workflow_run_id, int)
            or isinstance(self.workflow_run_id, bool)
            or self.workflow_run_id < 1
        ):
            raise ValueError("Workflow run ID is invalid")
        _github_url(self.workflow_run_url, "workflow run URL")
        if not _REPOSITORY.fullmatch(self.repository_full_name):
            raise ValueError("Preview repository is invalid")
        if not _BRANCH.fullmatch(self.branch) or not self.branch.startswith("agent/"):
            raise ValueError("Preview branch is invalid")
        _commit(self.commit_sha, "preview commit")
        _commit(self.tree_sha, "preview tree")
        _id(self.preview_environment_id, "preview environment ID")
        _origin(self.preview_url, "preview receipt URL")
        _id(self.deployment_revision, "preview deployment revision")
        if (
            not isinstance(self.health_status_code, int)
            or isinstance(self.health_status_code, bool)
            or not 200 <= self.health_status_code <= 399
        ):
            raise ValueError("Preview health status is invalid")
        _digest(self.health_digest, "preview health digest")
        if len(self.jobs) != 2 or any(not isinstance(value, WorkflowJobReceipt) for value in self.jobs):
            raise ValueError("Preview workflow evidence is incomplete")
        _utc(self.deployed_at, "preview deployment time")

    @property
    def digest(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class CustomerAcceptanceRecord:
    acceptance_id: str
    customer_id: str
    request_id: str
    product_id: str
    delivery_id: str
    delivery_digest: str
    delivery_review_digest: str
    repository_full_name: str
    base_branch: str
    head_branch: str
    commit_sha: str
    tree_sha: str
    pull_request_number: int
    pull_request_url: str
    configuration_digest: str
    preview_environment_id: str
    preview_url: str
    workflow_file: str
    automated_test_job: str
    security_job: str
    browser_plan_id: str
    browser_plan_digest: str
    journeys: tuple[AcceptanceJourneySummary, ...]
    created_at: datetime
    updated_at: datetime
    status: CustomerAcceptanceStatus = CustomerAcceptanceStatus.AWAITING_APPROVAL
    approved_at: datetime | None = None
    approved_by: str | None = None
    workflow_run_id: int | None = None
    workflow_run_url: str | None = None
    deployment_revision: str | None = None
    deployment_receipt_digest: str | None = None
    browser_execution_digest: str | None = None
    evidence_package_id: str | None = None
    evidence_package_digest: str | None = None
    failure_classification: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.acceptance_id, "acceptance ID"),
            (self.customer_id, "acceptance customer ID"),
            (self.request_id, "acceptance request ID"),
            (self.product_id, "acceptance product ID"),
            (self.delivery_id, "acceptance delivery ID"),
            (self.preview_environment_id, "acceptance preview environment ID"),
            (self.browser_plan_id, "acceptance browser plan ID"),
        ):
            _id(value, label)
        for value, label in (
            (self.delivery_digest, "delivery digest"),
            (self.delivery_review_digest, "delivery review digest"),
            (self.configuration_digest, "acceptance configuration digest"),
            (self.browser_plan_digest, "browser plan digest"),
        ):
            _digest(value, label)
        if not _REPOSITORY.fullmatch(self.repository_full_name):
            raise ValueError("Acceptance repository is invalid")
        for branch in (self.base_branch, self.head_branch):
            if not _BRANCH.fullmatch(branch):
                raise ValueError("Acceptance branch is invalid")
        if not self.head_branch.startswith("agent/") or self.base_branch == self.head_branch:
            raise ValueError("Acceptance branch authority is invalid")
        _commit(self.commit_sha, "acceptance commit")
        _commit(self.tree_sha, "acceptance tree")
        if not isinstance(self.pull_request_number, int) or isinstance(self.pull_request_number, bool) or self.pull_request_number < 1:
            raise ValueError("Acceptance pull-request number is invalid")
        _github_url(self.pull_request_url, "acceptance pull-request URL")
        _origin(self.preview_url, "acceptance preview URL")
        if not _WORKFLOW.fullmatch(self.workflow_file):
            raise ValueError("Acceptance workflow is invalid")
        _text(self.automated_test_job, "acceptance test job", 200)
        _text(self.security_job, "acceptance security job", 200)
        if (
            not self.journeys
            or len(self.journeys) > 50
            or any(not isinstance(value, AcceptanceJourneySummary) for value in self.journeys)
            or len({value.journey_id for value in self.journeys}) != len(self.journeys)
        ):
            raise ValueError("Acceptance journey summaries are invalid")
        _utc(self.created_at, "acceptance creation time")
        _utc(self.updated_at, "acceptance update time")
        if self.updated_at < self.created_at:
            raise ValueError("Acceptance time regressed")
        if not isinstance(self.status, CustomerAcceptanceStatus):
            raise ValueError("Acceptance status is invalid")
        if self.approved_at is not None:
            _utc(self.approved_at, "acceptance approval time")
        if (self.approved_at is None) != (self.approved_by is None):
            raise ValueError("Acceptance approval identity is incomplete")
        if self.approved_by is not None:
            _id(self.approved_by, "acceptance approver")
        if self.status in {
            CustomerAcceptanceStatus.APPROVED,
            CustomerAcceptanceStatus.EXECUTION_IN_PROGRESS,
            CustomerAcceptanceStatus.EVIDENCE_READY,
        } and self.approved_at is None:
            raise ValueError("Acceptance transition requires customer approval")
        receipt = (
            self.workflow_run_id,
            self.workflow_run_url,
            self.deployment_revision,
            self.deployment_receipt_digest,
            self.browser_execution_digest,
            self.evidence_package_id,
            self.evidence_package_digest,
        )
        if self.status is CustomerAcceptanceStatus.EVIDENCE_READY:
            if any(value is None for value in receipt):
                raise ValueError("Acceptance evidence receipt is incomplete")
        elif any(value is not None for value in receipt):
            raise ValueError("Acceptance receipt exists before evidence is ready")
        if (
            self.status is CustomerAcceptanceStatus.RECONCILIATION_REQUIRED
        ) != (self.failure_classification is not None):
            raise ValueError("Acceptance reconciliation classification is invalid")
        if self.failure_classification is not None:
            _text(self.failure_classification, "acceptance failure classification", 200)

    @property
    def approval_digest(self) -> str:
        return _hash(
            {
                "acceptance_id": self.acceptance_id,
                "customer_id": self.customer_id,
                "request_id": self.request_id,
                "product_id": self.product_id,
                "delivery_id": self.delivery_id,
                "delivery_digest": self.delivery_digest,
                "delivery_review_digest": self.delivery_review_digest,
                "repository_full_name": self.repository_full_name,
                "base_branch": self.base_branch,
                "head_branch": self.head_branch,
                "commit_sha": self.commit_sha,
                "tree_sha": self.tree_sha,
                "pull_request_number": self.pull_request_number,
                "pull_request_url": self.pull_request_url,
                "configuration_digest": self.configuration_digest,
                "preview_environment_id": self.preview_environment_id,
                "preview_url": self.preview_url,
                "workflow_file": self.workflow_file,
                "automated_test_job": self.automated_test_job,
                "security_job": self.security_job,
                "browser_plan_id": self.browser_plan_id,
                "browser_plan_digest": self.browser_plan_digest,
                "journeys": tuple(asdict(value) for value in self.journeys),
            }
        )

    @property
    def digest(self) -> str:
        return _hash(asdict(self))


def acceptance_id_for(request_id: str) -> str:
    _id(request_id, "acceptance request ID")
    value = hashlib.sha256(f"customer-acceptance:{request_id}".encode()).hexdigest()
    return f"customer-acceptance-{value[:24]}"


def browser_plan_id_for(request_id: str) -> str:
    _id(request_id, "browser plan request ID")
    value = hashlib.sha256(f"customer-browser-plan:{request_id}".encode()).hexdigest()
    return f"customer-browser-{value[:24]}"


def canonical_origin(value: str) -> str:
    _origin(value, "preview origin")
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    rendered = f"[{host}]" if ":" in host else host
    default = (parsed.scheme == "https" and parsed.port == 443) or (
        parsed.scheme == "http" and parsed.port == 80
    )
    suffix = "" if parsed.port is None or default else f":{parsed.port}"
    return f"{parsed.scheme}://{rendered}{suffix}"


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json).encode()
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


def _commit(value: object, label: str) -> None:
    if not isinstance(value, str) or not _COMMIT.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} is invalid")


def _origin(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 2_048:
        raise ValueError(f"{label} is invalid")
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        parsed.scheme not in ({"http", "https"} if loopback else {"https"})
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} is unsafe")
    try:
        if parsed.port == 0:
            raise ValueError(f"{label} is unsafe")
    except ValueError as error:
        raise ValueError(f"{label} is unsafe") from error
    host = parsed.hostname or ""
    rendered = f"[{host}]" if ":" in host else host
    default = (parsed.scheme == "https" and parsed.port == 443) or (
        parsed.scheme == "http" and parsed.port == 80
    )
    suffix = "" if parsed.port is None or default else f":{parsed.port}"
    if value.rstrip("/") != f"{parsed.scheme}://{rendered}{suffix}":
        raise ValueError(f"{label} must be a canonical origin")


def _github_url(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("https://github.com/") or len(value) > 2_048:
        raise ValueError(f"{label} is invalid")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
