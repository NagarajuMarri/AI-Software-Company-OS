"""Traceable deterministic roadmap draft derived from one locked customer PRD."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re

from runtime.product_requirements import RequirementPriority


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REQUIREMENT_ID = re.compile(r"^REQ-[A-Z0-9][A-Z0-9-]{0,59}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
GENERATION_PROFILE = "ascos-deterministic-customer-roadmap-v1"
ROADMAP_STATUS = "DRAFT"


@dataclass(frozen=True)
class CustomerRoadmapMilestone:
    """One governed-domain roadmap item with exact locked requirement mappings."""

    roadmap_item_id: str
    milestone: str
    sequence: int
    requirement_ids: tuple[str, ...]
    priorities: tuple[RequirementPriority, ...]
    status: str = ROADMAP_STATUS

    def __post_init__(self) -> None:
        if not isinstance(self.roadmap_item_id, str) or not _IDENTIFIER.fullmatch(
            self.roadmap_item_id
        ):
            raise ValueError("Customer roadmap item ID is invalid")
        _text(self.milestone, "customer roadmap milestone", 300)
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or not 1 <= self.sequence <= 100:
            raise ValueError("Customer roadmap sequence is invalid")
        if (
            not isinstance(self.requirement_ids, tuple)
            or not self.requirement_ids
            or len(self.requirement_ids) > 100
            or len(set(self.requirement_ids)) != len(self.requirement_ids)
            or any(
                not isinstance(value, str) or not _REQUIREMENT_ID.fullmatch(value)
                for value in self.requirement_ids
            )
        ):
            raise ValueError("Customer roadmap requirement mapping is invalid")
        if (
            not isinstance(self.priorities, tuple)
            or len(self.priorities) != len(self.requirement_ids)
            or any(not isinstance(value, RequirementPriority) for value in self.priorities)
        ):
            raise ValueError("Customer roadmap priorities are invalid")
        if self.status != ROADMAP_STATUS:
            raise ValueError("Customer roadmap item must remain DRAFT")


@dataclass(frozen=True)
class CustomerRoadmapDraft:
    """Write-once planning draft bound to the complete locked-PRD authority chain."""

    roadmap_id: str
    customer_id: str
    request_id: str
    product_id: str
    prd_id: str
    prd_version: str
    source_request_digest: str
    requirements_digest: str
    requirements_approval_digest: str
    prd_digest: str
    prd_approval_id: str
    prd_approval_digest: str
    generation_profile: str
    title: str
    milestones: tuple[CustomerRoadmapMilestone, ...]
    generated_at: datetime
    status: str = ROADMAP_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.roadmap_id, "customer roadmap ID"),
            (self.customer_id, "customer roadmap customer ID"),
            (self.request_id, "customer roadmap request ID"),
            (self.product_id, "customer roadmap product ID"),
            (self.prd_id, "customer roadmap PRD ID"),
            (self.prd_approval_id, "customer roadmap PRD approval ID"),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.prd_version != "0.1":
            raise ValueError("Customer roadmap PRD version is invalid")
        for value, label in (
            (self.source_request_digest, "source request digest"),
            (self.requirements_digest, "requirements digest"),
            (self.requirements_approval_digest, "requirements approval digest"),
            (self.prd_digest, "PRD digest"),
            (self.prd_approval_digest, "PRD approval digest"),
        ):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.generation_profile != GENERATION_PROFILE:
            raise ValueError("Customer roadmap generation profile is invalid")
        _text(self.title, "customer roadmap title", 300)
        if (
            not isinstance(self.milestones, tuple)
            or not self.milestones
            or len(self.milestones) > 100
            or any(not isinstance(value, CustomerRoadmapMilestone) for value in self.milestones)
            or tuple(value.sequence for value in self.milestones)
            != tuple(range(1, len(self.milestones) + 1))
            or len({value.roadmap_item_id for value in self.milestones}) != len(self.milestones)
        ):
            raise ValueError("Customer roadmap milestones are invalid")
        mapped = tuple(
            requirement_id
            for milestone in self.milestones
            for requirement_id in milestone.requirement_ids
        )
        if len(mapped) != len(set(mapped)):
            raise ValueError("Customer roadmap requirements must map exactly once")
        if (
            not isinstance(self.generated_at, datetime)
            or self.generated_at.tzinfo is None
            or self.generated_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("Customer roadmap generated_at must be UTC")
        if self.status != ROADMAP_STATUS:
            raise ValueError("Customer roadmap must remain DRAFT")

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        return tuple(
            requirement_id
            for milestone in self.milestones
            for requirement_id in milestone.requirement_ids
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self)).hexdigest()


def roadmap_id_for(request_id: str) -> str:
    """Derive one bounded non-secret roadmap identity from the product request."""

    if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
        raise ValueError("Customer roadmap request ID is invalid")
    digest = hashlib.sha256(f"customer-roadmap:{request_id}".encode()).hexdigest()
    return f"customer-roadmap-{digest[:24]}"


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


def _canonical(value: CustomerRoadmapDraft) -> bytes:
    payload = asdict(value)
    for milestone, source in zip(payload["milestones"], value.milestones, strict=True):
        milestone["priorities"] = [priority.value for priority in source.priorities]
    payload["generated_at"] = value.generated_at.isoformat()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
