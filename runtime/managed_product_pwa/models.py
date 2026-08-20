"""Immutable PWA verification and complete capability-submission authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


class PwaClaim(str, Enum):
    MANIFEST_VERIFIED = "MANIFEST_VERIFIED"
    ICONS_VERIFIED = "ICONS_VERIFIED"
    SERVICE_WORKER_ACTIVE = "SERVICE_WORKER_ACTIVE"
    SERVICE_WORKER_CONTROLS_PAGE = "SERVICE_WORKER_CONTROLS_PAGE"
    STANDALONE_DISPLAY = "STANDALONE_DISPLAY"
    REFRESH_SURVIVES = "REFRESH_SURVIVES"
    OFFLINE_SHELL_AVAILABLE = "OFFLINE_SHELL_AVAILABLE"


LOCKED_PWA_CLAIMS = tuple(PwaClaim)
LOCKED_CAPABILITY_ORDER = ("AUTHENTICATION", "VOICE", "PWA")


@dataclass(frozen=True)
class PwaExecutionPolicy:
    allowed_provider_ids: frozenset[str]
    allowed_origins: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_provider_ids, frozenset) or not self.allowed_provider_ids:
            raise ValueError("PWA policy requires allowed provider IDs")
        for value in self.allowed_provider_ids:
            _identifier(value, "PWA policy provider ID")
        if not isinstance(self.allowed_origins, frozenset) or not self.allowed_origins:
            raise ValueError("PWA policy requires allowed origins")
        for value in self.allowed_origins:
            if (
                not isinstance(value, str)
                or value != value.strip()
                or "\\" in value
                or any(ord(character) < 32 or ord(character) == 127 for character in value)
            ):
                raise ValueError("PWA policy origin is unsafe")
            parsed = urlsplit(value)
            try:
                port = parsed.port
            except ValueError as error:
                raise ValueError("PWA policy origin is unsafe") from error
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
                or port == 0
            ):
                raise ValueError("PWA policy origin is unsafe")


@dataclass(frozen=True)
class PwaVerificationPlan:
    plan_id: str
    run_id: str
    product_id: str
    configuration_id: str
    configuration_revision: int
    configuration_digest: str
    commit_sha: str
    acceptance_profile_id: str
    acceptance_profile_version: str
    acceptance_profile_digest: str
    provider_id: str
    start_path: str
    manifest_path: str
    service_worker_path: str
    shell_test_id: str
    shell_expected_text: str
    claims: tuple[PwaClaim, ...]
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.plan_id, "PWA plan ID"),
            (self.run_id, "PWA run ID"),
            (self.product_id, "PWA product ID"),
            (self.configuration_id, "PWA configuration ID"),
            (self.acceptance_profile_id, "PWA profile ID"),
            (self.provider_id, "PWA provider ID"),
            (self.shell_test_id, "PWA shell test ID"),
        ):
            _identifier(value, label)
        for value, label in (
            (self.configuration_digest, "PWA configuration digest"),
            (self.acceptance_profile_digest, "PWA profile digest"),
        ):
            _digest(value, label)
        _sha(self.commit_sha)
        if (
            isinstance(self.configuration_revision, bool)
            or not isinstance(self.configuration_revision, int)
            or self.configuration_revision < 1
        ):
            raise ValueError("PWA configuration revision must be positive")
        for value, label in (
            (self.start_path, "PWA start path"),
            (self.manifest_path, "PWA manifest path"),
            (self.service_worker_path, "PWA service-worker path"),
        ):
            _path(value, label)
        if len({self.start_path, self.manifest_path, self.service_worker_path}) != 3:
            raise ValueError("PWA authority paths must be distinct")
        _bounded(self.acceptance_profile_version, "PWA profile version", 128)
        _bounded(self.shell_expected_text, "PWA shell marker", 256)
        _bounded(self.created_by, "PWA plan creator", 256)
        if self.claims != LOCKED_PWA_CLAIMS:
            raise ValueError("PWA plan must contain every locked claim in order")
        _utc(self.created_at, "PWA plan created_at")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["claims"] = [value.value for value in self.claims]
        payload["created_at"] = self.created_at.isoformat()
        return _hash(payload)


@dataclass(frozen=True)
class CapabilityExecutionReference:
    capability_id: str
    plan_id: str
    plan_digest: str
    result_digest: str
    journey_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.capability_id, "submission capability ID")
        _identifier(self.plan_id, "submission source plan ID")
        _digest(self.plan_digest, "submission source plan digest")
        _digest(self.result_digest, "submission source result digest")
        if (
            not isinstance(self.journey_ids, tuple)
            or not self.journey_ids
            or len(self.journey_ids) != len(set(self.journey_ids))
        ):
            raise ValueError("Submission source requires unique journey IDs")
        for value in self.journey_ids:
            _identifier(value, "submission journey ID")


@dataclass(frozen=True)
class AcceptanceSubmissionPlan:
    submission_id: str
    run_id: str
    product_id: str
    configuration_id: str
    configuration_revision: int
    configuration_digest: str
    commit_sha: str
    acceptance_profile_id: str
    acceptance_profile_version: str
    acceptance_profile_digest: str
    sources: tuple[CapabilityExecutionReference, ...]
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.submission_id, "submission ID"),
            (self.run_id, "submission run ID"),
            (self.product_id, "submission product ID"),
            (self.configuration_id, "submission configuration ID"),
            (self.acceptance_profile_id, "submission profile ID"),
        ):
            _identifier(value, label)
        for value, label in (
            (self.configuration_digest, "submission configuration digest"),
            (self.acceptance_profile_digest, "submission profile digest"),
        ):
            _digest(value, label)
        _sha(self.commit_sha)
        if (
            isinstance(self.configuration_revision, bool)
            or not isinstance(self.configuration_revision, int)
            or self.configuration_revision < 1
        ):
            raise ValueError("Submission configuration revision must be positive")
        if (
            not isinstance(self.sources, tuple)
            or any(not isinstance(item, CapabilityExecutionReference) for item in self.sources)
            or tuple(item.capability_id for item in self.sources) != LOCKED_CAPABILITY_ORDER
        ):
            raise ValueError("Submission must bind Authentication, Voice, and PWA in order")
        all_journeys = tuple(value for item in self.sources for value in item.journey_ids)
        if len(all_journeys) != len(set(all_journeys)):
            raise ValueError("Submission journeys must be unique across capability slices")
        _bounded(self.acceptance_profile_version, "submission profile version", 128)
        _bounded(self.created_by, "submission creator", 256)
        _utc(self.created_at, "submission created_at")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        return _hash(payload)


@dataclass(frozen=True)
class AcceptanceSubmissionReceipt:
    submission_id: str
    submission_digest: str
    run_id: str
    product_id: str
    runtime_evidence_digest: str
    source_result_digests: tuple[str, ...]
    submitted_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.submission_id, "receipt submission ID"),
            (self.run_id, "receipt run ID"),
            (self.product_id, "receipt product ID"),
        ):
            _identifier(value, label)
        _digest(self.submission_digest, "receipt submission digest")
        _digest(self.runtime_evidence_digest, "receipt runtime evidence digest")
        if (
            not isinstance(self.source_result_digests, tuple)
            or len(self.source_result_digests) != len(LOCKED_CAPABILITY_ORDER)
            or len(set(self.source_result_digests)) != len(self.source_result_digests)
        ):
            raise ValueError("Receipt requires unique source-result digests")
        for value in self.source_result_digests:
            _digest(value, "receipt source-result digest")
        _utc(self.submitted_at, "receipt submitted_at")


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")


def _digest(value: str, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _sha(value: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("PWA authority requires a lowercase full commit SHA")


def _path(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value != value.strip()
        or "\\" in value
        or any(marker in value for marker in ("?", "#", "%", "//"))
        or any(part in {".", ".."} for part in PurePosixPath(value).parts)
        or str(PurePosixPath(value)) != value
    ):
        raise ValueError(f"{label} must be a canonical absolute URL path")


def _bounded(value: str, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} must be bounded text")


def _utc(value: datetime, label: str) -> None:
    offset = value.utcoffset() if isinstance(value, datetime) else None
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or offset is None
        or offset.total_seconds() != 0
    ):
        raise ValueError(f"{label} must use UTC")
