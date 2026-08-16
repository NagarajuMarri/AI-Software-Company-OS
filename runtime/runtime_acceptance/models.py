"""First-class, exact-commit runtime product acceptance domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


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
        if (
            not isinstance(self.required_evidence, tuple)
            or not self.required_evidence
            or any(not isinstance(item, EvidenceKind) for item in self.required_evidence)
            or len(set(self.required_evidence)) != len(self.required_evidence)
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
        if not isinstance(self.required_journey_ids, tuple) or not isinstance(
            self.requirement_ids, tuple
        ):
            raise ValueError("Capability journey and requirement IDs must be tuples")
        if self.locked and not self.required_journey_ids:
            raise ValueError("Locked capability requires customer journeys")
        _unique_text(self.required_journey_ids, "required journey IDs")
        _unique_text(self.requirement_ids, "requirement IDs", allow_empty=True)


@dataclass(frozen=True)
class RuntimeAcceptanceProfile:
    """Stable identity and digest for a locked capability/journey contract."""

    profile_id: str
    version: str
    capabilities: tuple[CapabilityAcceptanceContract, ...]
    journeys: tuple[AcceptanceJourney, ...]

    def __post_init__(self) -> None:
        _identifier(self.profile_id, "acceptance profile ID")
        _text(self.version, "acceptance profile version")
        if (
            not isinstance(self.capabilities, tuple)
            or not isinstance(self.journeys, tuple)
            or not self.capabilities
            or not self.journeys
            or any(
                not isinstance(item, CapabilityAcceptanceContract)
                for item in self.capabilities
            )
            or any(not isinstance(item, AcceptanceJourney) for item in self.journeys)
        ):
            raise ValueError("Acceptance profile requires capabilities and journeys")
        _unique_text(
            tuple(item.capability_id for item in self.capabilities), "capability IDs"
        )
        _unique_text(tuple(item.journey_id for item in self.journeys), "journey IDs")
        journey_by_id = {item.journey_id: item for item in self.journeys}
        referenced: set[str] = set()
        for capability in self.capabilities:
            for journey_id in capability.required_journey_ids:
                journey = journey_by_id.get(journey_id)
                if journey is None or journey.capability_id != capability.capability_id:
                    raise ValueError(
                        "Acceptance profile journeys must match their capability contract"
                    )
                referenced.add(journey_id)
        if referenced != set(journey_by_id):
            raise ValueError("Acceptance profile cannot contain unreferenced journeys")

    @property
    def digest(self) -> str:
        return acceptance_profile_digest(
            self.profile_id,
            self.version,
            self.capabilities,
            self.journeys,
        )


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
        for key, value in self.metadata:
            _text(key, "evidence metadata key")
            _text(value, "evidence metadata value")
            normalized = key.casefold().replace("-", "_")
            if any(
                marker in normalized
                for marker in (
                    "authorization",
                    "api_key",
                    "password",
                    "secret",
                    "session_cookie",
                    "access_token",
                    "refresh_token",
                )
            ):
                raise ValueError("Secret-bearing evidence metadata is prohibited")


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
    evidence_ids: tuple[str, ...]

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
        _unique_text(self.evidence_ids, "human UX evidence IDs")


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
    runtime_configuration_id: str = ""
    runtime_configuration_revision: int = 0
    runtime_configuration_digest: str = ""
    acceptance_profile_id: str = ""
    acceptance_profile_version: str = ""
    acceptance_profile_digest: str = ""

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
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.stage is AcceptanceStage.COMPLETED:
            if self.completed_at is None or self.completed_at != self.updated_at:
                raise ValueError("Completed acceptance requires its exact completion time")
        elif self.completed_at is not None:
            raise ValueError("Only completed acceptance may have completed_at")
        if (
            not isinstance(self.capabilities, tuple)
            or not self.capabilities
            or any(
                not isinstance(item, CapabilityAcceptanceContract)
                for item in self.capabilities
            )
            or not isinstance(self.journeys, tuple)
            or any(not isinstance(item, AcceptanceJourney) for item in self.journeys)
            or not isinstance(self.evidence, tuple)
            or any(not isinstance(item, EvidenceArtifact) for item in self.evidence)
            or not isinstance(self.journey_results, tuple)
            or any(not isinstance(item, JourneyResult) for item in self.journey_results)
            or not isinstance(self.human_acceptances, tuple)
            or any(
                not isinstance(item, HumanAcceptance)
                for item in self.human_acceptances
            )
            or not isinstance(self.blockers, tuple)
        ):
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
        binding = (
            self.runtime_configuration_id,
            self.runtime_configuration_revision,
            self.runtime_configuration_digest,
            self.acceptance_profile_id,
            self.acceptance_profile_version,
            self.acceptance_profile_digest,
        )
        if any(binding):
            if not all(binding):
                raise ValueError("Runtime acceptance configuration binding must be complete")
            _identifier(self.runtime_configuration_id, "runtime configuration ID")
            if (
                isinstance(self.runtime_configuration_revision, bool)
                or not isinstance(self.runtime_configuration_revision, int)
                or self.runtime_configuration_revision < 1
            ):
                raise ValueError("Runtime configuration revision must be positive")
            _canonical_digest(
                self.runtime_configuration_digest, "runtime configuration digest"
            )
            _identifier(self.acceptance_profile_id, "acceptance profile ID")
            _text(self.acceptance_profile_version, "acceptance profile version")
            _canonical_digest(
                self.acceptance_profile_digest, "acceptance profile digest"
            )
            expected_profile = acceptance_profile_digest(
                self.acceptance_profile_id,
                self.acceptance_profile_version,
                self.capabilities,
                self.journeys,
            )
            if self.acceptance_profile_digest != expected_profile:
                raise ValueError(
                    "Runtime acceptance profile digest does not match its locked contract"
                )
        if self.evidence_digest:
            _digest(self.evidence_digest)
            if self.evidence_digest != evidence_digest(self):
                raise ValueError("Stored runtime evidence digest does not match the run")


@dataclass(frozen=True)
class CompletenessReport:
    complete: bool
    blockers: tuple[str, ...]
    capability_ids: tuple[str, ...]
    evidence_digest: str


def evidence_digest(run: RuntimeAcceptanceRun) -> str:
    payload: dict[str, object] = {
        "run_id": run.run_id,
        "product_id": run.product_id,
        "version": run.version,
        "commit_sha": run.commit_sha,
        "capabilities": _capabilities_payload(run.capabilities),
        "journeys": _journeys_payload(run.journeys),
        "journey_results": [
            {
                "id": item.journey_id,
                "outcome": item.outcome.value,
                "evidence": sorted(item.evidence_ids),
                "completed_at": item.completed_at.isoformat(),
            }
            for item in sorted(run.journey_results, key=lambda item: item.journey_id)
        ],
        "evidence": [
            {
                "id": item.evidence_id,
                "capability_id": item.capability_id,
                "journey_id": item.journey_id,
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
    if run.runtime_configuration_id:
        payload["runtime_configuration"] = {
            "id": run.runtime_configuration_id,
            "revision": run.runtime_configuration_revision,
            "digest": run.runtime_configuration_digest,
            "acceptance_profile_id": run.acceptance_profile_id,
            "acceptance_profile_version": run.acceptance_profile_version,
            "acceptance_profile_digest": run.acceptance_profile_digest,
        }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def acceptance_contract_digest(
    capabilities: tuple[CapabilityAcceptanceContract, ...],
    journeys: tuple[AcceptanceJourney, ...],
) -> str:
    """Hash a capability/journey contract independently of a run."""

    payload = {
        "capabilities": _capabilities_payload(capabilities),
        "journeys": _journeys_payload(journeys),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def acceptance_profile_digest(
    profile_id: str,
    profile_version: str,
    capabilities: tuple[CapabilityAcceptanceContract, ...],
    journeys: tuple[AcceptanceJourney, ...],
) -> str:
    """Hash profile identity together with its immutable contract."""

    _identifier(profile_id, "acceptance profile ID")
    _text(profile_version, "acceptance profile version")
    payload = {
        "profile_id": profile_id,
        "profile_version": profile_version,
        "contract_digest": acceptance_contract_digest(capabilities, journeys),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _capabilities_payload(
    capabilities: tuple[CapabilityAcceptanceContract, ...],
) -> list[dict[str, object]]:
    return [
        {
            "id": item.capability_id,
            "version": item.version,
            "title": item.title,
            "journeys": sorted(item.required_journey_ids),
            "requirements": sorted(item.requirement_ids),
            "locked": item.locked,
            "customer_facing": item.customer_facing,
            "human": item.human_acceptance_required,
        }
        for item in sorted(capabilities, key=lambda item: item.capability_id)
    ]


def _journeys_payload(
    journeys: tuple[AcceptanceJourney, ...],
) -> list[dict[str, object]]:
    return [
        {
            "id": item.journey_id,
            "capability_id": item.capability_id,
            "title": item.title,
            "required_evidence": sorted(kind.value for kind in item.required_evidence),
            "customer_facing": item.customer_facing,
        }
        for item in sorted(journeys, key=lambda item: item.journey_id)
    ]


def _text(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 20_000
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} is required and bounded")


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")


def _unique_text(values: tuple[str, ...], label: str, *, allow_empty: bool = False) -> None:
    if (not values and not allow_empty) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be non-empty and unique")
    for value in values:
        _text(value, label)


def _sha(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Runtime evidence requires a full hexadecimal commit SHA")


def _digest(value: str) -> None:
    candidate = value.removeprefix("sha256:")
    if len(candidate) != 64 or any(
        character not in "0123456789abcdef" for character in candidate.lower()
    ):
        raise ValueError("Evidence requires a SHA-256 digest")


def _canonical_digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} requires a lowercase SHA-256 digest")


def _utc(value: datetime, label: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")
