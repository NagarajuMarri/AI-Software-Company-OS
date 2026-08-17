"""Immutable exact-commit Voice capability verification authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import re
from urllib.parse import urlsplit
from pathlib import PurePosixPath

from runtime.runtime_acceptance.models import DeterministicAudioFixture, EvidenceKind
from runtime.runtime_acceptance.profiles import VOICE_JOURNEYS


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_PATH = re.compile(r"^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[0-9a-f]{64}\.wav$")


class VoiceClaim(str, Enum):
    CONSENT_BOUND_CAPTURE = "CONSENT_BOUND_CAPTURE"
    FIXTURE_INTEGRITY_VERIFIED = "FIXTURE_INTEGRITY_VERIFIED"
    NON_SILENT_INPUT = "NON_SILENT_INPUT"
    TRANSCRIPT_EXACT = "TRANSCRIPT_EXACT"
    TURN_PERSISTED = "TURN_PERSISTED"
    RESPONSE_BOUNDED = "RESPONSE_BOUNDED"
    TTS_MEDIA_VERIFIED = "TTS_MEDIA_VERIFIED"
    TTS_NON_SILENT = "TTS_NON_SILENT"
    PLAYBACK_COMPLETED = "PLAYBACK_COMPLETED"
    PLAYBACK_UNMUTED = "PLAYBACK_UNMUTED"
    AVATAR_SPEAKING_OBSERVED = "AVATAR_SPEAKING_OBSERVED"
    AVATAR_IDLE_AFTER_AUDIO = "AVATAR_IDLE_AFTER_AUDIO"
    SECOND_TURN_COMPLETED = "SECOND_TURN_COMPLETED"
    SESSION_CONTINUITY = "SESSION_CONTINUITY"


LOCKED_VOICE_CLAIMS = {
    "voice.capture": (
        VoiceClaim.CONSENT_BOUND_CAPTURE,
        VoiceClaim.FIXTURE_INTEGRITY_VERIFIED,
        VoiceClaim.NON_SILENT_INPUT,
    ),
    "voice.stt": (VoiceClaim.TRANSCRIPT_EXACT,),
    "voice.conversation": (VoiceClaim.TURN_PERSISTED,),
    "voice.llm": (VoiceClaim.RESPONSE_BOUNDED,),
    "voice.tts": (VoiceClaim.TTS_MEDIA_VERIFIED, VoiceClaim.TTS_NON_SILENT),
    "voice.audible_playback": (
        VoiceClaim.PLAYBACK_COMPLETED,
        VoiceClaim.PLAYBACK_UNMUTED,
    ),
    "voice.avatar_synchronization": (
        VoiceClaim.AVATAR_SPEAKING_OBSERVED,
        VoiceClaim.AVATAR_IDLE_AFTER_AUDIO,
    ),
    "voice.repeat_turn": (
        VoiceClaim.SECOND_TURN_COMPLETED,
        VoiceClaim.SESSION_CONTINUITY,
        VoiceClaim.TRANSCRIPT_EXACT,
        VoiceClaim.RESPONSE_BOUNDED,
        VoiceClaim.PLAYBACK_COMPLETED,
        VoiceClaim.AVATAR_IDLE_AFTER_AUDIO,
    ),
}

_NON_BROWSER_EVIDENCE = {
    "voice.capture": (EvidenceKind.AUDIO_FIXTURE, EvidenceKind.SECURITY),
    "voice.stt": (EvidenceKind.AUDIO_FIXTURE, EvidenceKind.STT),
    "voice.conversation": (EvidenceKind.PERSISTENCE,),
    "voice.llm": (EvidenceKind.LLM, EvidenceKind.SECURITY),
    "voice.tts": (EvidenceKind.TTS, EvidenceKind.SECURITY),
    "voice.audible_playback": (EvidenceKind.AUDIBLE_PLAYBACK,),
    "voice.avatar_synchronization": (EvidenceKind.AVATAR_SYNCHRONIZATION,),
    "voice.repeat_turn": (
        EvidenceKind.AUDIO_FIXTURE,
        EvidenceKind.STT,
        EvidenceKind.LLM,
        EvidenceKind.TTS,
        EvidenceKind.AUDIBLE_PLAYBACK,
        EvidenceKind.AVATAR_SYNCHRONIZATION,
        EvidenceKind.PERSISTENCE,
    ),
}


@dataclass(frozen=True)
class VoiceJourneyVerification:
    journey_id: str
    required_step_ids: tuple[str, ...]
    claims: tuple[VoiceClaim, ...]
    evidence_kinds: tuple[EvidenceKind, ...]

    def __post_init__(self) -> None:
        _identifier(self.journey_id, "voice journey ID")
        if (
            not isinstance(self.required_step_ids, tuple)
            or not self.required_step_ids
            or len(self.required_step_ids) > 100
            or any(not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) for value in self.required_step_ids)
            or len(self.required_step_ids) != len(set(self.required_step_ids))
        ):
            raise ValueError("Voice verification requires unique safe step IDs")
        if self.claims != LOCKED_VOICE_CLAIMS.get(self.journey_id):
            raise ValueError("Voice claims do not match the locked journey")
        if self.evidence_kinds != _NON_BROWSER_EVIDENCE.get(self.journey_id):
            raise ValueError("Voice evidence kinds do not match the locked journey")


@dataclass(frozen=True)
class VoiceVerificationPlan:
    verification_id: str
    run_id: str
    product_id: str
    browser_plan_id: str
    browser_plan_digest: str
    configuration_id: str
    configuration_revision: int
    configuration_digest: str
    commit_sha: str
    acceptance_profile_id: str
    acceptance_profile_version: str
    acceptance_profile_digest: str
    provider_id: str
    journeys: tuple[VoiceJourneyVerification, ...]
    input_fixture: DeterministicAudioFixture
    output_fixture: DeterministicAudioFixture
    input_media_path: str
    output_media_path: str
    expected_response: str
    maximum_response_characters: int
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.verification_id, "voice verification ID"),
            (self.run_id, "voice run ID"),
            (self.product_id, "voice product ID"),
            (self.browser_plan_id, "voice browser plan ID"),
            (self.configuration_id, "voice configuration ID"),
            (self.acceptance_profile_id, "voice profile ID"),
            (self.provider_id, "voice provider ID"),
        ):
            _identifier(value, label)
        for value, label in (
            (self.browser_plan_digest, "browser plan digest"),
            (self.configuration_digest, "configuration digest"),
            (self.acceptance_profile_digest, "profile digest"),
        ):
            _digest(value, label)
        if not isinstance(self.commit_sha, str) or not _SHA.fullmatch(self.commit_sha):
            raise ValueError("Voice plan requires a lowercase full commit SHA")
        if (
            isinstance(self.configuration_revision, bool)
            or not isinstance(self.configuration_revision, int)
            or self.configuration_revision < 1
        ):
            raise ValueError("Voice configuration revision must be positive")
        if (
            not isinstance(self.journeys, tuple)
            or any(not isinstance(value, VoiceJourneyVerification) for value in self.journeys)
            or tuple(value.journey_id for value in self.journeys) != VOICE_JOURNEYS
        ):
            raise ValueError("Voice plan must contain every locked journey in order")
        if not isinstance(self.input_fixture, DeterministicAudioFixture) or not isinstance(
            self.output_fixture, DeterministicAudioFixture
        ):
            raise ValueError("Voice plan requires immutable input and output audio fixtures")
        if self.input_fixture.fixture_id == self.output_fixture.fixture_id:
            raise ValueError("Voice input and output fixtures must be distinct")
        for fixture in (self.input_fixture, self.output_fixture):
            _fixture(fixture, self.product_id, self.run_id)
        _path(self.input_media_path, "voice input media path")
        _path(self.output_media_path, "voice output media path")
        if self.input_media_path == self.output_media_path:
            raise ValueError("Voice input and output media paths must be distinct")
        if (
            isinstance(self.maximum_response_characters, bool)
            or not isinstance(self.maximum_response_characters, int)
            or not 1 <= self.maximum_response_characters <= 4_000
        ):
            raise ValueError("Voice response bound is outside policy")
        _bounded(self.expected_response, "expected tutor response", self.maximum_response_characters)
        _bounded(self.acceptance_profile_version, "profile version", 128)
        _bounded(self.created_by, "voice plan creator", 256)
        _utc(self.created_at, "voice plan created_at")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        for journey in payload["journeys"]:
            journey["claims"] = [value.value for value in journey["claims"]]
            journey["evidence_kinds"] = [value.value for value in journey["evidence_kinds"]]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def _fixture(value: DeterministicAudioFixture, product_id: str, run_id: str) -> None:
    parsed = urlsplit(value.artifact_uri)
    if (
        parsed.scheme != "artifact"
        or parsed.netloc != "browser"
        or parsed.query
        or parsed.fragment
        or not _ARTIFACT_PATH.fullmatch(parsed.path)
        or parsed.path.split("/")[1:3] != [product_id, run_id]
        or value.media_type != "audio/wav"
        or not 8_000 <= value.sample_rate_hz <= 48_000
        or value.channels not in {1, 2}
        or not 100 <= value.duration_ms <= 10_000
    ):
        raise ValueError("Voice audio fixture is outside policy or authority")


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")


def _path(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value != value.strip()
        or "\\" in value
        or "?" in value
        or "#" in value
        or "%" in value
        or "//" in value
        or any(part in {".", ".."} for part in PurePosixPath(value).parts)
        or str(PurePosixPath(value)) != value
    ):
        raise ValueError(f"{label} must be a canonical absolute URL path")


def _digest(value: str, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


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
    if not isinstance(value, datetime) or value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")
