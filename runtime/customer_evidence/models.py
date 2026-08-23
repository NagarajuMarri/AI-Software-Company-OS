"""Immutable preview, evidence, and customer-review authorities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import re
from urllib.parse import urlsplit

from runtime.runtime_acceptance import EvidenceArtifact, EvidenceKind, EvidenceOutcome


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
PACKAGE_STATUS = "AWAITING_CUSTOMER_REVIEW"
REVIEW_CONFIRMATION_VERSION = "ascos-customer-preview-review-v1"
REQUIRED_EVIDENCE_KINDS = (
    EvidenceKind.AUTOMATED_TEST,
    EvidenceKind.BROWSER,
    EvidenceKind.BROWSER_CONSOLE,
    EvidenceKind.BROWSER_NETWORK,
    EvidenceKind.SCREENSHOT,
    EvidenceKind.SECURITY,
)


@dataclass(frozen=True)
class CustomerPreviewEvidencePackage:
    """One exact-commit preview plus governed evidence awaiting a human decision."""

    package_id: str
    customer_id: str
    request_id: str
    product_id: str
    progress_id: str
    progress_digest: str
    roadmap_digest: str
    estimate_digest: str
    preview_label: str
    preview_url: str
    commit_sha: str
    evidence: tuple[EvidenceArtifact, ...]
    published_at: datetime
    status: str = PACKAGE_STATUS

    def __post_init__(self) -> None:
        for value, label in (
            (self.package_id, "evidence package ID"),
            (self.customer_id, "evidence customer ID"),
            (self.request_id, "evidence request ID"),
            (self.product_id, "evidence product ID"),
            (self.progress_id, "evidence progress ID"),
        ):
            _identifier(value, label)
        for value, label in (
            (self.progress_digest, "evidence progress digest"),
            (self.roadmap_digest, "evidence roadmap digest"),
            (self.estimate_digest, "evidence estimate digest"),
        ):
            _digest(value, label)
        _text(self.preview_label, "preview label", 200)
        _safe_url(self.preview_url, "preview URL", allow_artifact=False)
        _sha(self.commit_sha, "preview commit SHA")
        if (
            not isinstance(self.evidence, tuple)
            or not self.evidence
            or any(not isinstance(item, EvidenceArtifact) for item in self.evidence)
            or len({item.evidence_id for item in self.evidence}) != len(self.evidence)
            or not set(REQUIRED_EVIDENCE_KINDS) <= {item.kind for item in self.evidence}
            or any(item.commit_sha != self.commit_sha for item in self.evidence)
        ):
            raise ValueError("Preview evidence is incomplete or belongs to another commit")
        for item in self.evidence:
            _safe_url(item.artifact_uri, "evidence artifact URI", allow_artifact=True)
        _utc(self.published_at, "preview published time")
        if self.status != PACKAGE_STATUS:
            raise ValueError("Preview evidence package status is invalid")

    @property
    def all_required_evidence_passed(self) -> bool:
        required = set(REQUIRED_EVIDENCE_KINDS)
        return all(
            item.outcome is EvidenceOutcome.PASS
            for item in self.evidence
            if item.kind in required
        )

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["published_at"] = self.published_at.isoformat()
        for record, item in zip(payload["evidence"], self.evidence, strict=True):
            record["kind"] = item.kind.value
            record["outcome"] = item.outcome.value
            record["observed_at"] = item.observed_at.isoformat()
            record["metadata"] = [list(value) for value in item.metadata]
        return _hash(payload)


@dataclass(frozen=True)
class CustomerPreviewReview:
    """Immutable customer ACCEPT or REVISE decision for one exact package."""

    review_id: str
    package_id: str
    customer_id: str
    request_id: str
    package_digest: str
    progress_digest: str
    decision: str
    comments: str
    confirmation_version: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.review_id, "preview review ID"),
            (self.package_id, "preview review package ID"),
            (self.customer_id, "preview review customer ID"),
            (self.request_id, "preview review request ID"),
        ):
            _identifier(value, label)
        _digest(self.package_digest, "preview review package digest")
        _digest(self.progress_digest, "preview review progress digest")
        if self.decision not in {"ACCEPT", "REVISE"}:
            raise ValueError("Preview review decision is invalid")
        if not isinstance(self.comments, str) or len(self.comments) > 2_000:
            raise ValueError("Preview review comments are invalid")
        if self.decision == "REVISE" and not self.comments.strip():
            raise ValueError("REVISE requires customer comments")
        if self.confirmation_version != REVIEW_CONFIRMATION_VERSION:
            raise ValueError("Preview review confirmation contract is invalid")
        _utc(self.reviewed_at, "preview reviewed time")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["reviewed_at"] = self.reviewed_at.isoformat()
        return _hash(payload)


def package_id_for(request_id: str) -> str:
    _identifier(request_id, "preview package request ID")
    digest = hashlib.sha256(f"customer-preview-evidence:{request_id}".encode()).hexdigest()
    return f"customer-evidence-{digest[:24]}"


def review_id_for(request_id: str) -> str:
    _identifier(request_id, "preview review request ID")
    digest = hashlib.sha256(f"customer-preview-review:{request_id}".encode()).hexdigest()
    return f"customer-review-{digest[:24]}"


def preview_origin(value: str) -> str:
    """Return one canonical credential-free origin for policy comparison."""

    _safe_url(value, "preview URL", allow_artifact=False)
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    port = parsed.port
    default = (parsed.scheme == "https" and port == 443) or (
        parsed.scheme == "http" and port == 80
    )
    authority = host if port is None or default else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"


def _safe_url(value: object, label: str, *, allow_artifact: bool) -> None:
    if not isinstance(value, str) or not value or len(value) > 2_048:
        raise ValueError(f"{label} is invalid")
    parsed = urlsplit(value)
    allowed = {"https"}
    if allow_artifact:
        allowed.add("artifact")
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        allowed.add("http")
    if (
        parsed.scheme not in allowed
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise ValueError(f"{label} is unsafe")


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _text(value: object, label: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _sha(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _utc(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
