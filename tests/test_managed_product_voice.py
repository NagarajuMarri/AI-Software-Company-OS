from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import struct
import wave

import pytest

from runtime.managed_product_browser import (
    BrowserActionKind,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserJourneyPlan,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
    BrowserStep,
    ContentAddressedBrowserArtifactStore,
)
from runtime.managed_product_runtime import (
    CommandSpec,
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    OneShotCommand,
    ReadinessProbe,
)
from runtime.managed_product_voice import (
    FileVoiceVerificationPlanStore,
    LOCKED_VOICE_CLAIMS,
    VoiceEvidenceBrowserProvider,
    VoiceJourneyVerification,
    VoicePlanError,
    VoiceVerificationError,
    VoiceVerificationPlan,
)
from runtime.runtime_acceptance import (
    DeterministicAudioFixture,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
    VOICE_JOURNEYS,
    speakmate_v1_profile,
)


NOW = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
TRANSCRIPT = "Hello, I would like to practise English."
RESPONSE = "Great start. Please tell me about your day."
NON_BROWSER = {
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
REQUIRED_STEPS = {
    "voice.capture": ("capture-verified",),
    "voice.stt": ("transcript-exact",),
    "voice.conversation": ("turn-persisted",),
    "voice.llm": ("response-bounded",),
    "voice.tts": ("tts-generated",),
    "voice.audible_playback": ("audio-played",),
    "voice.avatar_synchronization": ("avatar-synchronized",),
    "voice.repeat_turn": (
        "second-transcript-exact",
        "second-response-bounded",
        "second-turn-complete",
        "second-audio-played",
    ),
}


class _FakeBrowser:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, plan, configuration, inputs, redactions, artifact_store):
        self.calls += 1
        evidence = []
        results = []
        for journey in plan.journeys:
            steps = []
            for step in journey.steps:
                item = {"step_id": step.step_id, "outcome": "PASS"}
                if step.action is BrowserActionKind.ASSERT_MEDIA_PLAYED:
                    item.update(
                        duration_ms=400,
                        played_ms=400,
                        muted=False,
                        volume_milli=1000,
                    )
                steps.append(item)
            uri, digest = artifact_store.write_json(
                plan.product_id,
                plan.run_id,
                {
                    "provider_id": "fake",
                    "plan_digest": plan.digest,
                    "journey_id": journey.journey_id,
                    "outcome": "PASS",
                    "failure_code": None,
                    "steps": steps,
                },
            )
            artifact = EvidenceArtifact(
                f"{plan.run_id}.{journey.journey_id}.browser",
                plan.run_id,
                "VOICE",
                journey.journey_id,
                EvidenceKind.BROWSER,
                EvidenceOutcome.PASS,
                plan.commit_sha,
                uri,
                digest,
                NOW,
                "passed",
            )
            evidence.append(artifact)
            results.append(
                JourneyResult(
                    journey.journey_id,
                    EvidenceOutcome.PASS,
                    (artifact.evidence_id,),
                    NOW,
                )
            )
        return BrowserExecutionResult(
            plan.run_id,
            plan.product_id,
            plan.plan_id,
            plan.digest,
            plan.commit_sha,
            BrowserExecutionStage.COMPLETED,
            tuple(evidence),
            tuple(results),
            NOW,
            NOW,
        )


def _wav(frequency: int) -> bytes:
    stream = BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(
            b"".join(
                struct.pack("<h", round(10_000 * math.sin(2 * math.pi * frequency * i / 16_000)))
                for i in range(6_400)
            )
        )
    return stream.getvalue()


def _fixtures(store):
    input_uri, input_digest = store.write_bytes("product", "voice-run", _wav(440), "wav")
    output_uri, output_digest = store.write_bytes("product", "voice-run", _wav(660), "wav")
    return (
        DeterministicAudioFixture(
            "learner-turn", input_uri, input_digest, "audio/wav", 16_000, 1, 400, TRANSCRIPT
        ),
        DeterministicAudioFixture(
            "tutor-turn", output_uri, output_digest, "audio/wav", 16_000, 1, 400, RESPONSE
        ),
    )


