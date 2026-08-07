"""First-class, exact-commit runtime product acceptance domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AcceptanceStage(str, Enum):
    PLANNED = "PLANNED"
    IMPLEMENTED = "IMPLEMENTED"
    AUTOMATED_VERIFIED = "AUTOMATED_VERIFIED"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"
    HUMAN_ACCEPTANCE_REQUIRED = "HUMAN_ACCEPTANCE_REQUIRED"
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"


class EvidenceOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class EvidenceKind(str, Enum):
    CODE = "CODE_EVIDENCE"
    AUTOMATED_TEST = "AUTOMATED_TEST_EVIDENCE"
    SERVICE_STARTUP = "SERVICE_STARTUP_EVIDENCE"
    READINESS = "READINESS_EVIDENCE"
    MIGRATION = "MIGRATION_EVIDENCE"
    BROWSER = "BROWSER_EVIDENCE"
    BROWSER_CONSOLE = "BROWSER_CONSOLE_EVIDENCE"
    BROWSER_NETWORK = "BROWSER_NETWORK_EVIDENCE"
    SCREENSHOT = "SCREENSHOT_EVIDENCE"
    AUDIO_FIXTURE = "AUDIO_FIXTURE_EVIDENCE"
    STT = "STT_EVIDENCE"
    LLM = "LLM_EVIDENCE"
    TTS = "TTS_EVIDENCE"
    AUDIBLE_PLAYBACK = "AUDIBLE_PLAYBACK_EVIDENCE"
    AVATAR_SYNCHRONIZATION = "AVATAR_SYNCHRONIZATION_EVIDENCE"
    PERSISTENCE = "PERSISTENCE_EVIDENCE"
    PWA = "PWA_EVIDENCE"
    SECURITY = "SECURITY_EVIDENCE"
    HUMAN_UX = "HUMAN_UX_EVIDENCE"


@dataclass(frozen=True)
class AcceptanceJourney:
    journey_id: str
    capability_id: str
    title: str
    required_evidence: tuple[EvidenceKind, ...]
    customer_facing: bool = True

    def __post_init__(self) -> None:
        _text(self.journey_id, "journey ID")
        _text(self.capability_id, "capability ID")
        _text(self.title, "journey title")
        if not self.required_evidence or len(set(self.required_evidence)) != len(
            self.required_evidence
        ):
            raise ValueError("Journey requires unique evidence kinds")


@dataclass(frozen=True)
class CapabilityAcceptanceContract:
    capability_id: str
    version: str
    title: str
    required_journey_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...] = ()
    locked: bool = True
    customer_facing: bool = True
    human_acceptance_required: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.capability_id, "capability ID"),
            (self.version, "capability version"),
            (self.title, "capability title"),
        ):
            _text(value, label)
        if self.locked and not self.required_journey_ids:
            raise ValueError("Locked capability requires customer journeys")
        _unique_text(self.required_journey_ids, "required journey IDs")
        _unique_text(self.requirement_ids, "requirement IDs", allow_empty=True)


@dataclass(frozen=True)
class EvidenceArtifact:
    evidence_id: str
    run_id: str
    capability_id: str
    journey_id: str
    kind: EvidenceKind
    outcome: EvidenceOutcome
    commit_sha: str
    artifact_uri: str
    digest: str
    observed_at: datetime
    summary: str
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value, label in (
            (self.evidence_id, "evidence ID"),
            (self.run_id, "run ID"),
            (self.capability_id, "capability ID"),
            (self.journey_id, "journey ID"),
            (self.artifact_uri, "artifact URI"),
            (self.summary, "evidence summary"),
        ):
            _text(value, label)
        _sha(self.commit_sha)
        _digest(self.digest)
        _utc(self.observed_at, "observed_at")
        if len(set(key for key, _ in self.metadata)) != len(self.metadata):
            raise ValueError("Evidence metadata keys must be unique")


@dataclass(frozen=True)
class JourneyResult:
    journey_id: str
    outcome: EvidenceOutcome
    evidence_ids: tuple[str, ...]
    completed_at: datetime

    def __post_init__(self) -> None:
        _text(self.journey_id, "journey ID")
        _unique_text(self.evidence_ids, "evidence IDs")
        _utc(self.completed_at, "completed_at")


@dataclass(frozen=True)
class HumanAcceptance:
    capability_id: str
    reviewer: str
    decision: str
    rationale: str
    commit_sha: str
    evidence_digest: str
    accepted_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.capability_id, "capability ID"),
            (self.reviewer, "reviewer"),
            (self.rationale, "acceptance rationale"),
        ):
            _text(value, label)
        if self.decision not in {"ACCEPT", "REJECT"}:
            raise ValueError("Human acceptance decision must be ACCEPT or REJECT")
        _sha(self.commit_sha)
        _digest(self.evidence_digest)
        _utc(self.accepted_at, "accepted_at")


@dataclass(frozen=True)
class DeterministicAudioFixture:
    fixture_id: str
    artifact_uri: str
    digest: str
    media_type: str
    sample_rate_hz: int
    channels: int
    duration_ms: int
    expected_transcript: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.fixture_id, "fixture ID"),
            (self.artifact_uri, "fixture artifact URI"),
            (self.media_type, "fixture media type"),
            (self.expected_transcript, "expected transcript"),
        ):
            _text(value, label)
        _digest(self.digest)
        if self.sample_rate_hz <= 0 or self.channels <= 0 or self.duration_ms <= 0:
            raise ValueError("Audio fixture dimensions must be positive")


@dataclass(frozen=True)
class RuntimeAcceptanceRun:
    run_id: str
    product_id: str
    version: str
    commit_sha: str
    stage: AcceptanceStage
    capabilities: tuple[CapabilityAcceptanceContract, ...]
    journeys: tuple[AcceptanceJourney, ...]
    created_at: datetime
    updated_at: datetime
    evidence: tuple[EvidenceArtifact, ...] = ()
    journey_results: tuple[JourneyResult, ...] = ()
    human_acceptances: tuple[HumanAcceptance, ...] = ()
    completed_at: datetime | None = None
    evidence_digest: str = ""
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_id, "run ID"),
            (self.product_id, "product ID"),
            (self.version, "acceptance version"),
        ):
            _text(value, label)
        _sha(self.commit_sha)
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")
        if self.completed_at is not None:
            _utc(self.completed_at, "completed_at")
        if not self.capabilities:
            raise ValueError("Runtime acceptance requires capabilities")
        _unique_text(
            tuple(item.capability_id for item in self.capabilities), "capability IDs"
        )
        _unique_text(tuple(item.journey_id for item in self.journeys), "journey IDs")
        _unique_text(
            tuple(item.evidence_id for item in self.evidence),
            "evidence IDs",
            allow_empty=True,
        )
        _unique_text(
            tuple(item.journey_id for item in self.journey_results),
            "journey result IDs",
            allow_empty=True,
        )
        if self.evidence_digest:
            _digest(self.evidence_digest)


@dataclass(frozen=True)
class CompletenessReport:
    complete: bool
    blockers: tuple[str, ...]
    capability_ids: tuple[str, ...]
    evidence_digest: str


def evidence_digest(run: RuntimeAcceptanceRun) -> str:
    payload = {
        "run_id": run.run_id,
        "product_id": run.product_id,
        "version": run.version,
        "commit_sha": run.commit_sha,
        "capabilities": [
            {
                "id": item.capability_id,
                "version": item.version,
                "journeys": sorted(item.required_journey_ids),
                "human": item.human_acceptance_required,
            }
            for item in sorted(run.capabilities, key=lambda item: item.capability_id)
        ],
        "journeys": [
            {
                "id": item.journey_id,
                "outcome": item.outcome.value,
                "evidence": sorted(item.evidence_ids),
            }
            for item in sorted(run.journey_results, key=lambda item: item.journey_id)
        ],
        "evidence": [
            {
                "id": item.evidence_id,
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "commit": item.commit_sha,
                "artifact_uri": item.artifact_uri,
                "digest": item.digest,
                "observed_at": item.observed_at.isoformat(),
                "summary": item.summary,
                "metadata": sorted(item.metadata),
            }
            for item in sorted(run.evidence, key=lambda item: item.evidence_id)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 20_000:
        raise ValueError(f"{label} is required and bounded")


def _unique_text(values: tuple[str, ...], label: str, *, allow_empty: bool = False) -> None:
    if (not values and not allow_empty) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be non-empty and unique")
    for value in values:
        _text(value, label)


def _sha(value: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise ValueError("Runtime evidence requires a full hexadecimal commit SHA")


def _digest(value: str) -> None:
    candidate = value.removeprefix("sha256:")
    if len(candidate) != 64 or any(
        character not in "0123456789abcdef" for character in candidate.lower()
    ):
        raise ValueError("Evidence requires a SHA-256 digest")


def _utc(value: datetime, label: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")
