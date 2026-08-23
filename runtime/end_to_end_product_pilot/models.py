"""Exact-source models for ASCOS Day 36 first end-to-end product pilot."""

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

VERIFY_CUSTOMER_IDEA = "VERIFY_CUSTOMER_IDEA"
VERIFY_LOCKED_PRD = "VERIFY_LOCKED_PRD"
VERIFY_APPROVED_PLAN = "VERIFY_APPROVED_PLAN"
VERIFY_GOVERNED_AGENTS = "VERIFY_GOVERNED_AGENTS"
VERIFY_REVIEWED_CODE = "VERIFY_REVIEWED_CODE"
VERIFY_DRAFT_PR = "VERIFY_DRAFT_PR"
VERIFY_HEALTHY_PREVIEW = "VERIFY_HEALTHY_PREVIEW"
VERIFY_COMPLETE_RUNTIME = "VERIFY_COMPLETE_RUNTIME"
REPORT_PRODUCT_PILOT = "REPORT_PRODUCT_PILOT"

END_TO_END_PRODUCT_PILOT_ACTIONS = (
    VERIFY_CUSTOMER_IDEA,
    VERIFY_LOCKED_PRD,
    VERIFY_APPROVED_PLAN,
    VERIFY_GOVERNED_AGENTS,
    VERIFY_REVIEWED_CODE,
    VERIFY_DRAFT_PR,
    VERIFY_HEALTHY_PREVIEW,
    VERIFY_COMPLETE_RUNTIME,
    REPORT_PRODUCT_PILOT,
)
END_TO_END_PRODUCT_PILOT_CAPABILITIES = (
    "exact-customer-idea-binding",
    "locked-prd-and-roadmap-binding",
    "governed-agent-execution-binding",
    "reviewed-code-and-test-binding",
    "draft-pr-delivery-binding",
    "healthy-preview-binding",
    "complete-runtime-acceptance-binding",
    "founder-safe-pilot-reporting",
)
END_TO_END_PRODUCT_PILOT_TOOL_IDS = ("PERSISTED_PILOT_SOURCE_READER",)

PILOT_STAGE_IDS = (
    "customer-idea",
    "locked-prd",
    "approved-plan",
    "governed-agents",
    "reviewed-code-and-tests",
    "draft-pull-request",
    "healthy-preview",
    "complete-runtime-acceptance",
)
PILOT_STAGE_STATES = (
    "EXACT_CUSTOMER_IDEA_VERIFIED",
    "EXACT_LOCKED_PRD_VERIFIED",
    "EXACT_APPROVED_ROADMAP_VERIFIED",
    "GOVERNED_AGENT_CHAIN_VERIFIED",
    "EXACT_REVIEWED_CODE_AND_TESTS_VERIFIED",
    "EXACT_OPEN_DRAFT_PR_VERIFIED",
    "EXACT_HEALTHY_PREVIEW_VERIFIED",
    "ALL_DECLARED_RUNTIME_JOURNEYS_PASSED",
)

WORK_ORDER_STATUS = "AUTHORIZED_FIRST_END_TO_END_PRODUCT_PILOT"
ARTIFACT_STATUS = "PILOT_COMPLETED_AWAITING_FOUNDER_ACCEPTANCE"
PRODUCTION_STATE = "NOT_TARGETED"
PILOT_STATUS = "FIRST_END_TO_END_FIXTURE_PILOT_COMPLETED"


