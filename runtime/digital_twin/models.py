"""Immutable authority, assignment, and evidence models for Digital Twins."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import re

from runtime.agents.role import AgentRole, validate_agent_role


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ACTION = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SENSITIVE_KEY = re.compile(
    r"(^|[_.-])(password|passwd|token|secret|credential|api[_-]?key)($|[_.-])",
    re.IGNORECASE,
)

MAX_AUTHORITY_LIFETIME = timedelta(hours=24)
MAX_CONTEXT_ENTRIES = 32
MAX_CONTEXT_BYTES = 16_000
MAX_TOOL_IDS = 16
MAX_CAPABILITY_IDS = 32
MAX_TOOL_CALLS = 32
MIN_OUTPUT_BYTES = 256
MAX_OUTPUT_BYTES = 128_000

EXECUTE_ASSIGNED_WORK = "EXECUTE_ASSIGNED_WORK"
USE_ASSIGNED_TOOL = "USE_ASSIGNED_TOOL"
PRODUCE_EXECUTION_EVIDENCE = "PRODUCE_EXECUTION_EVIDENCE"

FORBIDDEN_DAY22_ACTIONS = frozenset(
    {
        "APPROVE",
        "BILL",
        "CHANGE_GOVERNANCE",
        "COMMIT",
        "DEPLOY",
        "MERGE",
        "RELEASE",
        "SELECT_PILOT_PRODUCT",
        "WRITE_PRODUCT_REPOSITORY",
    }
)


class DigitalTwinExecutionStatus(str, Enum):
    """Terminal outcome recorded by the Day 22 runtime."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ToolCallOutcome(str, Enum):
    """Sanitized outcome of one gateway-governed tool call."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ContextValue:
    """One bounded non-secret context value supplied to a provider."""

    key: str
    value: str

    def __post_init__(self) -> None:
        validate_public_field(self.key, self.value, label="context")


@dataclass(frozen=True)
class DelegatedAuthority:
    """Exact, expiring authority granted for one assignment and Digital Twin."""

    authority_id: str
    issuer_id: str
    tenant_id: str
    assignment_id: str
    twin_id: str
    business_role: AgentRole
    objective_digest: str
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    max_tool_calls: int
    max_output_bytes: int
    live_provider_allowed: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.authority_id, "authority ID"),
            (self.issuer_id, "authority issuer ID"),
            (self.tenant_id, "authority tenant ID"),
            (self.assignment_id, "authority assignment ID"),
            (self.twin_id, "authority Digital Twin ID"),
        ):
            validate_identifier(value, label)
        validate_agent_role(self.business_role)
        validate_digest(self.objective_digest, "authority objective digest")
        _unique_actions(self.allowed_action_ids)
        _unique_identifiers(
            self.allowed_tool_ids,
            "authority allowed tool IDs",
            MAX_TOOL_IDS,
        )
        if EXECUTE_ASSIGNED_WORK not in self.allowed_action_ids:
            raise ValueError("Digital Twin authority must allow assigned work execution")
        if PRODUCE_EXECUTION_EVIDENCE not in self.allowed_action_ids:
            raise ValueError("Digital Twin authority must allow execution evidence")
        if self.allowed_tool_ids and USE_ASSIGNED_TOOL not in self.allowed_action_ids:
            raise ValueError("Digital Twin tool authority is missing")
        forbidden = FORBIDDEN_DAY22_ACTIONS.intersection(self.allowed_action_ids)
        if forbidden:
            raise ValueError("Day 22 authority contains a prohibited action")
        validate_utc(self.issued_at, "authority issued time")
        validate_utc(self.expires_at, "authority expiry time")
        if not self.issued_at < self.expires_at:
            raise ValueError("Digital Twin authority must expire after it is issued")
        if self.expires_at - self.issued_at > MAX_AUTHORITY_LIFETIME:
            raise ValueError("Digital Twin authority lifetime exceeds 24 hours")
        if (
            not isinstance(self.max_tool_calls, int)
            or isinstance(self.max_tool_calls, bool)
            or not 0 <= self.max_tool_calls <= MAX_TOOL_CALLS
        ):
            raise ValueError("Digital Twin tool-call budget is invalid")
        if self.allowed_tool_ids and self.max_tool_calls < 1:
            raise ValueError("Assigned tools require a positive tool-call budget")
        if not self.allowed_tool_ids and self.max_tool_calls != 0:
            raise ValueError("Tool-call budget requires at least one allowed tool")
        if (
            not isinstance(self.max_output_bytes, int)
            or isinstance(self.max_output_bytes, bool)
            or not MIN_OUTPUT_BYTES <= self.max_output_bytes <= MAX_OUTPUT_BYTES
        ):
            raise ValueError("Digital Twin output budget is invalid")
        if not isinstance(self.live_provider_allowed, bool):
            raise ValueError("Digital Twin live-provider authority must be boolean")

    @property
    def digest(self) -> str:
        return canonical_digest(_authority_record(self))


@dataclass(frozen=True)
class DigitalTwinDefinition:
    """One provider-neutral fulfilment identity aligned to one Business Role."""

    twin_id: str
    display_name: str
    business_role: AgentRole
    provider_id: str
    capability_ids: tuple[str, ...]
    approved_tool_ids: tuple[str, ...]
    enabled: bool = True

    def __post_init__(self) -> None:
        validate_identifier(self.twin_id, "Digital Twin ID")
        validate_text(self.display_name, "Digital Twin display name", 200)
        validate_agent_role(self.business_role)
        validate_identifier(self.provider_id, "Digital Twin provider ID")
        _unique_identifiers(
            self.capability_ids,
            "Digital Twin capability IDs",
            MAX_CAPABILITY_IDS,
        )
        _unique_identifiers(
            self.approved_tool_ids,
            "Digital Twin approved tool IDs",
            MAX_TOOL_IDS,
        )
        if not isinstance(self.enabled, bool):
            raise ValueError("Digital Twin enabled state must be boolean")

    @property
    def digest(self) -> str:
        return canonical_digest(_definition_record(self))


@dataclass(frozen=True)
class DigitalTwinAssignment:
    """A bounded unit of responsibility addressed to one Digital Twin."""

    assignment_id: str
    tenant_id: str
    twin_id: str
    business_role: AgentRole
    objective: str
    context: tuple[ContextValue, ...]
    required_capability_ids: tuple[str, ...]
    requested_tool_ids: tuple[str, ...]
    authority_id: str
    authority_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.assignment_id, "Digital Twin assignment ID"),
            (self.tenant_id, "Digital Twin assignment tenant ID"),
            (self.twin_id, "Digital Twin assignment twin ID"),
            (self.authority_id, "Digital Twin assignment authority ID"),
        ):
            validate_identifier(value, label)
        validate_agent_role(self.business_role)
        validate_text(self.objective, "Digital Twin assignment objective", 2_000)
        if (
            not isinstance(self.context, tuple)
            or any(not isinstance(item, ContextValue) for item in self.context)
            or len(self.context) > MAX_CONTEXT_ENTRIES
            or len({item.key for item in self.context}) != len(self.context)
        ):
            raise ValueError("Digital Twin assignment context is invalid")
        context_bytes = len(
            canonical_json([asdict(item) for item in self.context]).encode("utf-8")
        )
        if context_bytes > MAX_CONTEXT_BYTES:
            raise ValueError("Digital Twin assignment context exceeds its byte limit")
        _unique_identifiers(
            self.required_capability_ids,
            "Digital Twin required capability IDs",
            MAX_CAPABILITY_IDS,
        )
        _unique_identifiers(
            self.requested_tool_ids,
            "Digital Twin requested tool IDs",
            MAX_TOOL_IDS,
        )
        validate_digest(self.authority_digest, "Digital Twin authority digest")
        validate_utc(self.created_at, "Digital Twin assignment creation time")

    @property
    def objective_digest(self) -> str:
        return hashlib.sha256(self.objective.encode("utf-8")).hexdigest()

    @property
    def digest(self) -> str:
        return canonical_digest(_assignment_record(self))


@dataclass(frozen=True)
class ProviderExecutionRequest:
    """The only input exposed to a Digital Twin provider."""

    execution_id: str
    provider_id: str
    twin_id: str
    twin_digest: str
    assignment_id: str
    assignment_digest: str
    authority_id: str
    authority_digest: str
    tenant_id: str
    business_role: AgentRole
    objective: str
    context: tuple[ContextValue, ...]
    required_capability_ids: tuple[str, ...]
    allowed_action_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    authority_expires_at: datetime
    max_tool_calls: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.execution_id, "provider execution ID"),
            (self.provider_id, "provider ID"),
            (self.twin_id, "provider Digital Twin ID"),
            (self.assignment_id, "provider assignment ID"),
            (self.authority_id, "provider authority ID"),
            (self.tenant_id, "provider tenant ID"),
        ):
            validate_identifier(value, label)
        for value, label in (
            (self.twin_digest, "provider Digital Twin digest"),
            (self.assignment_digest, "provider assignment digest"),
            (self.authority_digest, "provider authority digest"),
        ):
            validate_digest(value, label)
        validate_agent_role(self.business_role)
        validate_utc(self.authority_expires_at, "provider authority expiry time")

    @property
    def digest(self) -> str:
        return canonical_digest(_request_record(self))


@dataclass(frozen=True)
class ProviderExecutionResult:
    """Bounded structured response returned by a Digital Twin provider."""

    execution_id: str
    provider_id: str
    request_digest: str
    status: DigitalTwinExecutionStatus
    summary: str
    output: tuple[ContextValue, ...]
    failure_code: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.execution_id, "provider-result execution ID")
        validate_identifier(self.provider_id, "provider-result provider ID")
        validate_digest(self.request_digest, "provider-result request digest")
        if not isinstance(self.status, DigitalTwinExecutionStatus):
            raise ValueError("Digital Twin provider-result status is invalid")
        validate_text(self.summary, "Digital Twin provider-result summary", 2_000)
        if (
            not isinstance(self.output, tuple)
            or any(not isinstance(item, ContextValue) for item in self.output)
            or len(self.output) > MAX_CONTEXT_ENTRIES
            or len({item.key for item in self.output}) != len(self.output)
        ):
            raise ValueError("Digital Twin provider-result output is invalid")
        if self.status is DigitalTwinExecutionStatus.SUCCEEDED:
            if self.failure_code is not None:
                raise ValueError("Successful Digital Twin result cannot have a failure code")
        else:
            validate_identifier(self.failure_code, "provider-result failure code")
            if self.output:
                raise ValueError("Failed Digital Twin result cannot contain output")

    @property
    def output_digest(self) -> str:
        return canonical_digest([asdict(item) for item in self.output])


@dataclass(frozen=True)
class ToolCallEvidence:
    """Digest-only evidence for one invocation through the bounded gateway."""

    sequence: int
    tool_id: str
    request_digest: str
    outcome: ToolCallOutcome
    response_digest: str | None
    failure_code: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise ValueError("Digital Twin tool-call sequence is invalid")
        validate_identifier(self.tool_id, "Digital Twin tool-call tool ID")
        validate_digest(self.request_digest, "Digital Twin tool-call request digest")
        if not isinstance(self.outcome, ToolCallOutcome):
            raise ValueError("Digital Twin tool-call outcome is invalid")
        if self.outcome is ToolCallOutcome.SUCCEEDED:
            validate_digest(self.response_digest, "Digital Twin tool-call response digest")
            if self.failure_code is not None:
                raise ValueError("Successful tool call cannot have a failure code")
        else:
            if self.response_digest is not None:
                raise ValueError("Failed tool call cannot expose a response digest")
            validate_identifier(self.failure_code, "Digital Twin tool-call failure code")


@dataclass(frozen=True)
class DigitalTwinExecutionIntent:
    """Write-before-effect identity for one exact execution attempt."""

    execution_id: str
    tenant_id: str
    twin_id: str
    twin_digest: str
    assignment_id: str
    assignment_digest: str
    authority_id: str
    authority_digest: str
    provider_id: str
    request_digest: str
    prepared_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.execution_id, "execution intent ID"),
            (self.tenant_id, "execution intent tenant ID"),
            (self.twin_id, "execution intent Digital Twin ID"),
            (self.assignment_id, "execution intent assignment ID"),
            (self.authority_id, "execution intent authority ID"),
            (self.provider_id, "execution intent provider ID"),
        ):
            validate_identifier(value, label)
        for value, label in (
            (self.twin_digest, "execution intent twin digest"),
            (self.assignment_digest, "execution intent assignment digest"),
            (self.authority_digest, "execution intent authority digest"),
            (self.request_digest, "execution intent request digest"),
        ):
            validate_digest(value, label)
        validate_utc(self.prepared_at, "execution intent prepared time")

    @property
    def digest(self) -> str:
        return canonical_digest(_intent_record(self))


@dataclass(frozen=True)
class DigitalTwinExecutionReceipt:
    """Immutable exact-authority result and tool-use evidence."""

    receipt_id: str
    execution_id: str
    tenant_id: str
    twin_id: str
    twin_digest: str
    assignment_id: str
    assignment_digest: str
    authority_id: str
    authority_digest: str
    provider_id: str
    request_digest: str
    intent_digest: str
    status: DigitalTwinExecutionStatus
    summary: str
    output_digest: str
    tool_calls: tuple[ToolCallEvidence, ...]
    failure_code: str | None
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_id, "Digital Twin receipt ID"),
            (self.execution_id, "Digital Twin receipt execution ID"),
            (self.tenant_id, "Digital Twin receipt tenant ID"),
            (self.twin_id, "Digital Twin receipt twin ID"),
            (self.assignment_id, "Digital Twin receipt assignment ID"),
            (self.authority_id, "Digital Twin receipt authority ID"),
            (self.provider_id, "Digital Twin receipt provider ID"),
        ):
            validate_identifier(value, label)
        for value, label in (
            (self.twin_digest, "Digital Twin receipt twin digest"),
            (self.assignment_digest, "Digital Twin receipt assignment digest"),
            (self.authority_digest, "Digital Twin receipt authority digest"),
            (self.request_digest, "Digital Twin receipt request digest"),
            (self.intent_digest, "Digital Twin receipt intent digest"),
            (self.output_digest, "Digital Twin receipt output digest"),
        ):
            validate_digest(value, label)
        if not isinstance(self.status, DigitalTwinExecutionStatus):
            raise ValueError("Digital Twin receipt status is invalid")
        validate_text(self.summary, "Digital Twin receipt summary", 2_000)
        if (
            not isinstance(self.tool_calls, tuple)
            or any(not isinstance(item, ToolCallEvidence) for item in self.tool_calls)
            or tuple(item.sequence for item in self.tool_calls)
            != tuple(range(1, len(self.tool_calls) + 1))
        ):
            raise ValueError("Digital Twin receipt tool evidence is invalid")
        if self.status is DigitalTwinExecutionStatus.SUCCEEDED:
            if self.failure_code is not None:
                raise ValueError("Successful Digital Twin receipt cannot have a failure code")
        else:
            validate_identifier(self.failure_code, "Digital Twin receipt failure code")
        validate_utc(self.started_at, "Digital Twin receipt start time")
        validate_utc(self.completed_at, "Digital Twin receipt completion time")
        if self.completed_at < self.started_at:
            raise ValueError("Digital Twin receipt completed before it started")

    @property
    def digest(self) -> str:
        return canonical_digest(_receipt_record(self))


def receipt_id_for(execution_id: str) -> str:
    """Derive a stable receipt identity without trusting provider output."""

    validate_identifier(execution_id, "execution receipt source ID")
    value = hashlib.sha256(f"digital-twin-receipt:{execution_id}".encode()).hexdigest()
    return f"twin-receipt-{value[:24]}"


def validate_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def validate_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def validate_text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        raise ValueError(f"{label} is invalid")


def validate_utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be a timezone-aware UTC datetime")


def validate_public_field(key: object, value: object, *, label: str) -> None:
    if (
        not isinstance(key, str)
        or not _CONTEXT_KEY.fullmatch(key)
        or _SENSITIVE_KEY.search(key)
        or not isinstance(value, str)
        or len(value) > 2_000
        or "\x00" in value
    ):
        raise ValueError(f"Digital Twin {label} field is invalid or secret-bearing")


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _unique_actions(values: object) -> None:
    if (
        not isinstance(values, tuple)
        or not values
        or len(values) > 16
        or any(not isinstance(value, str) or not _ACTION.fullmatch(value) for value in values)
        or len(values) != len(set(values))
    ):
        raise ValueError("Digital Twin authority actions are invalid")


def _unique_identifiers(values: object, label: str, maximum: int) -> None:
    if (
        not isinstance(values, tuple)
        or len(values) > maximum
        or len(values) != len(set(values))
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        validate_identifier(value, label)


def _authority_record(value: DelegatedAuthority) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["allowed_action_ids"] = list(value.allowed_action_ids)
    payload["allowed_tool_ids"] = list(value.allowed_tool_ids)
    payload["issued_at"] = value.issued_at.isoformat()
    payload["expires_at"] = value.expires_at.isoformat()
    return payload


def _definition_record(value: DigitalTwinDefinition) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["capability_ids"] = list(value.capability_ids)
    payload["approved_tool_ids"] = list(value.approved_tool_ids)
    return payload


def _assignment_record(value: DigitalTwinAssignment) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["context"] = [asdict(item) for item in value.context]
    payload["required_capability_ids"] = list(value.required_capability_ids)
    payload["requested_tool_ids"] = list(value.requested_tool_ids)
    payload["created_at"] = value.created_at.isoformat()
    return payload


def _request_record(value: ProviderExecutionRequest) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    payload["context"] = [asdict(item) for item in value.context]
    payload["required_capability_ids"] = list(value.required_capability_ids)
    payload["allowed_action_ids"] = list(value.allowed_action_ids)
    payload["allowed_tool_ids"] = list(value.allowed_tool_ids)
    payload["authority_expires_at"] = value.authority_expires_at.isoformat()
    return payload


def _intent_record(value: DigitalTwinExecutionIntent) -> dict[str, object]:
    payload = asdict(value)
    payload["prepared_at"] = value.prepared_at.isoformat()
    return payload


def _receipt_record(value: DigitalTwinExecutionReceipt) -> dict[str, object]:
    payload = asdict(value)
    payload["status"] = value.status.value
    payload["tool_calls"] = [
        {
            **asdict(item),
            "outcome": item.outcome.value,
        }
        for item in value.tool_calls
    ]
    payload["started_at"] = value.started_at.isoformat()
    payload["completed_at"] = value.completed_at.isoformat()
    return payload


__all__ = [
    "DelegatedAuthority",
    "DigitalTwinAssignment",
    "DigitalTwinDefinition",
    "DigitalTwinExecutionIntent",
    "DigitalTwinExecutionReceipt",
    "DigitalTwinExecutionStatus",
    "ContextValue",
    "EXECUTE_ASSIGNED_WORK",
    "FORBIDDEN_DAY22_ACTIONS",
    "PRODUCE_EXECUTION_EVIDENCE",
    "ProviderExecutionRequest",
    "ProviderExecutionResult",
    "ToolCallEvidence",
    "ToolCallOutcome",
    "USE_ASSIGNED_TOOL",
    "canonical_digest",
    "canonical_json",
    "receipt_id_for",
    "validate_digest",
    "validate_identifier",
    "validate_public_field",
]
