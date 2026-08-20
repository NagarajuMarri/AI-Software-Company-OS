"""Immutable revision authority for guided customer requirements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_PLATFORMS = ("WEB", "MOBILE", "API", "AUTOMATION")


class DataSensitivity(str, Enum):
    """Customer-declared product data boundary."""

    NO_PERSONAL_DATA = "NO_PERSONAL_DATA"
    PERSONAL_DATA = "PERSONAL_DATA"
    SENSITIVE_DATA = "SENSITIVE_DATA"


class DeliveryPriority(str, Enum):
    """Non-scheduling product priority signal."""

    STANDARD = "STANDARD"
    TIME_SENSITIVE = "TIME_SENSITIVE"


@dataclass(frozen=True)
class CustomerRequirementsDraft:
    """One write-once draft revision bound to one immutable product request."""

    draft_id: str
    customer_id: str
    request_id: str
    revision: int
    source_request_digest: str
    primary_user_journey: str
    desired_outcomes: tuple[str, ...]
    must_have_features: tuple[str, ...]
    success_metrics: tuple[str, ...]
    non_goals: tuple[str, ...]
    platforms: tuple[str, ...]
    data_sensitivity: DataSensitivity
    delivery_priority: DeliveryPriority
    updated_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.draft_id, "requirements draft ID")
        _identifier(self.customer_id, "requirements customer ID")
        _identifier(self.request_id, "requirements request ID")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("Requirements revision is invalid")
        if not isinstance(self.source_request_digest, str) or not _DIGEST.fullmatch(
            self.source_request_digest
        ):
            raise ValueError("Source product-request digest is invalid")
        _text(self.primary_user_journey, "primary user journey", 2_000)
        _items(self.desired_outcomes, "desired outcomes", 1, 10, 300)
        _items(self.must_have_features, "must-have features", 1, 20, 300)
        _items(self.success_metrics, "success metrics", 1, 10, 300)
        _items(self.non_goals, "non-goals", 0, 10, 300)
        if (
            not isinstance(self.platforms, tuple)
            or not self.platforms
            or len(self.platforms) > len(ALLOWED_PLATFORMS)
            or len(set(self.platforms)) != len(self.platforms)
            or tuple(item for item in ALLOWED_PLATFORMS if item in self.platforms)
            != self.platforms
        ):
            raise ValueError("Requirements platforms are invalid")
        if not isinstance(self.data_sensitivity, DataSensitivity):
            raise ValueError("Requirements data sensitivity is invalid")
        if not isinstance(self.delivery_priority, DeliveryPriority):
            raise ValueError("Requirements delivery priority is invalid")
        if (
            not isinstance(self.updated_at, datetime)
            or self.updated_at.tzinfo is None
            or self.updated_at.utcoffset() is None
        ):
            raise ValueError("Requirements updated_at must be timezone-aware")

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self)).hexdigest()

    @property
    def business_content(self) -> tuple[object, ...]:
        """Fields used to make exact browser retries idempotent."""

        return (
            self.customer_id,
            self.request_id,
            self.source_request_digest,
            self.primary_user_journey,
            self.desired_outcomes,
            self.must_have_features,
            self.success_metrics,
            self.non_goals,
            self.platforms,
            self.data_sensitivity,
            self.delivery_priority,
        )


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def draft_id_for(request_id: str) -> str:
    """Derive one bounded non-secret draft identity from a safe request ID."""

    _identifier(request_id, "requirements request ID")
    return f"requirements-{hashlib.sha256(request_id.encode()).hexdigest()[:24]}"


def _text(value: object, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
        or "\x7f" in value
    ):
        raise ValueError(f"{label} is invalid")


def _items(
    values: object,
    label: str,
    minimum: int,
    maximum: int,
    item_limit: int,
) -> None:
    if (
        not isinstance(values, tuple)
        or not minimum <= len(values) <= maximum
        or len({value.casefold() for value in values if isinstance(value, str)}) != len(values)
    ):
        raise ValueError(f"{label} are invalid")
    for value in values:
        _text(value, label, item_limit)


def _canonical(value: CustomerRequirementsDraft) -> bytes:
    payload = asdict(value)
    payload["data_sensitivity"] = value.data_sensitivity.value
    payload["delivery_priority"] = value.delivery_priority.value
    payload["updated_at"] = value.updated_at.isoformat()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