@dataclass(frozen=True)
class EndToEndProductPilotWorkOrder:
    work_order_id: str
    tenant_id: str
    customer_id: str
    request_id: str
    opportunity_id: str
    assignment_id: str
    pilot_id: str
    source_request_digest: str
    prd_digest: str
    prd_approval_digest: str
    roadmap_digest: str
    roadmap_approval_digest: str
    preview_artifact_digest: str
    runtime_acceptance_artifact_digest: str
    product_binding_digest: str
    customer_product_id: str
    runtime_product_id: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    preview_environment_id: str
    preview_url: str
    journey_ids: tuple[str, ...]
    objectives: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    constraints: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    status: str = WORK_ORDER_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.customer_id, "customer"),
            (self.request_id, "request"),
            (self.opportunity_id, "opportunity"),
            (self.assignment_id, "assignment"),
            (self.pilot_id, "pilot"),
            (self.customer_product_id, "customer product"),
            (self.runtime_product_id, "runtime product"),
            (self.preview_environment_id, "preview environment"),
        ):
            _identifier(value, f"product-pilot {label} ID")
        for value, label in (
            (self.source_request_digest, "source request"),
            (self.prd_digest, "PRD"),
            (self.prd_approval_digest, "PRD approval"),
            (self.roadmap_digest, "roadmap"),
            (self.roadmap_approval_digest, "roadmap approval"),
            (self.preview_artifact_digest, "preview artifact"),
            (self.runtime_acceptance_artifact_digest, "runtime acceptance artifact"),
            (self.product_binding_digest, "product binding"),
        ):
            _digest(value, f"product-pilot {label} digest")
        if not isinstance(self.repository_full_name, str) or _FULL_NAME.fullmatch(
            self.repository_full_name
        ) is None:
            raise ValueError("Product-pilot repository full name is invalid")
        _branch(self.feature_branch)
        _commit(self.approved_commit, "product-pilot approved commit")
        _commit(self.approved_tree, "product-pilot approved tree")
        if (
            isinstance(self.draft_pull_request_number, bool)
            or not isinstance(self.draft_pull_request_number, int)
            or self.draft_pull_request_number < 1
        ):
            raise ValueError("Product-pilot draft PR number is invalid")
        _preview_url(self.preview_url)
        _identifiers(self.journey_ids, "product-pilot journey IDs", 1, 100)
        _items(self.objectives, "product-pilot objectives", 4, 12, 400)
        _items(self.acceptance_checks, "product-pilot checks", 8, 24, 400)
        _items(self.constraints, "product-pilot constraints", 8, 24, 400)
        _utc(self.issued_at, "product-pilot work-order issue time")
        _utc(self.expires_at, "product-pilot work-order expiry time")
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("Product-pilot work-order validity window is invalid")
        if self.status != WORK_ORDER_STATUS:
            raise ValueError("Product-pilot work-order status is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class EndToEndProductPilotAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    pilot_id: str
    work_order_digest: str
    source_request_digest: str
    roadmap_approval_digest: str
    runtime_acceptance_artifact_digest: str
    product_binding_digest: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_source_records: int = 7
    max_stage_receipts: int = 8
    max_journeys: int = 100
    pilot_execution_allowed: bool = True
    repository_write_allowed: bool = False
    pull_request_mutation_allowed: bool = False
    preview_mutation_allowed: bool = False
    merge_allowed: bool = False
    production_deployment_allowed: bool = False
    release_allowed: bool = False
    billing_allowed: bool = False
    risk_acceptance_allowed: bool = False
    day37_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
            (self.pilot_id, "pilot"),
        ):
            _identifier(value, f"product-pilot {label} ID")
        for value, label in (
            (self.work_order_digest, "work-order"),
            (self.source_request_digest, "source request"),
            (self.roadmap_approval_digest, "roadmap approval"),
            (self.runtime_acceptance_artifact_digest, "runtime acceptance artifact"),
            (self.product_binding_digest, "product binding"),
        ):
            _digest(value, f"product-pilot authority {label} digest")
        if self.allowed_action_ids != END_TO_END_PRODUCT_PILOT_ACTIONS:
            raise ValueError("Product-pilot authority action profile is invalid")
        if self.allowed_tool_ids != END_TO_END_PRODUCT_PILOT_TOOL_IDS:
            raise ValueError("Product-pilot authority tool profile is invalid")
        _utc(self.issued_at, "product-pilot authority issue time")
        _utc(self.expires_at, "product-pilot authority expiry time")
        if not self.issued_at < self.expires_at <= self.issued_at + timedelta(hours=24):
            raise ValueError("Product-pilot authority validity window is invalid")
        for budget, expected, label in (
            (self.max_source_records, 7, "source budget"),
            (self.max_stage_receipts, 8, "stage budget"),
        ):
            if budget != expected:
                raise ValueError(f"Product-pilot authority {label} is invalid")
        if (
            isinstance(self.max_journeys, bool)
            or not isinstance(self.max_journeys, int)
            or not 1 <= self.max_journeys <= 100
        ):
            raise ValueError("Product-pilot authority journey budget is invalid")
        if not (
            self.pilot_execution_allowed
            and not self.repository_write_allowed
            and not self.pull_request_mutation_allowed
            and not self.preview_mutation_allowed
            and not self.merge_allowed
            and not self.production_deployment_allowed
            and not self.release_allowed
            and not self.billing_allowed
            and not self.risk_acceptance_allowed
            and not self.day37_allowed
        ):
            raise ValueError("Product-pilot authority crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["issued_at"] = self.issued_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class ProductPilotSourceSnapshot:
    pilot_id: str
    source_request_digest: str
    prd_digest: str
    prd_approval_digest: str
    roadmap_digest: str
    roadmap_approval_digest: str
    orchestration_artifact_digest: str
    coding_review_artifact_digest: str
    github_delivery_artifact_digest: str
    preview_artifact_digest: str
    runtime_acceptance_artifact_digest: str
    product_binding_digest: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    preview_environment_id: str
    preview_url: str
    journey_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.pilot_id, "product-pilot snapshot ID")
        for value in (
            self.source_request_digest,
            self.prd_digest,
            self.prd_approval_digest,
            self.roadmap_digest,
            self.roadmap_approval_digest,
            self.orchestration_artifact_digest,
            self.coding_review_artifact_digest,
            self.github_delivery_artifact_digest,
            self.preview_artifact_digest,
            self.runtime_acceptance_artifact_digest,
            self.product_binding_digest,
        ):
            _digest(value, "product-pilot snapshot source digest")
        if not isinstance(self.repository_full_name, str) or _FULL_NAME.fullmatch(
            self.repository_full_name
        ) is None:
            raise ValueError("Product-pilot snapshot repository is invalid")
        _branch(self.feature_branch)
        _commit(self.approved_commit, "product-pilot snapshot commit")
        _commit(self.approved_tree, "product-pilot snapshot tree")
        if not isinstance(self.draft_pull_request_number, int) or self.draft_pull_request_number < 1:
            raise ValueError("Product-pilot snapshot PR number is invalid")
        _identifier(self.preview_environment_id, "product-pilot snapshot environment ID")
        _preview_url(self.preview_url)
        _identifiers(self.journey_ids, "product-pilot snapshot journey IDs", 1, 100)

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True)
class ProductPilotStageReceipt:
    stage_id: str
    source_digest: str
    state: str
    evidence_count: int
    completed_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.stage_id, "product-pilot stage ID")
        _digest(self.source_digest, "product-pilot stage source digest")
        _text(self.state, "product-pilot stage state", 160)
        if (
            isinstance(self.evidence_count, bool)
            or not isinstance(self.evidence_count, int)
            or self.evidence_count < 1
        ):
            raise ValueError("Product-pilot stage evidence count is invalid")
        _utc(self.completed_at, "product-pilot stage completion time")


