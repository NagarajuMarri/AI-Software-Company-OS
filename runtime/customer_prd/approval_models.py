"""Immutable customer authority for one locked PRD version."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
PRD_CONFIRMATION_VERSION = "customer-prd-v1"


@dataclass(frozen=True)
class CustomerPrdApproval:
    """Write-once receipt that approves and locks one exact customer PRD."""

    approval_id: str
    customer_id: str
    request_id: str
    artifact_id: str
    product_id: str
    prd_id: str
    prd_version: str
    source_request_digest: str
    requirements_digest: str
    requirements_approval_digest: str
    prd_digest: str
    confirmation_version: str
    approved_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.approval_id, "customer PRD approval ID"),
            (self.customer_id, "customer PRD approval customer ID"),
            (self.request_id, "customer PRD approval request ID"),
            (self.artifact_id, "customer PRD approval artifact ID"),
            (self.product_id, "customer PRD approval product ID"),
            (self.prd_id, "customer PRD approval PRD ID"),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.prd_version != "0.1":
            raise ValueError("Customer PRD approval version is invalid")
        for value, label in (
            (self.source_request_digest, "source product-request digest"),
            (self.requirements_digest, "requirements draft digest"),
            (self.requirements_approval_digest, "requirements approval digest"),
            (self.prd_digest, "customer PRD digest"),
        ):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.confirmation_version != PRD_CONFIRMATION_VERSION:
            raise ValueError("Customer PRD confirmation version is invalid")
        if (
            not isinstance(self.approved_at, datetime)
            or self.approved_at.tzinfo is None
            or self.approved_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("Customer PRD approved_at must be UTC")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["approved_at"] = self.approved_at.isoformat()
        content = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(content).hexdigest()


def prd_approval_id_for(request_id: str) -> str:
    """Derive a bounded non-secret approval identity from a safe request ID."""

    if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
        raise ValueError("Customer PRD approval request ID is invalid")
    digest = hashlib.sha256(f"customer-prd-approval:{request_id}".encode()).hexdigest()
    return f"prd-approval-{digest[:24]}"
