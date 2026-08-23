"""Deterministic customer delivery-effort estimate derived from a locked roadmap."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REQUIREMENT_ID = re.compile(r"^REQ-[A-Z0-9][A-Z0-9-]{0,59}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
GENERATION_PROFILE = "ascos-deterministic-customer-delivery-estimate-v1"
ESTIMATE_STATUS = "DRAFT"
EFFORT_UNIT = "engineering-day"


class EstimateConfidence(str, Enum):
    """Bounded confidence signal, not a delivery guarantee."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EffortBand(str, Enum):
    """Stable relative effort band for customer review."""

    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    EXTRA_LARGE = "EXTRA_LARGE"


@dataclass(frozen=True)
class CustomerMilestoneEstimate:
    """One exact locked roadmap item with a deterministic effort range."""

    roadmap_item_id: str
    milestone: str
    sequence: int
    requirement_ids: tuple[str, ...]
    complexity_points: int
    minimum_effort_days: int
    maximum_effort_days: int
    effort_band: EffortBand
    confidence: EstimateConfidence
    drivers: tuple[str, ...]
    status: str = ESTIMATE_STATUS

    def __post_init__(self) -> None:
        _identifier(self.roadmap_item_id, "estimate roadmap item ID")
        _text(self.milestone, "estimate milestone", 300)
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("Estimate sequence is invalid")
        if (
            not isinstance(self.requirement_ids, tuple)
            or not self.requirement_ids
            or len(set(self.requirement_ids)) != len(self.requirement_ids)
            or any(
                not isinstance(value, str) or not _REQUIREMENT_ID.fullmatch(value)
                for value in self.requirement_ids
            )
        ):
            raise ValueError("Estimate requirement mapping is invalid")
        for value, label in (
            (self.complexity_points, "complexity points"),
            (self.minimum_effort_days, "minimum effort"),
            (self.maximum_effort_days, "maximum effort"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 10_000:
                raise ValueError(f"Estimate {label} is invalid")
        if self.maximum_effort_days < self.minimum_effort_days:
            raise ValueError("Estimate effort range is invalid")
        if not isinstance(self.effort_band, EffortBand):
            raise ValueError("Estimate effort band is invalid")
        if not isinstance(self.confidence, EstimateConfidence):
            raise ValueError("Estimate confidence is invalid")
        _items(self.drivers, "estimate drivers", 1, 20, 300)
        if self.status != ESTIMATE_STATUS:
            raise ValueError("Milestone estimate must remain DRAFT")


@dataclass(frozen=True)
class CustomerDeliveryEstimateDraft:
    """Write-once estimate bound to the complete locked-roadmap chain."""

    estimate_id: str
    customer_id: str
    request_id: str
    roadmap_id: str
    roadmap_approval_id: str
    product_id: str
    prd_id: str
    prd_version: str
    source_request_digest: str
    requirements_digest: str
    requirements_approval_digest: str
    prd_digest: str
    prd_approval_digest: str
    roadmap_digest: str
    roadmap_approval_digest: str
    generation_profile: str
    title: str
    milestones: tuple[CustomerMilestoneEstimate, ...]
    total_minimum_effort_days: int
    total_maximum_effort_days: int
    effort_unit: str
    confidence: EstimateConfidence
    assumptions: tuple[str, ...]
    generated_at: datetime
    status: str = ESTIMATE_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.estimate_id, "estimate ID"),
            (self.customer_id, "estimate customer ID"),
            (self.request_id, "estimate request ID"),
            (self.roadmap_id, "estimate roadmap ID"),
            (self.roadmap_approval_id, "estimate roadmap approval ID"),
            (self.product_id, "estimate product ID"),
            (self.prd_id, "estimate PRD ID"),
        ):
            _identifier(value, label)
        if self.prd_version != "0.1":
            raise ValueError("Estimate PRD version is invalid")
        for value, label in (
            (self.source_request_digest, "source request digest"),
            (self.requirements_digest, "requirements digest"),
            (self.requirements_approval_digest, "requirements approval digest"),
            (self.prd_digest, "PRD digest"),
            (self.prd_approval_digest, "PRD approval digest"),
            (self.roadmap_digest, "roadmap digest"),
            (self.roadmap_approval_digest, "roadmap approval digest"),
        ):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError(f"Estimate {label} is invalid")
        if self.generation_profile != GENERATION_PROFILE:
            raise ValueError("Estimate generation profile is invalid")
        _text(self.title, "estimate title", 300)
        if (
            not isinstance(self.milestones, tuple)
            or not self.milestones
            or any(not isinstance(value, CustomerMilestoneEstimate) for value in self.milestones)
            or tuple(value.sequence for value in self.milestones)
            != tuple(range(1, len(self.milestones) + 1))
            or len({value.roadmap_item_id for value in self.milestones}) != len(self.milestones)
        ):
            raise ValueError("Estimate milestones are invalid")
        mapped = tuple(
            requirement
            for milestone in self.milestones
            for requirement in milestone.requirement_ids
        )
        if len(mapped) != len(set(mapped)):
            raise ValueError("Estimate requirements must map exactly once")
        if self.total_minimum_effort_days != sum(
            value.minimum_effort_days for value in self.milestones
        ):
            raise ValueError("Estimate minimum total is invalid")
        if self.total_maximum_effort_days != sum(
            value.maximum_effort_days for value in self.milestones
        ):
            raise ValueError("Estimate maximum total is invalid")
        if self.effort_unit != EFFORT_UNIT:
            raise ValueError("Estimate effort unit is invalid")
        if not isinstance(self.confidence, EstimateConfidence):
            raise ValueError("Estimate overall confidence is invalid")
        _items(self.assumptions, "estimate assumptions", 1, 20, 500)
        _utc(self.generated_at, "estimate generated_at")
        if self.status != ESTIMATE_STATUS:
            raise ValueError("Customer delivery estimate must remain DRAFT")

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        return tuple(
            requirement
            for milestone in self.milestones
            for requirement in milestone.requirement_ids
        )

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["confidence"] = self.confidence.value
        payload["generated_at"] = self.generated_at.isoformat()
        for milestone, source in zip(payload["milestones"], self.milestones, strict=True):
            milestone["effort_band"] = source.effort_band.value
            milestone["confidence"] = source.confidence.value
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()


def estimate_id_for(request_id: str) -> str:
    """Derive one bounded non-secret estimate identity."""

    _identifier(request_id, "estimate request ID")
    digest = hashlib.sha256(f"customer-delivery-estimate:{request_id}".encode()).hexdigest()
    return f"customer-estimate-{digest[:24]}"


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


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


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")
