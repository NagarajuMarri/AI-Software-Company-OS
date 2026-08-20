"""Immutable customer product-request authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ProductRequestStage(str, Enum):
    """Day 11 accepts one terminal intake state only."""

    SUBMITTED = "SUBMITTED"


@dataclass(frozen=True)
class CustomerProductRequest:
    """One immutable product brief submitted by one customer."""

    request_id: str
    customer_id: str
    product_name: str
    product_summary: str
    target_users: str
    features: tuple[str, ...]
    constraints: tuple[str, ...]
    stage: ProductRequestStage
    submitted_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.request_id, "product request ID")
        _identifier(self.customer_id, "customer ID")
        _text(self.product_name, "product name", 120)
        _text(self.product_summary, "product summary", 2_000)
        _text(self.target_users, "target users", 500)
        _items(self.features, "product features", minimum=1, maximum=20, item_limit=300)
        _items(self.constraints, "product constraints", minimum=0, maximum=20, item_limit=300)
        if not isinstance(self.stage, ProductRequestStage):
            raise ValueError("Product request stage is invalid")
        if self.stage is not ProductRequestStage.SUBMITTED:
            raise ValueError("Day 11 accepts submitted product requests only")
        if (
            not isinstance(self.submitted_at, datetime)
            or self.submitted_at.tzinfo is None
            or self.submitted_at.utcoffset() is None
        ):
            raise ValueError("Product request submitted_at must be timezone-aware")

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self)).hexdigest()

    @property
    def business_identity(self) -> tuple[object, ...]:
        """Fields that make an exact browser retry idempotent."""

        return (
            self.request_id,
            self.customer_id,
            self.product_name,
            self.product_summary,
            self.target_users,
            self.features,
            self.constraints,
            self.stage,
        )


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
    *,
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


def _canonical(value: CustomerProductRequest) -> bytes:
    payload = asdict(value)
    payload["stage"] = value.stage.value
    payload["submitted_at"] = value.submitted_at.isoformat()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
