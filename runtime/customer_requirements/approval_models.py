"""Immutable customer approval authority for one requirements draft."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
CONFIRMATION_VERSION = "customer-requirements-v1"


@dataclass(frozen=True)
class CustomerRequirementsApproval:
    """Write-once receipt that locks one exact guided-requirements revision."""

    approval_id: str
    customer_id: str
    request_id: str
    draft_id: str
    draft_revision: int
    source_request_digest: str
    requirements_digest: str
    confirmation_version: str
    approved_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.approval_id, "requirements approval ID"),
            (self.customer_id, "requirements customer ID"),
            (self.request_id, "requirements request ID"),
            (self.draft_id, "requirements draft ID"),
        ):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if (
            isinstance(self.draft_revision, bool)
            or not isinstance(self.draft_revision, int)
            or self.draft_revision < 1
        ):
            raise ValueError("Approved requirements revision is invalid")
        for value, label in (
            (self.source_request_digest, "source product-request digest"),
            (self.requirements_digest, "requirements draft digest"),
        ):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError(f"{label} is invalid")
        if self.confirmation_version != CONFIRMATION_VERSION:
            raise ValueError("Requirements confirmation version is invalid")
        if (
            not isinstance(self.approved_at, datetime)
            or self.approved_at.tzinfo is None
            or self.approved_at.utcoffset() is None
        ):
            raise ValueError("Requirements approved_at must be timezone-aware")

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


def approval_id_for(request_id: str) -> str:
    """Derive a bounded, non-secret approval identity from a safe request ID."""

    if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
        raise ValueError("Requirements request ID is invalid")
    digest = hashlib.sha256(f"approval:{request_id}".encode()).hexdigest()
    return f"approval-{digest[:24]}"