def _configuration():
    profile = speakmate_v1_profile()
    return ManagedProductRuntimeConfiguration(
        "voice-runtime",
        "product",
        1,
        "https://github.com/example/product.git",
        "main",
        "a" * 40,
        "http://127.0.0.1:8123/",
        "http://127.0.0.1:8123/api",
        ("http://127.0.0.1:8123",),
        (OneShotCommand("migrate", CommandSpec("python", ("migrate.py",)), 10),),
        (
            ManagedRuntimeService(
                "app",
                CommandSpec("python", ("service.py",)),
                ReadinessProbe("ready", "http://127.0.0.1:8123/health", (204,), 10, 1),
                OneShotCommand("stop", CommandSpec("python", ("stop.py",)), 10),
                10,
                5,
            ),
        ),
        (),
        (),
        (),
        profile.profile_id,
        profile.version,
        profile.digest,
        "test",
        NOW,
    )


def _browser_plan(configuration=None):
    configuration = configuration or _configuration()
    profile = speakmate_v1_profile()
    contracts = {
        value.journey_id: value for value in profile.journeys if value.capability_id == "VOICE"
    }
    journeys = []
    for journey_id in VOICE_JOURNEYS:
        steps = []
        for step_id in REQUIRED_STEPS[journey_id]:
            if "audio-played" in step_id:
                steps.append(
                    BrowserStep(
                        step_id,
                        BrowserActionKind.ASSERT_MEDIA_PLAYED,
                        BrowserLocator(BrowserLocatorKind.TEST_ID, "tutor-audio"),
                    )
                )
            else:
                expected = (
                    TRANSCRIPT
                    if journey_id == "voice.stt" or "transcript" in step_id
                    else RESPONSE
                    if journey_id == "voice.llm" or "response" in step_id
                    else "Verified"
                )
                steps.append(
                    BrowserStep(
                        step_id,
                        BrowserActionKind.ASSERT_TEXT,
                        BrowserLocator(BrowserLocatorKind.TEXT, expected),
                        expected_text=expected,
                    )
                )
        journeys.append(
            BrowserJourneySpecification(
                journey_id,
                "VOICE",
                contracts[journey_id].title,
                f"/verify/{journey_id.split('.', 1)[1].replace('_', '-')}",
                tuple(steps),
            )
        )
    return BrowserJourneyPlan(
        "voice-browser-v1",
        "voice-run",
        configuration.project_id,
        configuration.configuration_id,
        configuration.revision,
        configuration.digest,
        configuration.commit_sha,
        profile.profile_id,
        profile.version,
        profile.digest,
        tuple(journeys),
        (),
        "test",
        NOW,
    )


def _voice_plan(artifact_store, browser=None, **changes):
    browser = browser or _browser_plan()
    input_fixture, output_fixture = _fixtures(artifact_store)
    fields = dict(
        verification_id="voice-verification-v1",
        run_id=browser.run_id,
        product_id=browser.product_id,
        browser_plan_id=browser.plan_id,
        browser_plan_digest=browser.digest,
        configuration_id=browser.configuration_id,
        configuration_revision=browser.configuration_revision,
        configuration_digest=browser.configuration_digest,
        commit_sha=browser.commit_sha,
        acceptance_profile_id=browser.acceptance_profile_id,
        acceptance_profile_version=browser.acceptance_profile_version,
        acceptance_profile_digest=browser.acceptance_profile_digest,
        provider_id="playwright-voice-v1",
        journeys=tuple(
            VoiceJourneyVerification(
                journey_id,
                REQUIRED_STEPS[journey_id],
                LOCKED_VOICE_CLAIMS[journey_id],
                NON_BROWSER[journey_id],
            )
            for journey_id in VOICE_JOURNEYS
        ),
        input_fixture=input_fixture,
        output_fixture=output_fixture,
        input_media_path="/media/learner.wav",
        output_media_path="/media/tutor.wav",
        expected_response=RESPONSE,
        maximum_response_characters=256,
        created_by="test",
        created_at=NOW,
    )
    fields.update(changes)
    return VoiceVerificationPlan(**fields)


def test_voice_plan_is_exact_deeply_immutable_and_digest_bound(tmp_path):
    store = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    value = _voice_plan(store)
    assert tuple(item.journey_id for item in value.journeys) == VOICE_JOURNEYS
    assert value.digest != replace(value, expected_response=RESPONSE + " Again.").digest
    with pytest.raises(ValueError, match="every locked journey"):
        replace(value, journeys=value.journeys[:-1])
    with pytest.raises(ValueError, match="claims"):
        replace(value.journeys[0], claims=value.journeys[1].claims)
    with pytest.raises(ValueError, match="canonical"):
        replace(value, output_media_path="/media/../tutor.wav")