@dataclass(frozen=True)
class EndToEndProductPilotObservation:
    provider_id: str
    pilot_id: str
    snapshot_digest: str
    stage_receipts: tuple[ProductPilotStageReceipt, ...]
    source_record_count: int
    completed_journey_count: int
    passed_journey_count: int
    report_count: int = 1
    repository_write_count: int = 0
    pull_request_mutation_count: int = 0
    preview_mutation_count: int = 0
    merge_count: int = 0
    production_deployment_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    risk_acceptance_count: int = 0
    day37_action_count: int = 0

    def __post_init__(self) -> None:
        _identifier(self.provider_id, "product-pilot provider ID")
        _identifier(self.pilot_id, "product-pilot observation ID")
        _digest(self.snapshot_digest, "product-pilot snapshot digest")
        _typed(self.stage_receipts, ProductPilotStageReceipt, "product-pilot stage receipts", 8, 8)
        if tuple(item.stage_id for item in self.stage_receipts) != PILOT_STAGE_IDS:
            raise ValueError("Product-pilot stage order is invalid")
        if tuple(item.state for item in self.stage_receipts) != PILOT_STAGE_STATES:
            raise ValueError("Product-pilot stage state is invalid")
        if self.source_record_count != 7 or self.report_count != 1:
            raise ValueError("Product-pilot source or report count is invalid")
        if (
            not isinstance(self.completed_journey_count, int)
            or self.completed_journey_count < 1
            or self.passed_journey_count != self.completed_journey_count
        ):
            raise ValueError("Product-pilot journey result is incomplete")
        if any(
            value != 0
            for value in (
                self.repository_write_count,
                self.pull_request_mutation_count,
                self.preview_mutation_count,
                self.merge_count,
                self.production_deployment_count,
                self.release_count,
                self.billing_count,
                self.risk_acceptance_count,
                self.day37_action_count,
            )
        ):
            raise ValueError("Product-pilot observation crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        for record, receipt in zip(payload["stage_receipts"], self.stage_receipts, strict=True):
            record["completed_at"] = receipt.completed_at.isoformat()
        return canonical_digest(payload)


@dataclass(frozen=True)
class EndToEndProductPilotArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    authority_digest: str
    tenant_id: str
    customer_id: str
    request_id: str
    opportunity_id: str
    execution_id: str
    assignment_id: str
    pilot_id: str
    customer_product_id: str
    runtime_product_id: str
    product_binding_digest: str
    source_request_digest: str
    prd_digest: str
    prd_approval_digest: str
    roadmap_digest: str
    roadmap_approval_digest: str
    orchestration_artifact_digest: str
    workspace_artifact_digest: str
    coding_review_artifact_digest: str
    qa_artifact_digest: str
    security_artifact_digest: str
    github_delivery_artifact_digest: str
    devops_artifact_digest: str
    preview_artifact_digest: str
    runtime_acceptance_artifact_digest: str
    runtime_configuration_digest: str
    acceptance_profile_digest: str
    browser_plan_digest: str
    browser_execution_digest: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    preview_environment_id: str
    preview_url: str
    journey_ids: tuple[str, ...]
    provider_id: str
    provider_output_digest: str
    stage_receipts: tuple[ProductPilotStageReceipt, ...]
    governance_capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    source_record_count: int
    completed_journey_count: int
    passed_journey_count: int
    report_count: int
    generated_at: datetime
    expires_at: datetime
    repository_write_count: int = 0
    pull_request_mutation_count: int = 0
    preview_mutation_count: int = 0
    merge_count: int = 0
    production_deployment_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    risk_acceptance_count: int = 0
    day37_action_count: int = 0
    production_state: str = PRODUCTION_STATE
    status: str = ARTIFACT_STATUS
    pilot_status: str = PILOT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.artifact_id, "artifact"), (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"), (self.customer_id, "customer"),
            (self.request_id, "request"), (self.opportunity_id, "opportunity"),
            (self.execution_id, "execution"), (self.assignment_id, "assignment"),
            (self.pilot_id, "pilot"), (self.customer_product_id, "customer product"),
            (self.runtime_product_id, "runtime product"),
            (self.preview_environment_id, "preview environment"),
        ):
            _identifier(value, f"product-pilot artifact {label} ID")
        for value in (
            self.work_order_digest, self.authority_digest, self.product_binding_digest,
            self.source_request_digest, self.prd_digest, self.prd_approval_digest,
            self.roadmap_digest, self.roadmap_approval_digest,
            self.orchestration_artifact_digest, self.workspace_artifact_digest,
            self.coding_review_artifact_digest, self.qa_artifact_digest,
            self.security_artifact_digest, self.github_delivery_artifact_digest,
            self.devops_artifact_digest, self.preview_artifact_digest,
            self.runtime_acceptance_artifact_digest, self.runtime_configuration_digest,
            self.acceptance_profile_digest, self.browser_plan_digest,
            self.browser_execution_digest, self.provider_output_digest,
        ):
            _digest(value, "product-pilot artifact digest")
        if not isinstance(self.repository_full_name, str) or _FULL_NAME.fullmatch(
            self.repository_full_name
        ) is None:
            raise ValueError("Product-pilot artifact repository is invalid")
        _branch(self.feature_branch)
        _commit(self.approved_commit, "product-pilot artifact commit")
        _commit(self.approved_tree, "product-pilot artifact tree")
        if not isinstance(self.draft_pull_request_number, int) or self.draft_pull_request_number < 1:
            raise ValueError("Product-pilot artifact PR number is invalid")
        _preview_url(self.preview_url)
        _identifiers(self.journey_ids, "product-pilot artifact journey IDs", 1, 100)
        if (
            self.governance_capability_ids != END_TO_END_PRODUCT_PILOT_CAPABILITIES
            or self.action_ids != END_TO_END_PRODUCT_PILOT_ACTIONS
            or self.tool_ids != END_TO_END_PRODUCT_PILOT_TOOL_IDS
        ):
            raise ValueError("Product-pilot artifact authority profile is invalid")
        observation = EndToEndProductPilotObservation(
            provider_id=self.provider_id,
            pilot_id=self.pilot_id,
            snapshot_digest=canonical_digest({
                "pilot_id": self.pilot_id,
                "source_request_digest": self.source_request_digest,
                "prd_digest": self.prd_digest,
                "prd_approval_digest": self.prd_approval_digest,
                "roadmap_digest": self.roadmap_digest,
                "roadmap_approval_digest": self.roadmap_approval_digest,
                "orchestration_artifact_digest": self.orchestration_artifact_digest,
                "coding_review_artifact_digest": self.coding_review_artifact_digest,
                "github_delivery_artifact_digest": self.github_delivery_artifact_digest,
                "preview_artifact_digest": self.preview_artifact_digest,
                "runtime_acceptance_artifact_digest": self.runtime_acceptance_artifact_digest,
                "product_binding_digest": self.product_binding_digest,
                "repository_full_name": self.repository_full_name,
                "feature_branch": self.feature_branch,
                "approved_commit": self.approved_commit,
                "approved_tree": self.approved_tree,
                "draft_pull_request_number": self.draft_pull_request_number,
                "preview_environment_id": self.preview_environment_id,
                "preview_url": self.preview_url,
                "journey_ids": self.journey_ids,
            }),
            stage_receipts=self.stage_receipts,
            source_record_count=self.source_record_count,
            completed_journey_count=self.completed_journey_count,
            passed_journey_count=self.passed_journey_count,
            report_count=self.report_count,
            repository_write_count=self.repository_write_count,
            pull_request_mutation_count=self.pull_request_mutation_count,
            preview_mutation_count=self.preview_mutation_count,
            merge_count=self.merge_count,
            production_deployment_count=self.production_deployment_count,
            release_count=self.release_count,
            billing_count=self.billing_count,
            risk_acceptance_count=self.risk_acceptance_count,
            day37_action_count=self.day37_action_count,
        )
        if observation.digest != self.provider_output_digest:
            raise ValueError("Product-pilot provider output digest is invalid")
        _utc(self.generated_at, "product-pilot artifact generation time")
        _utc(self.expires_at, "product-pilot artifact expiry time")
        if not self.generated_at < self.expires_at <= self.generated_at + timedelta(days=1):
            raise ValueError("Product-pilot artifact lifetime is invalid")
        if (
            self.production_state != PRODUCTION_STATE
            or self.status != ARTIFACT_STATUS
            or self.pilot_status != PILOT_STATUS
        ):
            raise ValueError("Product-pilot artifact terminal state is invalid")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        for record, receipt in zip(payload["stage_receipts"], self.stage_receipts, strict=True):
            record["completed_at"] = receipt.completed_at.isoformat()
        return canonical_digest(payload)


