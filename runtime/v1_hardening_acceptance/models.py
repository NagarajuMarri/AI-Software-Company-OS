"""Exact-source models for ASCOS Day 37 hardening and founder acceptance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
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

VERIFY_SECURITY = "VERIFY_SECURITY_HARDENING"
VERIFY_BACKUP = "VERIFY_BACKUP_INTEGRITY"
VERIFY_RECOVERY = "VERIFY_DETERMINISTIC_RECOVERY"
VERIFY_AUDIT = "VERIFY_TAMPER_EVIDENT_AUDIT"
VERIFY_MONITORING = "VERIFY_OPERATIONAL_MONITORING"
VERIFY_DOCUMENTATION = "VERIFY_DOCUMENTATION_COMPLETENESS"
PREPARE_FOUNDER_UAT = "PREPARE_FOUNDER_UAT"
REPORT_V1_READINESS = "REPORT_V1_READINESS"

V1_HARDENING_ACTIONS = (
    VERIFY_SECURITY,
    VERIFY_BACKUP,
    VERIFY_RECOVERY,
    VERIFY_AUDIT,
    VERIFY_MONITORING,
    VERIFY_DOCUMENTATION,
    PREPARE_FOUNDER_UAT,
    REPORT_V1_READINESS,
)
V1_HARDENING_CAPABILITIES = (
    "exact-day36-pilot-binding",
    "security-hardening-verification",
    "verified-backup-and-recovery",
    "tamper-evident-audit-chain",
    "operational-monitoring-readiness",
    "documentation-completeness",
    "founder-uat-readiness-reporting",
)
V1_HARDENING_TOOL_IDS = (
    "PERSISTED_DAY36_PILOT_READER",
    "BOUNDED_HARDENING_ARTIFACT_STORE",
)

HARDENING_CONTROL_IDS = (
    "security",
    "backup",
    "recovery",
    "audit",
    "monitoring",
    "documentation",
    "founder-uat-readiness",
)
HARDENING_CONTROL_STATES = (
    "SECURITY_BASELINE_VERIFIED",
    "BACKUP_COPY_VERIFIED",
    "RECOVERY_DRILL_VERIFIED",
    "AUDIT_CHAIN_VERIFIED",
    "MONITORING_SIGNALS_HEALTHY",
    "DOCUMENTATION_BUNDLE_COMPLETE",
    "TECHNICALLY_READY_FOR_FOUNDER_UAT",
)
MONITORING_SIGNAL_IDS = (
    "runtime-health",
    "persistence-integrity",
    "outbox-backlog",
    "worker-liveness",
    "browser-journey-health",
)
DOCUMENTATION_IDS = (
    "architecture",
    "security-boundaries",
    "backup-recovery-runbook",
    "monitoring-runbook",
    "release-evidence",
    "operator-guide",
    "founder-uat-guide",
)

WORK_ORDER_STATUS = "AUTHORIZED_ASCOS_V1_HARDENING"
ARTIFACT_STATUS = "V1_HARDENING_COMPLETE_AWAITING_FOUNDER_UAT"
FOUNDER_UAT_STATUS = "PENDING_FOUNDER_ACCEPTANCE"
RELEASE_STATE = "BLOCKED_PENDING_FOUNDER_ACCEPTANCE"
PRODUCTION_STATE = "NOT_TARGETED"


def canonical_digest(value: object) -> str:
    encoded = json.dumps(_normalise(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _normalise(value: object) -> object:
    if is_dataclass(value):
        return _normalise(asdict(value))  # type: ignore[arg-type]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalise(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalise(item) for item in value]
    return value


def hardening_policy_digests_for(pilot_digest: str) -> tuple[str, ...]:
    _digest(pilot_digest, "Day 36 pilot")
    contracts = (
        ("security", "least privilege, exact sources, no secrets, zero elevated effects"),
        ("backup", "canonical mode-0600 primary and byte-identical verified backup"),
        ("recovery", "explicit restore from a verified backup with exact artifact equality"),
        ("audit", "ordered hash-chained immutable control receipts"),
        ("monitoring", MONITORING_SIGNAL_IDS),
        ("documentation", DOCUMENTATION_IDS),
        ("founder-uat-readiness", "real Chromium evidence; subjective decision remains human"),
    )
    return tuple(
        canonical_digest(
            {"control_id": control_id, "pilot_digest": pilot_digest, "contract": contract}
        )
        for control_id, contract in contracts
    )


def audit_digest_for(
    control_id: str,
    source_digest: str,
    state: str,
    evidence_ids: tuple[str, ...],
    verified_at: datetime,
    previous_audit_digest: str,
) -> str:
    return canonical_digest(
        {
            "control_id": control_id,
            "source_digest": source_digest,
            "state": state,
            "evidence_ids": evidence_ids,
            "verified_at": verified_at,
            "previous_audit_digest": previous_audit_digest,
        }
    )


@dataclass(frozen=True)
class V1HardeningWorkOrder:
    work_order_id: str
    tenant_id: str
    assignment_id: str
    pilot_id: str
    source_pilot_execution_id: str
    source_pilot_artifact_digest: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    preview_url: str
    journey_ids: tuple[str, ...]
    control_source_digests: tuple[str, ...]
    monitoring_signal_ids: tuple[str, ...]
    documentation_ids: tuple[str, ...]
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
            (self.assignment_id, "assignment"),
            (self.pilot_id, "pilot"),
            (self.source_pilot_execution_id, "source execution"),
        ):
            _identifier(value, f"V1 hardening {label} ID")
        _digest(self.source_pilot_artifact_digest, "V1 hardening source pilot")
        _repository(self.repository_full_name)
        _branch(self.feature_branch)
        _commit(self.approved_commit, "V1 hardening approved commit")
        _commit(self.approved_tree, "V1 hardening approved tree")
        if (
            isinstance(self.draft_pull_request_number, bool)
            or not isinstance(self.draft_pull_request_number, int)
            or self.draft_pull_request_number < 1
        ):
            raise ValueError("V1 hardening draft PR number is invalid")
        _preview_url(self.preview_url)
        _identifiers(self.journey_ids, "V1 hardening journey IDs", 1, 100)
        _digests(self.control_source_digests, "V1 hardening control digests", 7)
        if self.monitoring_signal_ids != MONITORING_SIGNAL_IDS:
            raise ValueError("V1 hardening monitoring profile is invalid")
        if self.documentation_ids != DOCUMENTATION_IDS:
            raise ValueError("V1 hardening documentation profile is invalid")
        _items(self.objectives, "V1 hardening objectives", 4, 12, 400)
        _items(self.acceptance_checks, "V1 hardening checks", 7, 24, 400)
        _items(self.constraints, "V1 hardening constraints", 8, 24, 400)
        _window(self.issued_at, self.expires_at, "V1 hardening work order")
        if self.status != WORK_ORDER_STATUS:
            raise ValueError("V1 hardening work-order status is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class V1HardeningAuthority:
    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    pilot_id: str
    work_order_digest: str
    source_pilot_artifact_digest: str
    control_source_digests: tuple[str, ...]
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_controls: int = 7
    max_monitoring_signals: int = 5
    max_documentation_records: int = 7
    max_backup_copies: int = 1
    max_recovery_drills: int = 1
    hardening_execution_allowed: bool = True
    founder_uat_preparation_allowed: bool = True
    founder_acceptance_allowed: bool = False
    repository_write_allowed: bool = False
    pull_request_mutation_allowed: bool = False
    merge_allowed: bool = False
    production_deployment_allowed: bool = False
    release_allowed: bool = False
    billing_allowed: bool = False
    risk_acceptance_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority"),
            (self.issuer_id, "issuer"),
            (self.tenant_id, "tenant"),
            (self.assignment_id, "assignment"),
            (self.pilot_id, "pilot"),
        ):
            _identifier(value, f"V1 hardening {label} ID")
        _digest(self.work_order_digest, "V1 hardening work-order")
        _digest(self.source_pilot_artifact_digest, "V1 hardening source pilot")
        _digests(self.control_source_digests, "V1 hardening control digests", 7)
        if self.allowed_action_ids != V1_HARDENING_ACTIONS:
            raise ValueError("V1 hardening authority action profile is invalid")
        if self.allowed_tool_ids != V1_HARDENING_TOOL_IDS:
            raise ValueError("V1 hardening authority tool profile is invalid")
        _window(self.issued_at, self.expires_at, "V1 hardening authority")
        if (
            self.max_controls != 7
            or self.max_monitoring_signals != 5
            or self.max_documentation_records != 7
            or self.max_backup_copies != 1
            or self.max_recovery_drills != 1
        ):
            raise ValueError("V1 hardening authority budget is invalid")
        if not (
            self.hardening_execution_allowed
            and self.founder_uat_preparation_allowed
            and not self.founder_acceptance_allowed
            and not self.repository_write_allowed
            and not self.pull_request_mutation_allowed
            and not self.merge_allowed
            and not self.production_deployment_allowed
            and not self.release_allowed
            and not self.billing_allowed
            and not self.risk_acceptance_allowed
        ):
            raise ValueError("V1 hardening authority crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class V1HardeningSourceSnapshot:
    pilot_id: str
    source_pilot_artifact_digest: str
    security_artifact_digest: str
    devops_artifact_digest: str
    documentation_artifact_digest: str
    runtime_acceptance_artifact_digest: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    preview_url: str
    journey_ids: tuple[str, ...]
    control_source_digests: tuple[str, ...]
    monitoring_signal_ids: tuple[str, ...]
    documentation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.pilot_id, "V1 hardening snapshot pilot ID")
        for value in (
            self.source_pilot_artifact_digest,
            self.security_artifact_digest,
            self.devops_artifact_digest,
            self.documentation_artifact_digest,
            self.runtime_acceptance_artifact_digest,
        ):
            _digest(value, "V1 hardening snapshot digest")
        _repository(self.repository_full_name)
        _branch(self.feature_branch)
        _commit(self.approved_commit, "V1 hardening snapshot commit")
        _commit(self.approved_tree, "V1 hardening snapshot tree")
        if (
            not isinstance(self.draft_pull_request_number, int)
            or self.draft_pull_request_number < 1
        ):
            raise ValueError("V1 hardening snapshot PR number is invalid")
        _preview_url(self.preview_url)
        _identifiers(self.journey_ids, "V1 hardening snapshot journey IDs", 1, 100)
        _digests(self.control_source_digests, "V1 hardening snapshot control digests", 7)
        if self.monitoring_signal_ids != MONITORING_SIGNAL_IDS:
            raise ValueError("V1 hardening snapshot monitoring profile is invalid")
        if self.documentation_ids != DOCUMENTATION_IDS:
            raise ValueError("V1 hardening snapshot documentation profile is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class HardeningControlReceipt:
    control_id: str
    source_digest: str
    state: str
    evidence_ids: tuple[str, ...]
    verified_at: datetime
    previous_audit_digest: str
    audit_digest: str

    def __post_init__(self) -> None:
        _identifier(self.control_id, "V1 hardening control ID")
        _digest(self.source_digest, "V1 hardening control source")
        _text(self.state, "V1 hardening control state", 160)
        _identifiers(self.evidence_ids, "V1 hardening evidence IDs", 1, 16)
        _utc(self.verified_at, "V1 hardening verification time")
        _digest(self.previous_audit_digest, "V1 hardening previous audit")
        _digest(self.audit_digest, "V1 hardening audit")
        expected = audit_digest_for(
            self.control_id,
            self.source_digest,
            self.state,
            self.evidence_ids,
            self.verified_at,
            self.previous_audit_digest,
        )
        if self.audit_digest != expected:
            raise ValueError("V1 hardening audit receipt is invalid")


@dataclass(frozen=True)
class MonitoringSignalReceipt:
    signal_id: str
    state: str
    evidence_digest: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.signal_id, "V1 hardening monitoring signal ID")
        if self.state != "HEALTHY":
            raise ValueError("V1 hardening monitoring signal is not healthy")
        _digest(self.evidence_digest, "V1 hardening monitoring evidence")
        _utc(self.observed_at, "V1 hardening monitoring time")


@dataclass(frozen=True)
class V1HardeningObservation:
    provider_id: str
    pilot_id: str
    snapshot_digest: str
    control_receipts: tuple[HardeningControlReceipt, ...]
    monitoring_receipts: tuple[MonitoringSignalReceipt, ...]
    documentation_ids: tuple[str, ...]
    backup_copy_count: int = 1
    recovery_drill_count: int = 1
    audit_entry_count: int = 7
    report_count: int = 1
    repository_write_count: int = 0
    pull_request_mutation_count: int = 0
    merge_count: int = 0
    production_deployment_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    risk_acceptance_count: int = 0
    founder_acceptance_count: int = 0

    def __post_init__(self) -> None:
        _identifier(self.provider_id, "V1 hardening provider ID")
        _identifier(self.pilot_id, "V1 hardening observation pilot ID")
        _digest(self.snapshot_digest, "V1 hardening observation snapshot")
        _typed(self.control_receipts, HardeningControlReceipt, "control receipts", 7)
        _typed(self.monitoring_receipts, MonitoringSignalReceipt, "monitoring receipts", 5)
        if tuple(item.control_id for item in self.control_receipts) != HARDENING_CONTROL_IDS:
            raise ValueError("V1 hardening control order is invalid")
        if tuple(item.state for item in self.control_receipts) != HARDENING_CONTROL_STATES:
            raise ValueError("V1 hardening control state is invalid")
        previous = "0" * 64
        for receipt in self.control_receipts:
            if receipt.previous_audit_digest != previous:
                raise ValueError("V1 hardening audit chain is invalid")
            previous = receipt.audit_digest
        if tuple(item.signal_id for item in self.monitoring_receipts) != MONITORING_SIGNAL_IDS:
            raise ValueError("V1 hardening monitoring order is invalid")
        if self.documentation_ids != DOCUMENTATION_IDS:
            raise ValueError("V1 hardening documentation result is invalid")
        if (
            self.backup_copy_count != 1
            or self.recovery_drill_count != 1
            or self.audit_entry_count != 7
            or self.report_count != 1
        ):
            raise ValueError("V1 hardening evidence count is invalid")
        if any(
            value != 0
            for value in (
                self.repository_write_count,
                self.pull_request_mutation_count,
                self.merge_count,
                self.production_deployment_count,
                self.release_count,
                self.billing_count,
                self.risk_acceptance_count,
                self.founder_acceptance_count,
            )
        ):
            raise ValueError("V1 hardening observation crossed a prohibited boundary")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(frozen=True)
class V1HardeningAcceptanceArtifact:
    artifact_id: str
    work_order_id: str
    work_order_digest: str
    authority_digest: str
    tenant_id: str
    execution_id: str
    assignment_id: str
    pilot_id: str
    source_pilot_execution_id: str
    source_pilot_artifact_digest: str
    security_artifact_digest: str
    devops_artifact_digest: str
    documentation_artifact_digest: str
    runtime_acceptance_artifact_digest: str
    repository_full_name: str
    feature_branch: str
    approved_commit: str
    approved_tree: str
    draft_pull_request_number: int
    preview_url: str
    journey_ids: tuple[str, ...]
    provider_id: str
    provider_output_digest: str
    control_receipts: tuple[HardeningControlReceipt, ...]
    monitoring_receipts: tuple[MonitoringSignalReceipt, ...]
    documentation_ids: tuple[str, ...]
    governance_capability_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    tool_ids: tuple[str, ...]
    backup_copy_count: int
    recovery_drill_count: int
    audit_entry_count: int
    monitoring_signal_count: int
    documentation_record_count: int
    founder_uat_journey_count: int
    report_count: int
    generated_at: datetime
    expires_at: datetime
    repository_write_count: int = 0
    pull_request_mutation_count: int = 0
    merge_count: int = 0
    production_deployment_count: int = 0
    release_count: int = 0
    billing_count: int = 0
    risk_acceptance_count: int = 0
    founder_acceptance_count: int = 0
    founder_uat_status: str = FOUNDER_UAT_STATUS
    release_state: str = RELEASE_STATE
    production_state: str = PRODUCTION_STATE
    status: str = ARTIFACT_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.artifact_id, "artifact"),
            (self.work_order_id, "work-order"),
            (self.tenant_id, "tenant"),
            (self.execution_id, "execution"),
            (self.assignment_id, "assignment"),
            (self.pilot_id, "pilot"),
            (self.source_pilot_execution_id, "source execution"),
            (self.provider_id, "provider"),
        ):
            _identifier(value, f"V1 hardening artifact {label} ID")
        for value in (
            self.work_order_digest,
            self.authority_digest,
            self.source_pilot_artifact_digest,
            self.security_artifact_digest,
            self.devops_artifact_digest,
            self.documentation_artifact_digest,
            self.runtime_acceptance_artifact_digest,
            self.provider_output_digest,
        ):
            _digest(value, "V1 hardening artifact digest")
        _repository(self.repository_full_name)
        _branch(self.feature_branch)
        _commit(self.approved_commit, "V1 hardening artifact commit")
        _commit(self.approved_tree, "V1 hardening artifact tree")
        if (
            not isinstance(self.draft_pull_request_number, int)
            or self.draft_pull_request_number < 1
        ):
            raise ValueError("V1 hardening artifact PR number is invalid")
        _preview_url(self.preview_url)
        _identifiers(self.journey_ids, "V1 hardening artifact journey IDs", 1, 100)
        _typed(self.control_receipts, HardeningControlReceipt, "control receipts", 7)
        _typed(self.monitoring_receipts, MonitoringSignalReceipt, "monitoring receipts", 5)
        V1HardeningObservation(
            provider_id=self.provider_id,
            pilot_id=self.pilot_id,
            snapshot_digest=canonical_digest(
                {
                    "pilot_id": self.pilot_id,
                    "source_pilot_artifact_digest": self.source_pilot_artifact_digest,
                    "security_artifact_digest": self.security_artifact_digest,
                    "devops_artifact_digest": self.devops_artifact_digest,
                    "documentation_artifact_digest": self.documentation_artifact_digest,
                    "runtime_acceptance_artifact_digest": self.runtime_acceptance_artifact_digest,
                    "repository_full_name": self.repository_full_name,
                    "feature_branch": self.feature_branch,
                    "approved_commit": self.approved_commit,
                    "approved_tree": self.approved_tree,
                    "draft_pull_request_number": self.draft_pull_request_number,
                    "preview_url": self.preview_url,
                    "journey_ids": self.journey_ids,
                    "control_source_digests": tuple(
                        item.source_digest for item in self.control_receipts
                    ),
                    "monitoring_signal_ids": tuple(
                        item.signal_id for item in self.monitoring_receipts
                    ),
                    "documentation_ids": self.documentation_ids,
                }
            ),
            control_receipts=self.control_receipts,
            monitoring_receipts=self.monitoring_receipts,
            documentation_ids=self.documentation_ids,
            backup_copy_count=self.backup_copy_count,
            recovery_drill_count=self.recovery_drill_count,
            audit_entry_count=self.audit_entry_count,
            report_count=self.report_count,
            repository_write_count=self.repository_write_count,
            pull_request_mutation_count=self.pull_request_mutation_count,
            merge_count=self.merge_count,
            production_deployment_count=self.production_deployment_count,
            release_count=self.release_count,
            billing_count=self.billing_count,
            risk_acceptance_count=self.risk_acceptance_count,
            founder_acceptance_count=self.founder_acceptance_count,
        )
        if (
            self.governance_capability_ids != V1_HARDENING_CAPABILITIES
            or self.action_ids != V1_HARDENING_ACTIONS
            or self.tool_ids != V1_HARDENING_TOOL_IDS
        ):
            raise ValueError("V1 hardening artifact authority profile is invalid")
        if (
            self.monitoring_signal_count != 5
            or self.documentation_record_count != 7
            or self.founder_uat_journey_count != len(self.journey_ids)
        ):
            raise ValueError("V1 hardening artifact evidence summary is invalid")
        _window(self.generated_at, self.expires_at, "V1 hardening artifact")
        if (
            self.founder_uat_status != FOUNDER_UAT_STATUS
            or self.release_state != RELEASE_STATE
            or self.production_state != PRODUCTION_STATE
            or self.status != ARTIFACT_STATUS
        ):
            raise ValueError("V1 hardening artifact terminal state is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(self)


def artifact_id_for(tenant_id: str, execution_id: str) -> str:
    _identifier(tenant_id, "V1 hardening tenant ID")
    _identifier(execution_id, "V1 hardening execution ID")
    return "v1-hardening-" + hashlib.sha256(f"{tenant_id}:{execution_id}".encode()).hexdigest()[:32]


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} digest is invalid")


def _digests(values: tuple[str, ...], label: str, count: int) -> None:
    if not isinstance(values, tuple) or len(values) != count or len(set(values)) != count:
        raise ValueError(f"{label} are invalid")
    for value in values:
        _digest(value, label)


def _commit(value: object, label: str) -> None:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")


def _branch(value: object) -> None:
    if (
        not isinstance(value, str)
        or _BRANCH.fullmatch(value) is None
        or value in {"main", "master"}
    ):
        raise ValueError("V1 hardening feature branch is invalid")


def _repository(value: object) -> None:
    if not isinstance(value, str) or _FULL_NAME.fullmatch(value) is None:
        raise ValueError("V1 hardening repository is invalid")


def _preview_url(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("V1 hardening preview URL is invalid")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("V1 hardening preview URL is invalid")


def _identifiers(values: tuple[str, ...], label: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len(set(values)) != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        _identifier(value, label)


def _items(
    values: tuple[str, ...], label: str, minimum: int, maximum: int, item_maximum: int
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len(set(values)) != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        _text(value, label, item_maximum)


def _text(value: object, label: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} is invalid")


def _typed(values: tuple[object, ...], kind: type, label: str, count: int) -> None:
    if (
        not isinstance(values, tuple)
        or len(values) != count
        or not all(isinstance(value, kind) for value in values)
    ):
        raise ValueError(f"V1 hardening {label} are invalid")


def _utc(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must use UTC")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")


def _window(issued_at: datetime, expires_at: datetime, label: str) -> None:
    _utc(issued_at, f"{label} issue time")
    _utc(expires_at, f"{label} expiry time")
    if not issued_at < expires_at <= issued_at + timedelta(hours=24):
        raise ValueError(f"{label} validity window is invalid")
