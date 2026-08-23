"""Immutable customer authority for feature-specific PRD acceptance criteria."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REQUIREMENT_ID = re.compile(r"^REQ-FEATURE-[0-9]{3}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
CRITERIA_CONFIRMATION_VERSION = "customer-prd-criteria-v1"


@dataclass(frozen=True)
class CustomerPrdCriteriaEntry:
    """Locked customer-authored criteria for one exact feature requirement."""

    requirement_id: str
    acceptance_criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.requirement_id, str) or not _REQUIREMENT_ID.fullmatch(
            self.requirement_id
        ):
            raise ValueError("Customer PRD criteria requirement ID is invalid")
        _items(self.acceptance_criteria, "customer PRD refined criteria", 2, 5, 500)


@dataclass(frozen=True)
class CustomerPrdCriteriaRefinement:
    """Write-once baseline that refines every feature in one exact PRD draft."""

    refinement_id: str
    customer_id: str
    request_id: str
    source_prd_digest: str
    entries: tuple[CustomerPrdCriteriaEntry, ...]
    confirmation_version: str
    locked_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.refinement_id, "customer PRD criteria refinement ID"),
            (self.customer_id, "customer PRD criteria customer ID"),
            (self.request_id, "customer PRD criteria request ID"),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if not isinstance(self.source_prd_digest, str) or not _DIGEST.fullmatch(
            self.source_prd_digest
        ):
            raise ValueError("Customer PRD criteria source digest is invalid")
        if (
            not isinstance(self.entries, tuple)
            or not 1 <= len(self.entries) <= 20
            or any(not isinstance(item, CustomerPrdCriteriaEntry) for item in self.entries)
            or len({item.requirement_id for item in self.entries}) != len(self.entries)
            or tuple(sorted(self.entries, key=lambda item: item.requirement_id)) != self.entries
        ):
            raise ValueError("Customer PRD criteria entries are invalid")
        if self.confirmation_version != CRITERIA_CONFIRMATION_VERSION:
            raise ValueError("Customer PRD criteria confirmation version is invalid")
        if (
            not isinstance(self.locked_at, datetime)
            or self.locked_at.tzinfo is None
            or self.locked_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("Customer PRD criteria locked_at must be UTC")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["locked_at"] = self.locked_at.isoformat()
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()


def criteria_refinement_id_for(request_id: str) -> str:
    """Derive a bounded non-secret identity for one criteria baseline."""

    if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
        raise ValueError("Customer PRD criteria request ID is invalid")
    digest = hashlib.sha256(f"customer-prd-criteria:{request_id}".encode()).hexdigest()
    return f"prd-criteria-{digest[:24]}"


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
