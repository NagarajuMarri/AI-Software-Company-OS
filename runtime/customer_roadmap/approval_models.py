"""Immutable customer authority and locked projection for one roadmap draft."""

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
ROADMAP_CONFIRMATION_VERSION = "customer-roadmap-v1"


@dataclass(frozen=True)
class CustomerRoadmapApproval:
    """Write-once receipt that approves and locks one exact roadmap draft."""

    approval_id: str
    customer_id: str
    request_id: str
    roadmap_id: str
    product_id: str
    prd_id: str
    prd_version: str
    source_request_digest: str
    requirements_digest: str
    requirements_approval_digest: str
    prd_digest: str
    prd_approval_digest: str
    roadmap_digest: str
    confirmation_version: str
    approved_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.approval_id, "customer roadmap approval ID"),
            (self.customer_id, "customer roadmap approval customer ID"),
            (self.request_id, "customer roadmap approval request ID"),
            (self.roadmap_id, "customer roadmap approval roadmap ID"),
            (self.product_id, "customer roadmap approval product ID"),
            (self.prd_id, "customer roadmap approval PRD ID"),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.prd_version != "0.1":
            raise ValueError("Customer roadmap approval PRD version is invalid")
        for value, label in (
            (self.source_request_digest, "source request digest"),
            (self.requirements_digest, "requirements digest"),
            (self.requirements_approval_digest, "requirements approval digest"),
            (self.prd_digest, "PRD digest"),
            (self.prd_approval_digest, "PRD approval digest"),
            (self.roadmap_digest, "roadmap digest"),
        ):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.confirmation_version != ROADMAP_CONFIRMATION_VERSION:
            raise ValueError("Customer roadmap confirmation version is invalid")
        _utc(self.approved_at, "customer roadmap approved_at")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["approved_at"] = self.approved_at.isoformat()
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()


@dataclass(frozen=True)
class LockedCustomerRoadmapMilestone:
    """One exact approved roadmap item projected into terminal locked state."""

    roadmap_item_id: str
    milestone: str
    sequence: int
    requirement_ids: tuple[str, ...]
    priorities: tuple[RequirementPriority, ...]
    status: str = "LOCKED"

    def __post_init__(self) -> None:
        if not isinstance(self.roadmap_item_id, str) or not _IDENTIFIER.fullmatch(
            self.roadmap_item_id
        ):
            raise ValueError("Locked roadmap item ID is invalid")
        _text(self.milestone, "locked roadmap milestone", 300)
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("Locked roadmap sequence is invalid")
        if (
            not isinstance(self.requirement_ids, tuple)
            or not self.requirement_ids
            or len(set(self.requirement_ids)) != len(self.requirement_ids)
            or any(
                not isinstance(value, str) or not _REQUIREMENT_ID.fullmatch(value)
                for value in self.requirement_ids
            )
        ):
            raise ValueError("Locked roadmap requirement mapping is invalid")
        if (
            not isinstance(self.priorities, tuple)
            or len(self.priorities) != len(self.requirement_ids)
            or any(not isinstance(value, RequirementPriority) for value in self.priorities)
        ):
            raise ValueError("Locked roadmap priorities are invalid")
        if self.status != "LOCKED":
            raise ValueError("Approved roadmap item must be LOCKED")


@dataclass(frozen=True)
class LockedCustomerRoadmap:
    """Deterministic locked view whose authority is the approval receipt."""

    roadmap_id: str
    customer_id: str
    request_id: str
    product_id: str
    prd_id: str
    prd_version: str
    title: str
    source_roadmap_digest: str
    approval_id: str
    approval_digest: str
    approved_by: str
    locked_at: datetime
    milestones: tuple[LockedCustomerRoadmapMilestone, ...]
    status: str = "LOCKED"

    def __post_init__(self) -> None:
        for value, label in (
            (self.roadmap_id, "locked roadmap ID"),
            (self.customer_id, "locked roadmap customer ID"),
            (self.request_id, "locked roadmap request ID"),
            (self.product_id, "locked roadmap product ID"),
            (self.prd_id, "locked roadmap PRD ID"),
            (self.approval_id, "locked roadmap approval ID"),
            (self.approved_by, "locked roadmap approver"),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.prd_version != "0.1":
            raise ValueError("Locked roadmap PRD version is invalid")
        _text(self.title, "locked roadmap title", 300)
        for value in (self.source_roadmap_digest, self.approval_digest):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError("Locked roadmap digest is invalid")
        _utc(self.locked_at, "locked roadmap time")
        if (
            not isinstance(self.milestones, tuple)
            or not self.milestones
            or any(not isinstance(value, LockedCustomerRoadmapMilestone) for value in self.milestones)
            or tuple(value.sequence for value in self.milestones)
            != tuple(range(1, len(self.milestones) + 1))
        ):
            raise ValueError("Locked roadmap milestones are invalid")
        mapped = tuple(
            requirement
            for milestone in self.milestones
            for requirement in milestone.requirement_ids
        )
        if len(mapped) != len(set(mapped)):
            raise ValueError("Locked roadmap requirements must map exactly once")
        if self.status != "LOCKED":
            raise ValueError("Approved roadmap must be LOCKED")

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        return tuple(
            requirement
            for milestone in self.milestones
            for requirement in milestone.requirement_ids
        )


def roadmap_approval_id_for(request_id: str) -> str:
    """Derive one bounded non-secret roadmap-approval identity."""

    if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
        raise ValueError("Customer roadmap approval request ID is invalid")
    digest = hashlib.sha256(f"customer-roadmap-approval:{request_id}".encode()).hexdigest()
    return f"roadmap-approval-{digest[:24]}"


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


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{label} must be UTC")
