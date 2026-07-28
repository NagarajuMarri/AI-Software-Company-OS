"""Durable outbox value models and validation."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from runtime.outbox.exceptions import OutboxValidationError

_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]{1,99}$")
_PROVIDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SECRET = re.compile(
    r"(token|secret|password|api[_-]?key|credential|private[_-]?key)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{12,})",
    re.I,
)
MAX_PAYLOAD_BYTES = 32_768


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    DISPATCHING = "DISPATCHING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_WAIT = "RETRY_WAIT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


class FailureCategory(str, Enum):
    NON_RETRYABLE = "NON_RETRYABLE"
    RETRYABLE_IMMEDIATE = "RETRYABLE_IMMEDIATE"
    RETRYABLE_BACKOFF = "RETRYABLE_BACKOFF"
    RATE_LIMITED = "RATE_LIMITED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ReconciliationState(str, Enum):
    NONE = "NONE"
    REQUIRED = "REQUIRED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    UNVERIFIABLE = "UNVERIFIABLE"


def freeze_payload(value):
    if isinstance(value, Mapping):
        return MappingProxyType({
            str(key): freeze_payload(item) for key, item in value.items()
        })
    if isinstance(value, (list, tuple)):
        return tuple(freeze_payload(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise OutboxValidationError("Outbox payload is not serialisable")


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


def validate_payload(payload):
    frozen = freeze_payload(payload)
    encoded = json.dumps(plain(frozen), sort_keys=True, separators=(",", ":"))
    if len(encoded.encode()) > MAX_PAYLOAD_BYTES:
        raise OutboxValidationError("Outbox payload exceeds size limit")
    def inspect(value, path=""):
        if isinstance(value, Mapping):
            for key, item in value.items():
                if _SECRET.search(key):
                    raise OutboxValidationError("Secret-bearing payload key")
                inspect(item, f"{path}.{key}")
        elif isinstance(value, tuple):
            for item in value: inspect(item, path)
        elif isinstance(value, str) and (
            (_SECRET.search(path) and value) or _SECRET_VALUE.search(value)
        ):
            raise OutboxValidationError("Secret-bearing payload value")
    inspect(frozen)
    return frozen


def validate_safe_reference(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or _SECRET_VALUE.search(value)
    ):
        raise OutboxValidationError("Unsafe provider result reference")
    return value


@dataclass
class OutboxOperation:
    operation_id: str
    runtime_id: str
    project_id: str
    task_id: str
    work_item_id: str
    operation_type: str
    provider_id: str
    aggregate_id: str
    aggregate_version: int
    idempotency_key: str
    correlation_id: str | None
    causation_id: str | None
    payload: Mapping[str, object]
    payload_schema_version: int
    status: OutboxStatus
    priority: int
    available_at: datetime
    created_at: datetime
    first_attempted_at: datetime | None = None
    last_attempted_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int = 0
    maximum_attempts: int = 3
    claim_owner: str | None = None
    claim_token_hash: str | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    fencing_token: int = 0
    failure_code: str | None = None
    failure_category: FailureCategory | None = None
    retry_after: datetime | None = None
    result_reference: str | None = None
    reconciliation_state: ReconciliationState = ReconciliationState.NONE
    dead_letter_reason: str | None = None

    def __post_init__(self):
        if not _IDENTIFIER.fullmatch(self.operation_type):
            raise OutboxValidationError("Invalid operation type")
        if not _PROVIDER.fullmatch(self.provider_id):
            raise OutboxValidationError("Invalid provider ID")
        if self.aggregate_version < 0 or self.payload_schema_version < 1:
            raise OutboxValidationError("Invalid schema or aggregate version")
        if self.maximum_attempts < 1:
            raise OutboxValidationError("maximum_attempts must be positive")
        for name in ("available_at", "created_at"):
            value = getattr(self, name)
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset().total_seconds() != 0
            ):
                raise OutboxValidationError(
                    f"{name} must be a UTC timestamp"
                )
        self.payload = validate_payload(self.payload)

    def request_fingerprint(self):
        value = {
            "operation_type": self.operation_type,
            "provider_id": self.provider_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_version": self.aggregate_version,
            "payload_schema_version": self.payload_schema_version,
            "payload": plain(self.payload),
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class OutboxClaim:
    operation_id: str
    owner_id: str
    token: str
    claimed_at: datetime
    expires_at: datetime
    fencing_token: int


@dataclass(frozen=True)
class OutboxAttempt:
    operation_id: str
    attempt_number: int
    started_at: datetime
    completed_at: datetime | None
    outcome: str
    failure_code: str | None = None
    failure_category: FailureCategory | None = None
    safe_summary: str = ""


@dataclass(frozen=True)
class IdempotencyRecord:
    idempotency_key: str
    operation_id: str
    provider_id: str
    request_fingerprint: str
    first_dispatch_at: datetime
    provider_reference: str | None
    result_fingerprint: str | None
    completion_time: datetime | None
    status: str
