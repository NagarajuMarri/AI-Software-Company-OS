"""Exact-source models for ASCOS Day 34 isolated preview deployment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
from urllib.parse import urlparse

from runtime.workforce_devops import PREVIEW_ENVIRONMENT_CLASS


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_BRANCH = re.compile(r"^(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_FULL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")

VERIFY_APPROVED_PREVIEW_SOURCE = "VERIFY_APPROVED_PREVIEW_SOURCE"
RESERVE_ISOLATED_PREVIEW = "RESERVE_ISOLATED_PREVIEW"
DEPLOY_APPROVED_COMMIT = "DEPLOY_APPROVED_COMMIT"
APPLY_PREVIEW_MIGRATIONS = "APPLY_PREVIEW_MIGRATIONS"
VERIFY_PREVIEW_HEALTH = "VERIFY_PREVIEW_HEALTH"
ENABLE_PREVIEW_MONITORING = "ENABLE_PREVIEW_MONITORING"
REPORT_PREVIEW_STATUS = "REPORT_PREVIEW_STATUS"

PREVIEW_DEPLOYMENT_ACTIONS = (
    VERIFY_APPROVED_PREVIEW_SOURCE,
    RESERVE_ISOLATED_PREVIEW,
    DEPLOY_APPROVED_COMMIT,
    APPLY_PREVIEW_MIGRATIONS,
    VERIFY_PREVIEW_HEALTH,
    ENABLE_PREVIEW_MONITORING,
    REPORT_PREVIEW_STATUS,
)
PREVIEW_DEPLOYMENT_CAPABILITIES = (
    "exact-day33-delivery-binding",
    "exact-day28-devops-plan-binding",
    "isolated-preview-reservation",
    "approved-commit-preview-deployment",
    "preview-only-migration-execution",
    "preview-health-and-monitoring-verification",
    "rollback-readiness-reporting",
)
PREVIEW_DEPLOYMENT_TOOL_IDS = (
    "SCOPED_PREVIEW_PLATFORM",
    "OPAQUE_PREVIEW_CREDENTIALS",
)

WORK_ORDER_STATUS = "AUTHORIZED_ISOLATED_PREVIEW_DEPLOYMENT"
ARTIFACT_STATUS = "PREVIEW_DEPLOYED_AWAITING_RUNTIME_ACCEPTANCE"
SOURCE_STATE = "EXACT_DAY33_DELIVERY_VERIFIED"
PULL_REQUEST_STATE = "OPEN_DRAFT_UNMERGED"
ENVIRONMENT_STATE = "ACTIVE_HEALTHY_ISOLATED_PREVIEW"
DEPLOYMENT_STATE = "DEPLOYED_EXACT_APPROVED_COMMIT"
MIGRATION_STATE = "APPLIED_AND_VERIFIED_IN_PREVIEW"
MONITORING_STATE = "ENABLED_FOR_PREVIEW"
ROLLBACK_STATE = "READY_NOT_EXECUTED"
PRODUCTION_STATE = "NOT_TARGETED"
PILOT_STATUS = "NOT_SELECTED"


@dataclass(frozen=True)
class PreviewDeploymentWorkOrder:
    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    github_delivery_artifact_digest: str
    devops_artifact_digest: str
    repository_id: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    draft_pull_request_digest: str
    preview_environment_id: str
    preview_url: str
    preview_plan_digest: str
    migration_plan_digest: str
    deployment_plan_digest: str
    monitoring_plan_digest: str
    rollback_plan_digest: str
    configuration_digest: str
    secret_reference_ids: tuple[str, ...]
    health_check_urls: tuple[str, ...]
    objectives: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    preview_ttl_minutes: int = 120
    environment_class: str = PREVIEW_ENVIRONMENT_CLASS
    status: str = WORK_ORDER_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.assignment_id, "assignment"),
            (self.repository_id, "repository"),
            (self.preview_environment_id, "environment"),
        ):
            _identifier(value, f"preview {label} ID")
        for value, label in (
            (self.github_delivery_artifact_digest, "GitHub-delivery artifact"),
            (self.devops_artifact_digest, "DevOps artifact"),
            (self.draft_pull_request_digest, "draft pull-request"),
            (self.preview_plan_digest, "preview plan"),
            (self.migration_plan_digest, "migration plan"),
            (self.deployment_plan_digest, "deployment plan"),
            (self.monitoring_plan_digest, "monitoring plan"),
            (self.rollback_plan_digest, "rollback plan"),
            (self.configuration_digest, "configuration"),
        ):
            _digest(value, f"preview {label} digest")
        if not isinstance(self.repository_full_name, str) or _FULL_NAME.fullmatch(
            self.repository_full_name
        ) is None:
            raise ValueError("Preview repository full name is invalid")
        _branch(self.feature_branch, "preview feature branch")
        if not self.feature_branch.startswith("agent/"):
            raise ValueError("Preview source must be an isolated feature branch")
        _commit(self.approved_commit, "preview approved commit")
        _commit(self.approved_tree, "preview approved tree")
        if (
            isinstance(self.draft_pull_request_number, bool)
            or not isinstance(self.draft_pull_request_number, int)
            or self.draft_pull_request_number < 1
        ):
            raise ValueError("Preview draft pull-request number is invalid")
        _preview_url(self.preview_url, "preview URL")
        if self.environment_class != PREVIEW_ENVIRONMENT_CLASS:
            raise ValueError("Preview deployment cannot target a production environment")
        _identifiers(self.secret_reference_ids, "preview secret references", 0, 8)
        _urls(self.health_check_urls, self.preview_url)
        _items(self.objectives, "preview objectives", 4, 10, 400)
        _items(self.acceptance_checks, "preview acceptance checks", 8, 18, 400)
        _items(self.constraints, "preview constraints", 8, 18, 400)
        _utc(self.issued_at, "preview work-order issue time")
        _utc(self.expires_at, "preview work-order expiry time")
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("Preview work-order validity window is invalid")
        if (
            isinstance(self.preview_ttl_minutes, bool)
            or not isinstance(self.preview_ttl_minutes, int)
            or not 15 <= self.preview_ttl_minutes <= 1_440
        ):
            raise ValueError("Preview TTL is invalid")
        if self.status != WORK_ORDER_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Preview work-order state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class PreviewDeploymentAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    work_order_digest: str
    github_delivery_artifact_digest: str
    devops_artifact_digest: str
    repository_id: str
    approved_commit: str
    preview_environment_id: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_platform_calls: int = 6
    max_health_checks: int = 4
    max_secret_references: int = 4
    preview_deployment_allowed: bool = True
    scoped_credential_handle_allowed: bool = True
    migration_allowed: bool = True
    monitoring_allowed: bool = True
    production_deployment_allowed: bool = False
    merge_allowed: bool = False
    release_allowed: bool = False
    billing_allowed: bool = False
    pilot_selection_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
            (self.repository_id, "repository"),
            (self.preview_environment_id, "environment"),
        ):
            _identifier(value, f"preview {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order"),
            (self.github_delivery_artifact_digest, "GitHub-delivery artifact"),
            (self.devops_artifact_digest, "DevOps artifact"),
        ):
            _digest(value, f"preview authority {label} digest")
        _commit(self.approved_commit, "preview authority commit")
        if self.allowed_action_ids != PREVIEW_DEPLOYMENT_ACTIONS:
            raise ValueError("Preview authority action profile is invalid")
        if self.allowed_tool_ids != PREVIEW_DEPLOYMENT_TOOL_IDS:
            raise ValueError("Preview authority tool profile is invalid")
        _utc(self.issued_at, "preview authority issue time")
        _utc(self.expires_at, "preview authority expiry time")
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("Preview authority validity window is invalid")
        for budget, minimum, maximum, label in (
            (self.max_platform_calls, 3, 12, "platform-call budget"),
            (self.max_health_checks, 2, 8, "health-check budget"),
            (self.max_secret_references, 0, 8, "secret-reference budget"),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or not minimum <= budget <= maximum
            ):
                raise ValueError(f"Preview authority {label} is invalid")
        if not (
            self.preview_deployment_allowed
            and self.scoped_credential_handle_allowed
            and self.migration_allowed
            and self.monitoring_allowed
            and not self.production_deployment_allowed
            and not self.merge_allowed
            and not self.release_allowed
            and not self.billing_allowed
            and not self.pilot_selection_allowed
        ):
            raise ValueError("Preview authority crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class PreviewHealthReceipt:
    check_id: str
    url: str
    status_code: int
    response_digest: str
    checked_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.check_id, "preview health-check ID")
        _preview_url(self.url, "preview health-check URL", allow_path=True)
        if (
            isinstance(self.status_code, bool)
            or not isinstance(self.status_code, int)
            or self.status_code != 200
        ):
            raise ValueError("Preview health check did not return HTTP 200")
        _digest(self.response_digest, "preview health response digest")
        _utc(self.checked_at, "preview health-check time")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["checked_at"] = self.checked_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class PreviewDeploymentObservation:
    provider_id: str
    environment_id: str
    environment_class: str
    preview_url: str
    deployed_commit: str
    deployed_tree: str
    deployment_revision: str
    configuration_digest: str
    health_receipts: tuple[PreviewHealthReceipt, ...]
    platform_call_count: int
    credential_handle_count: int
    deployment_count: int = 1
    migration_count: int = 1
    monitoring_configuration_count: int = 1
    rollback_count: int = 0
    production_deployment_count: int = 0
    merge_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    secret_value_exposure_count: int = 0
    unapproved_network_call_count: int = 0
    general_command_count: int = 0

    def __post_init__(self) -> None:
        _identifier(self.provider_id, "preview provider ID")
        _identifier(self.environment_id, "preview environment ID")
        if self.environment_class != PREVIEW_ENVIRONMENT_CLASS:
            raise ValueError("Preview observation targeted a non-preview environment")
        _preview_url(self.preview_url, "observed preview URL")
        _commit(self.deployed_commit, "preview deployed commit")
        _commit(self.deployed_tree, "preview deployed tree")
        _identifier(self.deployment_revision, "preview deployment revision")
        _digest(self.configuration_digest, "preview configuration digest")
        _typed(self.health_receipts, PreviewHealthReceipt, "preview health receipts", 2, 8)
        if len({item.url for item in self.health_receipts}) != len(self.health_receipts):
            raise ValueError("Preview health receipts are duplicated")
        if not 3 <= self.platform_call_count <= 12:
            raise ValueError("Preview platform-call count is invalid")
        if not 0 <= self.credential_handle_count <= 8:
            raise ValueError("Preview credential-handle count is invalid")
        if (
            self.deployment_count,
            self.migration_count,
            self.monitoring_configuration_count,
        ) != (1, 1, 1):
            raise ValueError("Preview deployment effects are incomplete")
        zero_fields = (
            self.rollback_count,
            self.production_deployment_count,
            self.merge_count,
            self.release_count,
            self.billing_count,
            self.secret_value_exposure_count,
            self.unapproved_network_call_count,
            self.general_command_count,
        )
        if any(value != 0 for value in zero_fields):
            raise ValueError("Preview observation crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        for record, receipt in zip(payload["health_receipts"], self.health_receipts, strict=True):
            record["checked_at"] = receipt.checked_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class PreviewDeploymentArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    github_delivery_artifact_id: str
    github_delivery_artifact_digest: str
    devops_artifact_id: str
    devops_artifact_digest: str
    coding_review_artifact_digest: str
    workspace_artifact_digest: str
    orchestration_artifact_digest: str
    qa_artifact_digest: str
    security_artifact_digest: str
    repository_id: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    draft_pull_request_digest: str
    preview_environment_id: str
    preview_url: str
    preview_plan_digest: str
    migration_plan_digest: str
    deployment_plan_digest: str
    monitoring_plan_digest: str
    rollback_plan_digest: str
    configuration_digest: str
    secret_reference_count: int
    provider_id: str
    authority_digest: str
    capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    environment_class: str
    deployed_commit: str
    deployed_tree: str
    deployment_revision: str
    health_receipts: tuple[PreviewHealthReceipt, ...]
    platform_call_count: int
    credential_handle_count: int
    provider_output_digest: str
    generated_at: datetime
    expires_at: datetime
    deployment_count: int = 1
    migration_count: int = 1
    monitoring_configuration_count: int = 1
    rollback_count: int = 0
    production_deployment_count: int = 0
    merge_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    secret_value_exposure_count: int = 0
    unapproved_network_call_count: int = 0
    general_command_count: int = 0
    source_state: str = SOURCE_STATE
    pull_request_state: str = PULL_REQUEST_STATE
    environment_state: str = ENVIRONMENT_STATE
    deployment_state: str = DEPLOYMENT_STATE
    migration_state: str = MIGRATION_STATE
    monitoring_state: str = MONITORING_STATE
    rollback_state: str = ROLLBACK_STATE
    production_state: str = PRODUCTION_STATE
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
            (self.github_delivery_artifact_id, "GitHub-delivery artifact"),
            (self.devops_artifact_id, "DevOps artifact"),
            (self.repository_id, "repository"),
            (self.preview_environment_id, "environment"),
        ):
            _identifier(value, f"preview artifact {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order"),
            (self.github_delivery_artifact_digest, "GitHub-delivery artifact"),
            (self.devops_artifact_digest, "DevOps artifact"),
            (self.coding_review_artifact_digest, "coding-review artifact"),
            (self.workspace_artifact_digest, "workspace artifact"),
            (self.orchestration_artifact_digest, "orchestration artifact"),
            (self.qa_artifact_digest, "QA artifact"),
            (self.security_artifact_digest, "Security artifact"),
            (self.draft_pull_request_digest, "draft pull-request"),
            (self.preview_plan_digest, "preview plan"),
            (self.migration_plan_digest, "migration plan"),
            (self.deployment_plan_digest, "deployment plan"),
            (self.monitoring_plan_digest, "monitoring plan"),
            (self.rollback_plan_digest, "rollback plan"),
            (self.configuration_digest, "configuration"),
            (self.authority_digest, "authority"),
            (self.provider_output_digest, "provider output"),
        ):
            _digest(value, f"preview artifact {label} digest")
        if not isinstance(self.repository_full_name, str) or _FULL_NAME.fullmatch(
            self.repository_full_name
        ) is None:
            raise ValueError("Preview artifact repository full name is invalid")
        _branch(self.feature_branch, "preview artifact feature branch")
        _commit(self.approved_commit, "preview artifact approved commit")
        _commit(self.approved_tree, "preview artifact approved tree")
        _preview_url(self.preview_url, "preview artifact URL")
        if (
            isinstance(self.draft_pull_request_number, bool)
            or not isinstance(self.draft_pull_request_number, int)
            or self.draft_pull_request_number < 1
        ):
            raise ValueError("Preview artifact pull-request number is invalid")
        if not 0 <= self.secret_reference_count <= 8:
            raise ValueError("Preview artifact secret-reference count is invalid")
        if (
            self.capability_ids != PREVIEW_DEPLOYMENT_CAPABILITIES
            or self.action_ids != PREVIEW_DEPLOYMENT_ACTIONS
            or self.tool_ids != PREVIEW_DEPLOYMENT_TOOL_IDS
        ):
            raise ValueError("Preview artifact profile is invalid")
        observation = PreviewDeploymentObservation(
            provider_id=self.provider_id,
            environment_id=self.preview_environment_id,
            environment_class=self.environment_class,
            preview_url=self.preview_url,
            deployed_commit=self.deployed_commit,
            deployed_tree=self.deployed_tree,
            deployment_revision=self.deployment_revision,
            configuration_digest=self.configuration_digest,
            health_receipts=self.health_receipts,
            platform_call_count=self.platform_call_count,
            credential_handle_count=self.credential_handle_count,
            deployment_count=self.deployment_count,
            migration_count=self.migration_count,
            monitoring_configuration_count=self.monitoring_configuration_count,
            rollback_count=self.rollback_count,
            production_deployment_count=self.production_deployment_count,
            merge_count=self.merge_count,
            release_count=self.release_count,
            billing_count=self.billing_count,
            secret_value_exposure_count=self.secret_value_exposure_count,
            unapproved_network_call_count=self.unapproved_network_call_count,
            general_command_count=self.general_command_count,
        )
        if observation.digest != self.provider_output_digest:
            raise ValueError("Preview provider output digest is invalid")
        _utc(self.generated_at, "preview artifact generation time")
        _utc(self.expires_at, "preview artifact expiry time")
        if not self.generated_at < self.expires_at <= self.generated_at + timedelta(days=1):
            raise ValueError("Preview artifact lifetime is invalid")
        if (
            self.source_state != SOURCE_STATE
            or self.pull_request_state != PULL_REQUEST_STATE
            or self.environment_state != ENVIRONMENT_STATE
            or self.deployment_state != DEPLOYMENT_STATE
            or self.migration_state != MIGRATION_STATE
            or self.monitoring_state != MONITORING_STATE
            or self.rollback_state != ROLLBACK_STATE
            or self.production_state != PRODUCTION_STATE
            or self.status != ARTIFACT_STATUS
            or self.pilot_status != PILOT_STATUS
        ):
            raise ValueError("Preview artifact state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        for record, receipt in zip(payload["health_receipts"], self.health_receipts, strict=True):
            record["checked_at"] = receipt.checked_at.isoformat()
        return canonical_digest(payload)


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "preview execution ID")
    return f"preview-deployment-{hashlib.sha256(execution_id.encode()).hexdigest()[:24]}"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _identifiers(values: object, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len(set(values)) != len(values)
        or tuple(sorted(values)) != values
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        _identifier(value, label)


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _commit(value: object, label: str) -> None:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _branch(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or _BRANCH.fullmatch(value) is None
        or value.endswith(("/", "."))
        or value in {"HEAD", "FETCH_HEAD", "ORIG_HEAD", "main", "master", "production"}
    ):
        raise ValueError(f"{label} is invalid")


def _preview_url(value: object, label: str, *, allow_path: bool = False) -> None:
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError(f"{label} is invalid")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".preview.invalid")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or (not allow_path and parsed.path not in {"", "/"})
        or (allow_path and (not parsed.path.startswith("/") or ".." in parsed.path))
    ):
        raise ValueError(f"{label} is invalid")


def _urls(values: object, preview_url: str) -> None:
    if (
        not isinstance(values, tuple)
        or not 2 <= len(values) <= 8
        or len(set(values)) != len(values)
        or tuple(sorted(values)) != values
    ):
        raise ValueError("Preview health-check URLs are invalid")
    origin = preview_url.rstrip("/")
    for value in values:
        _preview_url(value, "preview health-check URL", allow_path=True)
        if not value.startswith(f"{origin}/"):
            raise ValueError("Preview health check escaped the approved origin")


def _items(values: object, label: str, minimum: int, maximum: int, item_limit: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len(set(values)) != len(values)
        or any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > item_limit
            or any(ord(character) < 32 for character in value)
            for value in values
        )
    ):
        raise ValueError(f"{label} are invalid")


def _typed(values: object, expected: type, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or any(not isinstance(value, expected) for value in values)
    ):
        raise ValueError(f"{label} are invalid")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} is invalid")