def product_binding_digest_for(
    pilot_id: str,
    customer_product_id: str,
    runtime_product_id: str,
    source_request_digest: str,
) -> str:
    for value, label in (
        (pilot_id, "pilot"), (customer_product_id, "customer product"),
        (runtime_product_id, "runtime product"),
    ):
        _identifier(value, f"product binding {label} ID")
    _digest(source_request_digest, "product binding source digest")
    return canonical_digest({
        "pilot_id": pilot_id,
        "customer_product_id": customer_product_id,
        "runtime_product_id": runtime_product_id,
        "source_request_digest": source_request_digest,
    })


def artifact_id_for(execution_id: str) -> str:
    _identifier(execution_id, "product-pilot execution ID")
    return "end-to-end-product-pilot-" + hashlib.sha256(execution_id.encode()).hexdigest()[:24]


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _commit(value: object, label: str) -> None:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _branch(value: object) -> None:
    if (
        not isinstance(value, str)
        or _BRANCH.fullmatch(value) is None
        or not value.startswith("agent/")
        or value.endswith(("/", "."))
    ):
        raise ValueError("Product-pilot feature branch is invalid")


def _preview_url(value: object) -> None:
    if not isinstance(value, str) or len(value) > 500 or value != value.strip():
        raise ValueError("Product-pilot preview URL is invalid")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Product-pilot preview URL must be credential-free HTTPS")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Product-pilot preview URL must be an origin")


def _identifiers(values: object, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len(values) != len(set(values))
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        _identifier(value, label)


def _items(values: object, label: str, minimum: int, maximum: int, item_limit: int) -> None:
    if not isinstance(values, tuple) or not minimum <= len(values) <= maximum:
        raise ValueError(f"{label} are invalid")
    if len({value.casefold() for value in values if isinstance(value, str)}) != len(values):
        raise ValueError(f"{label} are duplicated")
    for value in values:
        _text(value, label, item_limit)


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str) or value != value.strip() or not value
        or len(value) > maximum or "\x00" in value
    ):
        raise ValueError(f"{label} is invalid")


def _typed(values: object, expected: type, label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or any(not isinstance(value, expected) for value in values)
    ):
        raise ValueError(f"{label} are invalid")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
