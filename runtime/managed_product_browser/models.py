"""Immutable exact-authority models for managed browser journeys."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit

from runtime.runtime_acceptance.models import (
    EvidenceArtifact,
    EvidenceOutcome,
    JourneyResult,
)


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SECRET_NAME = re.compile(
    r"(^|[_-])(password|passwd|secret|token|authorization|auth|api[_-]?key|"
    r"access[_-]?key|cookie|credential)($|[_-])",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(^gh[pousr]_[A-Za-z0-9]{20,}$)|(^sk-[A-Za-z0-9_-]{16,}$)|"
    r"(^Basic\s+[A-Za-z0-9+/=]{12,}$)|(^AKIA[0-9A-Z]{16}$)",
    re.IGNORECASE,
)


class BrowserLocatorKind(str, Enum):
    ROLE = "ROLE"
    LABEL = "LABEL"
    TEST_ID = "TEST_ID"
    TEXT = "TEXT"


class BrowserActionKind(str, Enum):
    CLICK = "CLICK"
    FILL = "FILL"
    ASSERT_VISIBLE = "ASSERT_VISIBLE"
    ASSERT_TEXT = "ASSERT_TEXT"
    ASSERT_URL_PATH = "ASSERT_URL_PATH"
    RELOAD = "RELOAD"
    ASSERT_MEDIA_PLAYED = "ASSERT_MEDIA_PLAYED"


class BrowserExecutionStage(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True)
class BrowserLocator:
    kind: BrowserLocatorKind
    value: str
    accessible_name: str = ""
    exact: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BrowserLocatorKind):
            raise ValueError("Browser locator kind is invalid")
        _bounded_text(self.value, "browser locator value", maximum=256)
        if not isinstance(self.exact, bool):
            raise ValueError("Browser locator exact flag must be boolean")
        if self.kind is BrowserLocatorKind.ROLE:
            _bounded_text(
                self.accessible_name,
                "role locator accessible name",
                maximum=256,
            )
        elif self.accessible_name:
            raise ValueError("Only role locators may declare an accessible name")


@dataclass(frozen=True)
class BrowserInputBinding:
    input_id: str
    public_value: str | None = None
    secret_reference: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.input_id, "browser input ID")
        if (self.public_value is None) == (self.secret_reference is None):
            raise ValueError("Browser input requires exactly one public value or secret reference")
        if self.public_value is not None:
            _bounded_text(self.public_value, "browser public input", maximum=8_192)
            if _SECRET_NAME.search(self.input_id) or _SECRET_VALUE.search(self.public_value):
                raise ValueError("Secret-bearing browser inputs require an opaque reference")
        if self.secret_reference is not None:
            _identifier(self.secret_reference, "browser secret reference")

    @property
    def is_secret(self) -> bool:
        return self.secret_reference is not None


@dataclass(frozen=True)
class BrowserStep:
    step_id: str
    action: BrowserActionKind
    locator: BrowserLocator | None = None
    input_id: str = ""
    expected_text: str = ""
    expected_path: str = ""

    def __post_init__(self) -> None:
        _identifier(self.step_id, "browser step ID")
        if not isinstance(self.action, BrowserActionKind):
            raise ValueError("Browser step action is invalid")
        locator_actions = {
            BrowserActionKind.CLICK,
            BrowserActionKind.FILL,
            BrowserActionKind.ASSERT_VISIBLE,
            BrowserActionKind.ASSERT_TEXT,
            BrowserActionKind.ASSERT_MEDIA_PLAYED,
        }
        if (self.action in locator_actions) != (self.locator is not None):
            raise ValueError("Browser step locator does not match its action")
        if self.input_id:
            _identifier(self.input_id, "browser step input ID")
        if (self.action is BrowserActionKind.FILL) != bool(self.input_id):
            raise ValueError("Only fill steps require a browser input ID")
        if self.expected_text:
            _bounded_text(self.expected_text, "expected browser text", maximum=2_000)
        if (self.action is BrowserActionKind.ASSERT_TEXT) != bool(self.expected_text):
            raise ValueError("Only text assertions require expected text")
        if self.expected_path:
            _canonical_path(self.expected_path, "expected browser URL path")
        if (self.action is BrowserActionKind.ASSERT_URL_PATH) != bool(
            self.expected_path
        ):
            raise ValueError("Only URL assertions require an expected path")


@dataclass(frozen=True)
class BrowserJourneySpecification:
    journey_id: str
    capability_id: str
    title: str
    start_path: str
    steps: tuple[BrowserStep, ...]
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        _identifier(self.journey_id, "browser journey ID")
        _identifier(self.capability_id, "browser capability ID")
        _bounded_text(self.title, "browser journey title", maximum=512)
        _canonical_path(self.start_path, "browser journey start path")
        if (
            not isinstance(self.steps, tuple)
            or not self.steps
            or len(self.steps) > 100
            or any(not isinstance(item, BrowserStep) for item in self.steps)
        ):
            raise ValueError("Browser journey requires a bounded tuple of steps")
        _unique(tuple(item.step_id for item in self.steps), "browser step IDs")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 300
        ):
            raise ValueError("Browser journey timeout is outside policy")


@dataclass(frozen=True)
class BrowserJourneyPlan:
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
    journeys: tuple[BrowserJourneySpecification, ...]
    inputs: tuple[BrowserInputBinding, ...]
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.plan_id, "browser plan ID"),
            (self.run_id, "browser run ID"),
            (self.product_id, "browser product ID"),
            (self.configuration_id, "browser configuration ID"),
            (self.acceptance_profile_id, "browser acceptance profile ID"),
        ):
            _identifier(value, label)
        if (
            isinstance(self.configuration_revision, bool)
            or not isinstance(self.configuration_revision, int)
            or self.configuration_revision < 1
        ):
            raise ValueError("Browser configuration revision must be positive")
        _digest(self.configuration_digest, "browser configuration digest")
        _sha(self.commit_sha, "browser plan commit")
        _bounded_text(
            self.acceptance_profile_version,
            "browser acceptance profile version",
            maximum=128,
        )
        _digest(self.acceptance_profile_digest, "browser acceptance profile digest")
        if (
            not isinstance(self.journeys, tuple)
            or not self.journeys
            or len(self.journeys) > 100
            or any(not isinstance(item, BrowserJourneySpecification) for item in self.journeys)
        ):
            raise ValueError("Browser plan requires a bounded tuple of journeys")
        if (
            not isinstance(self.inputs, tuple)
            or len(self.inputs) > 100
            or any(not isinstance(item, BrowserInputBinding) for item in self.inputs)
        ):
            raise ValueError("Browser plan inputs must be a bounded tuple")
        _unique(tuple(item.journey_id for item in self.journeys), "browser journey IDs")
        _unique(tuple(item.input_id for item in self.inputs), "browser input IDs")
        known_inputs = {item.input_id for item in self.inputs}
        used_inputs = {
            step.input_id
            for journey in self.journeys
            for step in journey.steps
            if step.input_id
        }
        if used_inputs != known_inputs:
            raise ValueError("Browser plan inputs must be referenced exactly by its journeys")
        _bounded_text(self.created_by, "browser plan creator", maximum=256)
        _utc(self.created_at, "browser plan created_at")

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical_plan(self)).hexdigest()


@dataclass(frozen=True)
class BrowserExecutionRequest:
    run_id: str
    product_id: str
    plan_id: str
    plan_digest: str

    def __post_init__(self) -> None:
        _identifier(self.run_id, "browser execution run ID")
        _identifier(self.product_id, "browser execution product ID")
        _identifier(self.plan_id, "browser execution plan ID")
        _digest(self.plan_digest, "browser execution plan digest")


@dataclass(frozen=True)
class BrowserExecutionPolicy:
    allowed_provider_ids: frozenset[str]
    allowed_origins: frozenset[str]
    allowed_secret_references: frozenset[str] = frozenset()
    allowed_secret_reference_prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_provider_ids, frozenset) or not self.allowed_provider_ids:
            raise ValueError("Browser policy provider IDs must be a non-empty frozenset")
        for value in self.allowed_provider_ids:
            _identifier(value, "browser provider ID")
        if not isinstance(self.allowed_origins, frozenset) or not self.allowed_origins:
            raise ValueError("Browser policy origins must be a non-empty frozenset")
        for value in self.allowed_origins:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError("Browser policy origin is unsafe")
            try:
                port = parsed.port
            except ValueError as error:
                raise ValueError("Browser policy origin is unsafe") from error
            if port == 0:
                raise ValueError("Browser policy origin is unsafe")
        if not isinstance(self.allowed_secret_references, frozenset):
            raise ValueError("Browser policy secret references must be a frozenset")
        for value in self.allowed_secret_references:
            _identifier(value, "browser policy secret reference")
        if (
            not isinstance(self.allowed_secret_reference_prefixes, tuple)
            or len(self.allowed_secret_reference_prefixes)
            != len(set(self.allowed_secret_reference_prefixes))
            or any(
                not isinstance(value, str)
                or not value
                or len(value) > 128
                or not value.endswith((".", "-", "_"))
                or _has_control(value)
                for value in self.allowed_secret_reference_prefixes
            )
        ):
            raise ValueError("Browser policy secret-reference prefixes are unsafe")


@dataclass(frozen=True)
class BrowserExecutionResult:
    run_id: str
    product_id: str
    plan_id: str
    plan_digest: str
    commit_sha: str
    stage: BrowserExecutionStage
    evidence: tuple[EvidenceArtifact, ...]
    journey_results: tuple[JourneyResult, ...]
    started_at: datetime
    completed_at: datetime
    failure_code: str | None = None

    def __post_init__(self) -> None:
        BrowserExecutionRequest(
            self.run_id, self.product_id, self.plan_id, self.plan_digest
        )
        _sha(self.commit_sha, "browser result commit")
        if not isinstance(self.stage, BrowserExecutionStage):
            raise ValueError("Browser execution stage is invalid")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, EvidenceArtifact) for item in self.evidence
        ):
            raise ValueError("Browser evidence must be a tuple")
        if not isinstance(self.journey_results, tuple) or any(
            not isinstance(item, JourneyResult) for item in self.journey_results
        ):
            raise ValueError("Browser journey results must be a tuple")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        journey_ids = tuple(item.journey_id for item in self.journey_results)
        if len(evidence_ids) != len(set(evidence_ids)) or len(journey_ids) != len(
            set(journey_ids)
        ):
            raise ValueError("Browser execution evidence and journeys must be unique")
        if any(
            item.run_id != self.run_id or item.commit_sha != self.commit_sha
            for item in self.evidence
        ):
            raise ValueError("Browser execution evidence must bind its exact run and commit")
        available = set(evidence_ids)
        if any(
            not set(item.evidence_ids) <= available for item in self.journey_results
        ):
            raise ValueError("Browser journey result references unavailable evidence")
        _utc(self.started_at, "browser execution started_at")
        _utc(self.completed_at, "browser execution completed_at")
        if self.completed_at < self.started_at:
            raise ValueError("Browser execution time cannot move backwards")
        if self.stage is BrowserExecutionStage.COMPLETED:
            if (
                self.failure_code is not None
                or not self.evidence
                or not self.journey_results
                or any(
                    item.outcome is not EvidenceOutcome.PASS for item in self.evidence
                )
                or any(
                    item.outcome is not EvidenceOutcome.PASS
                    for item in self.journey_results
                )
            ):
                raise ValueError("Completed browser execution cannot retain a failure")
        else:
            _identifier(self.failure_code, "browser failure code")

    @property
    def digest(self) -> str:
        payload = {
            "run_id": self.run_id,
            "product_id": self.product_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "commit_sha": self.commit_sha,
            "stage": self.stage.value,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "run_id": item.run_id,
                    "capability_id": item.capability_id,
                    "journey_id": item.journey_id,
                    "kind": item.kind.value,
                    "outcome": item.outcome.value,
                    "commit_sha": item.commit_sha,
                    "artifact_uri": item.artifact_uri,
                    "digest": item.digest,
                    "observed_at": item.observed_at.isoformat(),
                    "summary": item.summary,
                    "metadata": item.metadata,
                }
                for item in self.evidence
            ],
            "journeys": [
                {
                    "journey_id": item.journey_id,
                    "outcome": item.outcome.value,
                    "evidence_ids": item.evidence_ids,
                    "completed_at": item.completed_at.isoformat(),
                }
                for item in self.journey_results
            ],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "failure_code": self.failure_code,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def _canonical_plan(plan: BrowserJourneyPlan) -> bytes:
    payload = asdict(plan)
    payload["created_at"] = plan.created_at.isoformat()
    for journey in payload["journeys"]:
        for step in journey["steps"]:
            step["action"] = step["action"].value
            if step["locator"] is not None:
                step["locator"]["kind"] = step["locator"]["kind"].value
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return encoded


def _canonical_path(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value != value.strip()
        or "\\" in value
        or "?" in value
        or "#" in value
        or "%" in value
        or "//" in value
        or _has_control(value)
    ):
        raise ValueError(f"{label} must be a canonical absolute URL path")
    decoded = unquote(value)
    if decoded != value and any(part in {".", ".."} for part in decoded.split("/")):
        raise ValueError(f"{label} cannot contain encoded traversal")
    parts = PurePosixPath(value).parts
    if any(part in {".", ".."} for part in parts) or str(PurePosixPath(value)) != value:
        raise ValueError(f"{label} must be canonical")


def _identifier(value: str | None, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")


def _bounded_text(value: str, label: str, *, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _has_control(value)
    ):
        raise ValueError(f"{label} must be bounded text")


def _sha(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} requires a lowercase full commit SHA")


def _digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} requires a lowercase SHA-256 digest")


def _unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _utc(value: datetime, label: str) -> None:
    offset = value.utcoffset() if isinstance(value, datetime) else None
    if not isinstance(value, datetime) or value.tzinfo is None or offset is None:
        raise ValueError(f"{label} must use UTC")
    if offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