def test_file_voice_plan_restart_immutability_and_tamper(tmp_path):
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    value = _voice_plan(artifacts)
    root = tmp_path / "plans"
    store = FileVoiceVerificationPlanStore(root)
    assert store.save(value) == value
    assert FileVoiceVerificationPlanStore(root).load(
        value.product_id, value.run_id, value.verification_id
    ) == value
    with pytest.raises(VoicePlanError, match="immutable"):
        store.save(replace(value, expected_response=RESPONSE + " Again."))
    path = root / value.product_id / value.run_id / f"{value.verification_id}.json"
    payload = json.loads(path.read_text())
    payload["digest"] = "b" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(VoicePlanError, match="corrupt"):
        store.load(value.product_id, value.run_id, value.verification_id)


def test_voice_provider_derives_complete_locked_evidence(monkeypatch, tmp_path):
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    browser = _browser_plan()
    value = _voice_plan(artifacts, browser)
    plans = FileVoiceVerificationPlanStore(tmp_path / "plans")
    plans.save(value)
    fake = _FakeBrowser()
    monkeypatch.setattr(
        "runtime.managed_product_voice.provider._fetch_media",
        lambda configuration, path: artifacts.read_bytes(
            value.input_fixture.artifact_uri if "learner" in path else value.output_fixture.artifact_uri,
            value.input_fixture.digest if "learner" in path else value.output_fixture.digest,
        ),
    )
    result = VoiceEvidenceBrowserProvider(
        value.provider_id, value.verification_id, plans, fake
    ).execute(browser, _configuration(), {}, (), artifacts)
    assert result.stage is BrowserExecutionStage.COMPLETED
    assert fake.calls == 1
    assert tuple(item.journey_id for item in result.journey_results) == VOICE_JOURNEYS
    assert {item.kind for item in result.evidence} >= {
        EvidenceKind.AUDIO_FIXTURE,
        EvidenceKind.STT,
        EvidenceKind.LLM,
        EvidenceKind.TTS,
        EvidenceKind.AUDIBLE_PLAYBACK,
        EvidenceKind.AVATAR_SYNCHRONIZATION,
        EvidenceKind.PERSISTENCE,
        EvidenceKind.SECURITY,
    }


def test_voice_provider_fails_closed_for_media_mismatch(monkeypatch, tmp_path):
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    browser = _browser_plan()
    value = _voice_plan(artifacts, browser)
    plans = FileVoiceVerificationPlanStore(tmp_path / "plans")
    plans.save(value)
    monkeypatch.setattr(
        "runtime.managed_product_voice.provider._fetch_media", lambda configuration, path: b"bad"
    )
    result = VoiceEvidenceBrowserProvider(
        value.provider_id, value.verification_id, plans, _FakeBrowser()
    ).execute(browser, _configuration(), {}, (), artifacts)
    assert result.stage is BrowserExecutionStage.FAILED
    assert result.failure_code == "VOICE_EVIDENCE_FAILED"
    assert all(item.outcome is EvidenceOutcome.FAIL for item in result.journey_results)


def test_voice_authority_mismatch_blocks_before_browser_effect(tmp_path):
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    browser = _browser_plan()
    value = _voice_plan(artifacts, browser)
    plans = FileVoiceVerificationPlanStore(tmp_path / "plans")
    plans.save(value)
    fake = _FakeBrowser()
    provider = VoiceEvidenceBrowserProvider("wrong-provider", value.verification_id, plans, fake)
    with pytest.raises(VoiceVerificationError, match="provider"):
        provider.execute(browser, _configuration(), {}, (), artifacts)
    assert fake.calls == 0


def test_media_action_requires_a_locator():
    with pytest.raises(ValueError, match="locator"):
        BrowserStep("played", BrowserActionKind.ASSERT_MEDIA_PLAYED)


def test_audio_artifact_bytes_are_digest_verified(tmp_path):
    store = ContentAddressedBrowserArtifactStore(tmp_path)
    content = _wav(440)
    uri, digest = store.write_bytes("product", "voice-run", content, "wav")
    assert store.read_bytes(uri, digest) == content
    path = store.resolve(uri)
    path.write_bytes(content + b"tamper")
    with pytest.raises(Exception, match="integrity"):
        store.read_bytes(uri, digest)
