"""Exact-source models for ASCOS Day 35 complete runtime acceptance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
from urllib.parse import urlparse


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_BRANCH = re.compile(r"^(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_FULL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")

VERIFY_APPROVED_PREVIEW = "VERIFY_APPROVED_PREVIEW"
VERIFY_RUNTIME_CONTRACT = "VERIFY_RUNTIME_CONTRACT"
RESOLVE_OPAQUE_LOGIN_INPUTS = "RESOLVE_OPAQUE_LOGIN_INPUTS"
OPEN_ISOLATED_CHROMIUM = "OPEN_ISOLATED_CHROMIUM"
AUTHENTICATE_PREVIEW_USER = "AUTHENTICATE_PREVIEW_USER"
EXECUTE_MODULE_JOURNEYS = "EXECUTE_MODULE_JOURNEYS"
CAPTURE_RUNTIME_EVIDENCE = "CAPTURE_RUNTIME_EVIDENCE"
REPORT_RUNTIME_ACCEPTANCE = "REPORT_RUNTIME_ACCEPTANCE"

COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS = (
    VERIFY_APPROVED_PREVIEW,
    VERIFY_RUNTIME_CONTRACT,
    RESOLVE_OPAQUE_LOGIN_INPUTS,
    OPEN_ISOLATED_CHROMIUM,
    AUTHENTICATE_PREVIEW_USER,
    EXECUTE_MODULE_JOURNEYS,
    CAPTURE_RUNTIME_EVIDENCE,
    REPORT_RUNTIME_ACCEPTANCE,
)
COMPLETE_RUNTIME_ACCEPTANCE_CAPABILITIES = (
    "exact-day34-preview-binding",
    "exact-runtime-configuration-binding",
    "locked-browser-plan-binding",
    "opaque-preview-authentication",
    "module-specific-chromium-journeys",
    "secret-safe-browser-evidence",
    "terminal-runtime-acceptance-reporting",
)
COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS = (
    "ISOLATED_CHROMIUM",
    "OPAQUE_RUNTIME_CREDENTIALS",
)

WORK_ORDER_STATUS = "AUTHORIZED_COMPLETE_RUNTIME_ACCEPTANCE"
ARTIFACT_STATUS = "RUNTIME_ACCEPTANCE_PASSED_AWAITING_FOUNDER_UX_ACCEPTANCE"
PREVIEW_STATE = "EXACT_DAY34_HEALTHY_PREVIEW_VERIFIED"
AUTHENTICATION_STATE = "PREVIEW_AUTHENTICATION_VERIFIED"
JOURNEY_STATE = "ALL_DECLARED_MODULE_JOURNEYS_PASSED"
BROWSER_STATE = "ISOLATED_CHROMIUM_EVIDENCE_COMPLETE"
PRODUCTION_STATE = "NOT_TARGETED"
PILOT_STATUS = "NOT_SELECTED"


@dataclass(frozen=True)
class CompleteRuntimeAcceptanceWorkOrder:
    work_order_id: str
    tenant_id: str
    opportunity_id: str
    assignment_id: str
    preview_artifact_digest: str
    product_id: str
    runtime_configuration_id: str
    runtime_configuration_revision: int
    runtime_configuration_digest: str
    acceptance_run_id: str
    acceptance_profile_id: str
    acceptance_profile_version: str
    acceptance_profile_digest: str
    browser_plan_id: str
    browser_plan_digest: str
    repository_id: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    preview_environment_id: str
    preview_url: str
    deployment_revision: str
    preview_configuration_digest: str
    capability_ids: tuple[str, ...]
    journey_ids: tuple[str, ...]
    authentication_journey_id: str
    login_secret_reference_ids: tuple[str, ...]
    objectives: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    status: str = WORK_ORDER_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.opportunity_id, "opportunity"),
            (self.assignment_id, "assignment"),
            (self.product_id, "product"),
            (self.runtime_configuration_id, "runtime configuration"),
            (self.acceptance_run_id, "acceptance run"),
            (self.acceptance_profile_id, "acceptance profile"),
            (self.browser_plan_id, "browser plan"),
            (self.repository_id, "repository"),
            (self.preview_environment_id, "preview environment"),
            (self.deployment_revision, "deployment revision"),
        ):
            _identifier(value, f"runtime-acceptance {label} ID")
        for value, label in (
            (self.preview_artifact_digest, "preview artifact"),
            (self.runtime_configuration_digest, "runtime configuration"),
            (self.acceptance_profile_digest, "acceptance profile"),
            (self.browser_plan_digest, "browser plan"),
            (self.preview_configuration_digest, "preview configuration"),
        ):
            _digest(value, f"runtime-acceptance {label} digest")
        if (
            isinstance(self.runtime_configuration_revision, bool)
            or not isinstance(self.runtime_configuration_revision, int)
            or self.runtime_configuration_revision < 1
        ):
            raise ValueError("Runtime-acceptance configuration revision is invalid")
        _text(self.acceptance_profile_version, "runtime-acceptance profile version", 128)
        if not isinstance(self.repository_full_name, str) or _FULL_NAME.fullmatch(
            self.repository_full_name
        ) is None:
            raise ValueError("Runtime-acceptance repository full name is invalid")
        _branch(self.feature_branch, "runtime-acceptance feature branch")
        if not self.feature_branch.startswith("agent/"):
            raise ValueError("Runtime acceptance requires an isolated feature branch")
        _commit(self.approved_commit, "runtime-acceptance approved commit")
        _commit(self.approved_tree, "runtime-acceptance approved tree")
        _preview_url(self.preview_url, "runtime-acceptance preview URL")
        _identifiers(self.capability_ids, "runtime-acceptance capability IDs", 1, 32)
        _identifiers(self.journey_ids, "runtime-acceptance journey IDs", 1, 100)
        _identifier(self.authentication_journey_id, "authentication journey ID")
        if self.authentication_journey_id not in self.journey_ids:
            raise ValueError("Authentication journey must be declared by the work order")
        _identifiers(
            self.login_secret_reference_ids,
            "runtime-acceptance login secret references",
            1,
            8,
            sorted_values=True,
        )
        _items(self.objectives, "runtime-acceptance objectives", 4, 10, 400)
        _items(self.acceptance_checks, "runtime-acceptance checks", 8, 20, 400)
        _items(self.constraints, "runtime-acceptance constraints", 8, 20, 400)
        _utc(self.issued_at, "runtime-acceptance work-order issue time")
        _utc(self.expires_at, "runtime-acceptance work-order expiry time")
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("Runtime-acceptance work-order validity window is invalid")
        if self.status != WORK_ORDER_STATUS or self.pilot_status != PILOT_STATUS:
            raise ValueError("Runtime-acceptance work-order state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class CompleteRuntimeAcceptanceAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    work_order_digest: str
    preview_artifact_digest: str
    product_id: str
    acceptance_run_id: str
    browser_plan_digest: str
    approved_commit: str
    preview_environment_id: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_browser_launches: int = 1
    max_journeys: int = 100
    max_secret_references: int = 8
    preview_browser_allowed: bool = True
    scoped_login_credentials_allowed: bool = True
    repository_write_allowed: bool = False
    preview_mutation_allowed: bool = False
    production_deployment_allowed: bool = False
    merge_allowed: bool = False
    release_allowed: bool = False
    billing_allowed: bool = False
    risk_acceptance_allowed: bool = False
    pilot_selection_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
            (self.product_id, "product"),
            (self.acceptance_run_id, "acceptance run"),
            (self.preview_environment_id, "preview environment"),
        ):
            _identifier(value, f"runtime-acceptance {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order"),
            (self.preview_artifact_digest, "preview artifact"),
            (self.browser_plan_digest, "browser plan"),
        ):
            _digest(value, f"runtime-acceptance authority {label} digest")
        _commit(self.approved_commit, "runtime-acceptance authority commit")
        if self.allowed_action_ids != COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS:
            raise ValueError("Runtime-acceptance authority action profile is invalid")
        if self.allowed_tool_ids != COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS:
            raise ValueError("Runtime-acceptance authority tool profile is invalid")
        _utc(self.issued_at, "runtime-acceptance authority issue time")
        _utc(self.expires_at, "runtime-acceptance authority expiry time")
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("Runtime-acceptance authority validity window is invalid")
        for budget, minimum, maximum, label in (
            (self.max_browser_launches, 1, 1, "browser-launch budget"),
            (self.max_journeys, 1, 100, "journey budget"),
            (self.max_secret_references, 1, 8, "secret-reference budget"),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or not minimum <= budget <= maximum
            ):
                raise ValueError(f"Runtime-acceptance authority {label} is invalid")
        if not (
            self.preview_browser_allowed
            and self.scoped_login_credentials_allowed
            and not self.repository_write_allowed
            and not self.preview_mutation_allowed
            and not self.production_deployment_allowed
            and not self.merge_allowed
            and not self.release_allowed
            and not self.billing_allowed
            and not self.risk_acceptance_allowed
            and not self.pilot_selection_allowed
        ):
            raise ValueError("Runtime-acceptance authority crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class RuntimeJourneyReceipt:
    journey_id: str
    capability_id: str
    title: str
    outcome: str
    evidence_count: int
    evidence_digest: str
    screenshot_digest: str
    completed_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.journey_id, "runtime journey ID")
        _identifier(self.capability_id, "runtime capability ID")
        _text(self.title, "runtime journey title", 512)
        if self.outcome != "PASS":
            raise ValueError("Runtime journey did not pass")
        if (
            isinstance(self.evidence_count, bool)
            or not isinstance(self.evidence_count, int)
            or not 4 <= self.evidence_count <= 32
        ):
            raise ValueError("Runtime journey evidence count is invalid")
        _digest(self.evidence_digest, "runtime journey evidence")
        _digest(self.screenshot_digest, "runtime journey screenshot")
        _utc(self.completed_at, "runtime journey completion time")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["completed_at"] = self.completed_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class RuntimeAcceptanceObservation:
    provider_id: str
    product_id: str
    acceptance_run_id: str
    browser_plan_id: str
    browser_plan_digest: str
    runtime_configuration_digest: str
    acceptance_profile_digest: str
    approved_commit: str
    preview_environment_id: str
    preview_url: str
    browser_execution_digest: str
    journey_receipts: tuple[RuntimeJourneyReceipt, ...]
    browser_launch_count: int
    authenticated_session_count: int
    evidence_artifact_count: int
    screenshot_count: int
    console_error_count: int = 0
    network_failure_count: int = 0
    raw_secret_exposure_count: int = 0
    repository_write_count: int = 0
    preview_mutation_count: int = 0
    production_deployment_count: int = 0
    merge_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    pilot_selection_count: int = 0

    def __post_init__(self) -> None:
        for value, label in (
            (self.provider_id, "runtime provider"),
            (self.product_id, "runtime product"),
            (self.acceptance_run_id, "runtime acceptance run"),
            (self.browser_plan_id, "runtime browser plan"),
            (self.preview_environment_id, "runtime preview environment"),
        ):
            _identifier(value, f"{label} ID")
        for value, label in (
            (self.browser_plan_digest, "runtime browser plan"),
            (self.runtime_configuration_digest, "runtime configuration"),
            (self.acceptance_profile_digest, "runtime acceptance profile"),
            (self.browser_execution_digest, "runtime browser execution"),
        ):
            _digest(value, f"{label} digest")
        _commit(self.approved_commit, "runtime observed commit")
        _preview_url(self.preview_url, "runtime observed preview URL")
        _typed(self.journey_receipts, RuntimeJourneyReceipt, "runtime journey receipts", 1, 100)
        journey_ids = tuple(item.journey_id for item in self.journey_receipts)
        if len(journey_ids) != len(set(journey_ids)):
            raise ValueError("Runtime journey receipts are duplicated")
        if self.browser_launch_count != 1:
            raise ValueError("Runtime acceptance requires exactly one browser launch")
        if self.authenticated_session_count != len(self.journey_receipts):
            raise ValueError("Runtime authenticated-session count is invalid")
        if self.evidence_artifact_count != sum(
            item.evidence_count for item in self.journey_receipts
        ):
            raise ValueError("Runtime evidence-artifact count is invalid")
        if self.screenshot_count != len(self.journey_receipts):
            raise ValueError("Every runtime journey requires one screenshot")
        zero_fields = (
            self.console_error_count,
            self.network_failure_count,
            self.raw_secret_exposure_count,
            self.repository_write_count,
            self.preview_mutation_count,
            self.production_deployment_count,
            self.merge_count,
            self.release_count,
            self.billing_count,
            self.pilot_selection_count,
        )
        if any(value != 0 for value in zero_fields):
            raise ValueError("Runtime observation crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        for record, receipt in zip(
            payload["journey_receipts"], self.journey_receipts, strict=True
        ):
            record["completed_at"] = receipt.completed_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class CompleteRuntimeAcceptanceArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    tenant_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    preview_artifact_id: str
    preview_artifact_digest: str
    github_delivery_artifact_digest: str
    devops_artifact_digest: str
    coding_review_artifact_digest: str
    workspace_artifact_digest: str
    orchestration_artifact_digest: str
    qa_artifact_digest: str
    security_artifact_digest: str
    product_id: str
    repository_id: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    preview_environment_id: str
    preview_url: str
    deployment_revision: str
    runtime_configuration_id: str
    runtime_configuration_revision: int
    runtime_configuration_digest: str
    acceptance_run_id: str
    acceptance_profile_id: str
    acceptance_profile_version: str
    acceptance_profile_digest: str
    browser_plan_id: str
    browser_plan_digest: str
    browser_execution_digest: str
    authority_digest: str
    provider_id: str
    provider_output_digest: str
    capability_ids: tuple[str, ...]
    journey_ids: tuple[str, ...]
    journey_receipts: tuple[RuntimeJourneyReceipt, ...]
    governance_capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    browser_launch_count: int
    authenticated_session_count: int
    evidence_artifact_count: int
    screenshot_count: int
    generated_at: datetime
    expires_at: datetime
    console_error_count: int = 0
    network_failure_count: int = 0
    raw_secret_exposure_count: int = 0
    repository_write_count: int = 0
    preview_mutation_count: int = 0
    production_deployment_count: int = 0
    merge_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    pilot_selection_count: int = 0
    preview_state: str = PREVIEW_STATE
    authentication_state: str = AUTHENTICATION_STATE
    journey_state: str = JOURNEY_STATE
    browser_state: str = BROWSER_STATE
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
            (self.preview_artifact_id, "preview artifact"),
            (self.product_id, "product"),
            (self.repository_id, "repository"),
            (self.preview_environment_id, "preview environment"),
            (self.deployment_revision, "deployment revision"),
            (self.runtime_configuration_id, "runtime configuration"),
            (self.acceptance_run_id, "acceptance run"),
            (self.acceptance_profile_id, "acceptance profile"),
            (self.browser_plan_id, "browser plan"),
        ):
            _identifier(value, f"runtime artifact {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order"),
            (self.preview_artifact_digest, "preview artifact"),
            (self.github_delivery_artifact_digest, "GitHub-delivery artifact"),
            (self.devops_artifact_digest, "DevOps artifact"),
            (self.coding_review_artifact_digest, "coding-review artifact"),
            (self.workspace_artifact_digest, "workspace artifact"),
            (self.orchestration_artifact_digest, "orchestration artifact"),
            (self.qa_artifact_digest, "QA artifact"),
            (self.security_artifact_digest, "Security artifact"),
            (self.runtime_configuration_digest, "runtime configuration"),
            (self.acceptance_profile_digest, "acceptance profile"),
            (self.browser_plan_digest, "browser plan"),
            (self.browser_execution_digest, "browser execution"),
            (self.authority_digest, "authority"),
            (self.provider_output_digest, "provider output"),
        ):
            _digest(value, f"runtime artifact {label} digest")
        if not isinstance(self.repository_full_name, str) or _FULL_NAME.fullmatch(
            self.repository_full_name
        ) is None:
            raise ValueError("Runtime artifact repository full name is invalid")
        _branch(self.feature_branch, "runtime artifact feature branch")
        _commit(self.approved_commit, "runtime artifact approved commit")
        _commit(self.approved_tree, "runtime artifact approved tree")
        _preview_url(self.preview_url, "runtime artifact preview URL")
        _text(self.acceptance_profile_version, "runtime artifact profile version", 128)
        if (
            isinstance(self.runtime_configuration_revision, bool)
            or not isinstance(self.runtime_configuration_revision, int)
            or self.runtime_configuration_revision < 1
        ):
            raise ValueError("Runtime artifact configuration revision is invalid")
        _identifiers(self.capability_ids, "runtime artifact capability IDs", 1, 32)
        _identifiers(self.journey_ids, "runtime artifact journey IDs", 1, 100)
        if (
            self.governance_capability_ids != COMPLETE_RUNTIME_ACCEPTANCE_CAPABILITIES
            or self.action_ids != COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS
            or self.tool_ids != COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS
        ):
            raise ValueError("Runtime artifact authority profile is invalid")
        observation = RuntimeAcceptanceObservation(
            provider_id=self.provider_id,
            product_id=self.product_id,
            acceptance_run_id=self.acceptance_run_id,
            browser_plan_id=self.browser_plan_id,
            browser_plan_digest=self.browser_plan_digest,
            runtime_configuration_digest=self.runtime_configuration_digest,
            acceptance_profile_digest=self.acceptance_profile_digest,
            approved_commit=self.approved_commit,
            preview_environment_id=self.preview_environment_id,
            preview_url=self.preview_url,
            browser_execution_digest=self.browser_execution_digest,
            journey_receipts=self.journey_receipts,
            browser_launch_count=self.browser_launch_count,
            authenticated_session_count=self.authenticated_session_count,
            evidence_artifact_count=self.evidence_artifact_count,
            screenshot_count=self.screenshot_count,
            console_error_count=self.console_error_count,
            network_failure_count=self.network_failure_count,
            raw_secret_exposure_count=self.raw_secret_exposure_count,
            repository_write_count=self.repository_write_count,
            preview_mutation_count=self.preview_mutation_count,
            production_deployment_count=self.production_deployment_count,
            merge_count=self.merge_count,
            release_count=self.release_count,
            billing_count=self.billing_count,
            pilot_selection_count=self.pilot_selection_count,
        )
        if observation.digest != self.provider_output_digest:
            raise ValueError("Runtime provider output digest is invalid")
        if tuple(item.journey_id for item in self.journey_receipts) != self.journey_ids:
            raise ValueError("Runtime journey receipts do not match the declared journey order")
        if tuple(dict.fromkeys(item.capability_id for item in self.journey_receipts)) != self.capability_ids:
            raise ValueError("Runtime receipts do not match the declared capability order")
        _utc(self.generated_at, "runtime artifact generation time")
        _utc(self.expires_at, "runtime artifact expiry time")
        if not self.generated_at < self.expires_at <= self.generated_at + timedelta(days=1):
            raise ValueError("Runtime artifact lifetime is invalid")
        if (
            self.preview_state != PREVIEW_STATE
            or self.authentication_state != AUTHENTICATION_STATE
            or self.journey_state != JOURNEY_STATE
            or self.browser_state != BROWSER_STATE
            or self.production_state != PRODUCTION_STATE
            or self.status != ARTIFACT_STATUS
            or self.pilot_status != PILOT_STATUS
        ):
            raise ValueError("Runtime artifact state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        for record, receipt in zip(
            payload["journey_receipts"], self.journey_receipts, strict=True
        ):
            record["completed_at"] = receipt.completed_at.isoformat()
        return canonical_digest(payload)


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "runtime-acceptance execution ID")
    return "complete-runtime-acceptance-" + hashlib.sha256(
        execution_id.encode()
    ).hexdigest()[:24]


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _identifiers(
    values: object,
    label: str,
    minimum: int,
    maximum: int,
    *,
    sorted_values: bool = False,
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len(set(values)) != len(values)
        or (sorted_values and tuple(sorted(values)) != values)
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


def _preview_url(value: object, label: str) -> None:
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
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(f"{label} is invalid")


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{label} is invalid")


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
