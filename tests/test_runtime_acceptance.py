from dataclasses import replace
from datetime import datetime, timezone
import hashlib

import pytest

from runtime.release_management import (
    Release,
    ReleaseCandidate,
    ReleaseKind,
    ReleaseManagementService,
    ReleaseStatus,
    ReleaseStore,
    Version,
)
from runtime.runtime_acceptance import *  # noqa: F403


NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)
LATER = datetime(2026, 8, 8, tzinfo=timezone.utc)
SHA = "a" * 40


def contract(*, human=False):
    return CapabilityAcceptanceContract(
        "AUTHENTICATION",
        "1.0",
        "Authentication",
        ("authentication.full",),
        human_acceptance_required=human,
    )


def journey():
    return AcceptanceJourney(
        "authentication.full",
        "AUTHENTICATION",
        "Complete account journey",
        (EvidenceKind.BROWSER, EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
    )


def run(*, capabilities=None, journeys=None):
    return RuntimeAcceptanceRun(
        "run-1",
        "spoken-english-ai",
        "1.0",
        SHA,
        AcceptanceStage.PLANNED,
        tuple(capabilities or (contract(),)),
        tuple(journeys or (journey(),)),
        NOW,
        NOW,
    )


def artifact(kind, journey_id="authentication.full", capability_id="AUTHENTICATION", *, index=0, commit=SHA):
    identity = f"{journey_id}-{kind.value}-{index}"
    return EvidenceArtifact(
        identity,
        "run-1",
        capability_id,
        journey_id,
        kind,
        EvidenceOutcome.PASS,
        commit,
        f"artifact://{identity}",
        hashlib.sha256(identity.encode()).hexdigest(),
        NOW,
        f"Verified {kind.value}",
    )


def automated_evidence():
    return (artifact(EvidenceKind.CODE), artifact(EvidenceKind.AUTOMATED_TEST))


def runtime_evidence(target=journey()):
    kinds = set(target.required_evidence) | {
        EvidenceKind.SERVICE_STARTUP,
        EvidenceKind.READINESS,
        EvidenceKind.MIGRATION,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
    }
    values = tuple(artifact(kind, target.journey_id, target.capability_id) for kind in sorted(kinds, key=lambda x: x.value))
    return values, JourneyResult(
        target.journey_id,
        EvidenceOutcome.PASS,
        tuple(item.evidence_id for item in values),
        NOW,
    )


def completed_acceptance(store, *, human=False):
    service = RuntimeAcceptanceService(store)
    value = service.plan(run(capabilities=(contract(human=human),)))
    value = service.mark_implemented(value.product_id, value.run_id, NOW)
    value = service.record_automated_verification(value.product_id, value.run_id, automated_evidence(), NOW)
    evidence, result = runtime_evidence()
    value = service.record_runtime_verification(value.product_id, value.run_id, evidence, (result,), NOW)
    if human:
        value = service.request_human_acceptance(value.product_id, value.run_id, NOW)
        value = service.record_human_acceptance(
            value.product_id,
            value.run_id,
            HumanAcceptance(
                "AUTHENTICATION",
                "founder",
                "ACCEPT",
                "Browser journey accepted",
                SHA,
                evidence_digest(value),
                NOW,
            ),
        )
    value = service.accept(value.product_id, value.run_id, NOW)
    return service.complete(value.product_id, value.run_id, LATER)


class EventRecorder:
    def __init__(self):
        self.names = []

    def publish(self, event_type, aggregate_type, aggregate_id, payload):
        assert aggregate_type == "RUNTIME_ACCEPTANCE"
        assert aggregate_id == "run-1"
        assert payload["commit_sha"] == SHA
        self.names.append(event_type.value)


def test_exact_runtime_acceptance_lifecycle():
    assert [item.value for item in AcceptanceStage] == [
        "PLANNED",
        "IMPLEMENTED",
        "AUTOMATED_VERIFIED",
        "RUNTIME_VERIFIED",
        "HUMAN_ACCEPTANCE_REQUIRED",
        "ACCEPTED",
        "COMPLETED",
    ]


def test_full_objective_lifecycle_is_exact_commit_bound(tmp_path):
    value = completed_acceptance(RuntimeAcceptanceStore(tmp_path))
    assert value.stage is AcceptanceStage.COMPLETED
    assert value.evidence_digest == evidence_digest(value)
    assert {item.commit_sha for item in value.evidence} == {SHA}


def test_runtime_acceptance_emits_typed_lifecycle_events(tmp_path):
    recorder = EventRecorder()
    service = RuntimeAcceptanceService(RuntimeAcceptanceStore(tmp_path), recorder)
    value = service.plan(run())
    value = service.mark_implemented(value.product_id, value.run_id, NOW)
    value = service.record_automated_verification(
        value.product_id, value.run_id, automated_evidence(), NOW
    )
    evidence, result = runtime_evidence()
    value = service.record_runtime_verification(
        value.product_id, value.run_id, evidence, (result,), NOW
    )
    value = service.accept(value.product_id, value.run_id, NOW)
    service.complete(value.product_id, value.run_id, LATER)
    assert recorder.names == [
        "RUNTIME_ACCEPTANCE_PLANNED",
        "RUNTIME_ACCEPTANCE_IMPLEMENTED",
        "AUTOMATED_VERIFICATION_PASSED",
        "RUNTIME_VERIFICATION_PASSED",
        "RUNTIME_ACCEPTANCE_ACCEPTED",
        "RUNTIME_ACCEPTANCE_COMPLETED",
    ]


def test_human_ux_gate_is_explicit_and_persisted(tmp_path):
    store = RuntimeAcceptanceStore(tmp_path)
    value = completed_acceptance(store, human=True)
    assert value.human_acceptances[0].reviewer == "founder"
    assert store.load(value.product_id, value.run_id) == value


def test_stale_runtime_evidence_is_rejected(tmp_path):
    service = RuntimeAcceptanceService(RuntimeAcceptanceStore(tmp_path))
    value = service.mark_implemented("spoken-english-ai", service.plan(run()).run_id, NOW)
    with pytest.raises(RuntimeAcceptanceError, match="stale"):
        service.record_automated_verification(
            value.product_id,
            value.run_id,
            (artifact(EvidenceKind.CODE, commit="b" * 40), artifact(EvidenceKind.AUTOMATED_TEST)),
            NOW,
        )


def test_global_startup_readiness_migration_and_browser_artifacts_are_required(tmp_path):
    service = RuntimeAcceptanceService(RuntimeAcceptanceStore(tmp_path))
    value = service.mark_implemented("spoken-english-ai", service.plan(run()).run_id, NOW)
    value = service.record_automated_verification(value.product_id, value.run_id, automated_evidence(), NOW)
    values = tuple(artifact(kind) for kind in journey().required_evidence)
    result = JourneyResult("authentication.full", EvidenceOutcome.PASS, tuple(x.evidence_id for x in values), NOW)
    with pytest.raises(RuntimeAcceptanceError, match="MISSING_GLOBAL"):
        service.record_runtime_verification(value.product_id, value.run_id, values, (result,), NOW)


def test_completed_evidence_is_immutable_after_restart(tmp_path):
    store = RuntimeAcceptanceStore(tmp_path)
    value = completed_acceptance(store)
    restarted = RuntimeAcceptanceStore(tmp_path)
    assert restarted.load(value.product_id, value.run_id) == value
    with pytest.raises(ValueError, match="immutable"):
        restarted.save(replace(value, blockers=("tampered",)))


def release(**changes):
    values = dict(
        release_id="release-1",
        product_ids=("spoken-english-ai",),
        version=Version.parse("1.0.0"),
        kind=ReleaseKind.STABLE,
        status=ReleaseStatus.PLANNED,
        title="SpeakMate RC1",
        created_by="owner",
        created_at=NOW,
        updated_at=NOW,
        commit_shas=(SHA,),
        locked_capability_ids=("AUTHENTICATION",),
        runtime_acceptance_run_ids=("run-1",),
    )
    values.update(changes)
    return Release(**values)


def candidate():
    return ReleaseCandidate("rc-1", Version.parse("1.0.0-rc.1"), SHA, "owner", NOW)


def test_release_candidate_review_is_blocked_without_runtime_acceptance(tmp_path):
    service = ReleaseManagementService(ReleaseStore(tmp_path / "releases"))
    value = service.create_candidate(service.create(release()), candidate(), NOW)
    with pytest.raises(ValueError, match="runtime-ready"):
        service.submit(value, NOW)
    assert "RUNTIME_ACCEPTANCE_STORE_UNAVAILABLE" in service.readiness(value).blockers


def test_release_candidate_review_accepts_only_completed_matching_capabilities(tmp_path):
    acceptance_store = RuntimeAcceptanceStore(tmp_path / "acceptance")
    completed_acceptance(acceptance_store)
    service = ReleaseManagementService(
        ReleaseStore(tmp_path / "releases"),
        runtime_acceptance_store=acceptance_store,
    )
    value = service.create_candidate(service.create(release()), candidate(), NOW)
    assert service.readiness(value).ready
    assert service.submit(value, NOW).status is ReleaseStatus.UNDER_REVIEW


def test_release_rejects_automated_only_acceptance(tmp_path):
    acceptance_store = RuntimeAcceptanceStore(tmp_path / "acceptance")
    acceptance = RuntimeAcceptanceService(acceptance_store)
    value = acceptance.mark_implemented("spoken-english-ai", acceptance.plan(run()).run_id, NOW)
    acceptance.record_automated_verification(value.product_id, value.run_id, automated_evidence(), NOW)
    service = ReleaseManagementService(
        ReleaseStore(tmp_path / "releases"), runtime_acceptance_store=acceptance_store
    )
    rc = service.create_candidate(service.create(release()), candidate(), NOW)
    assert "INCOMPLETE_RUNTIME_ACCEPTANCE:run-1:AUTOMATED_VERIFIED" in service.readiness(rc).blockers


class RecordingProvider:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            raise RuntimeError(name)
        return RuntimeProbeResult(())

    def verify_commit(self, expected_commit_sha):
        assert expected_commit_sha == SHA
        return self._call("commit")

    def verify_migrations(self): return self._call("migrations")
    def start_services(self): return self._call("start")
    def await_readiness(self): return self._call("readiness")
    def run_browser_journeys(self): return self._call("browser")
    def run_capability_journeys(self): return self._call("capabilities")
    def verify_persistence(self): return self._call("persistence")
    def verify_pwa(self): return self._call("pwa")
    def stop_services(self): self.calls.append("stop")


def test_runtime_orchestration_orders_actual_product_probes_and_stops_services():
    provider = RecordingProvider()
    RuntimeAcceptanceOrchestrator().execute(SHA, provider)
    assert provider.calls == [
        "commit", "migrations", "start", "readiness", "browser",
        "capabilities", "persistence", "pwa", "stop",
    ]


def test_runtime_orchestration_stops_services_after_probe_failure():
    provider = RecordingProvider("browser")
    with pytest.raises(RuntimeError, match="browser"):
        RuntimeAcceptanceOrchestrator().execute(SHA, provider)
    assert provider.calls[-1] == "stop"


def evidence_for(journey_value, index):
    return tuple(
        artifact(kind, journey_value.journey_id, journey_value.capability_id, index=index)
        for kind in journey_value.required_evidence
    )


def test_speakmate_authentication_cannot_pass_with_only_register_and_login(tmp_path):
    auth = speakmate_v1_contracts()[0]
    journeys = tuple(item for item in speakmate_v1_journeys() if item.capability_id == "AUTHENTICATION")
    service = RuntimeAcceptanceService(RuntimeAcceptanceStore(tmp_path))
    value = service.plan(run(capabilities=(auth,), journeys=journeys))
    value = service.mark_implemented(value.product_id, value.run_id, NOW)
    value = service.record_automated_verification(value.product_id, value.run_id, automated_evidence(), NOW)
    selected = journeys[:2]
    values = tuple(item for index, target in enumerate(selected) for item in evidence_for(target, index))
    results = tuple(
        JourneyResult(target.journey_id, EvidenceOutcome.PASS,
                      tuple(item.evidence_id for item in evidence_for(target, index)), NOW)
        for index, target in enumerate(selected)
    )
    with pytest.raises(RuntimeAcceptanceError, match="password_recovery"):
        service.record_runtime_verification(value.product_id, value.run_id, values, results, NOW)


def test_speakmate_partial_registration_failure_path_is_release_blocking(tmp_path):
    auth = speakmate_v1_contracts()[0]
    journeys = tuple(
        item for item in speakmate_v1_journeys() if item.capability_id == "AUTHENTICATION"
    )
    assert "authentication.security_error_paths" in auth.required_journey_ids
    error_path = next(
        item for item in journeys if item.journey_id == "authentication.security_error_paths"
    )
    assert "partial failure" in error_path.title
    selected = tuple(item for item in journeys if item != error_path)
    service = RuntimeAcceptanceService(RuntimeAcceptanceStore(tmp_path))
    value = service.plan(run(capabilities=(auth,), journeys=journeys))
    value = service.mark_implemented(value.product_id, value.run_id, NOW)
    value = service.record_automated_verification(
        value.product_id, value.run_id, automated_evidence(), NOW
    )
    values = tuple(
        item
        for index, target in enumerate(selected)
        for item in evidence_for(target, index)
    )
    results = tuple(
        JourneyResult(
            target.journey_id,
            EvidenceOutcome.PASS,
            tuple(item.evidence_id for item in evidence_for(target, index)),
            NOW,
        )
        for index, target in enumerate(selected)
    )
    with pytest.raises(RuntimeAcceptanceError, match="security_error_paths"):
        service.record_runtime_verification(
            value.product_id, value.run_id, values, results, NOW
        )


def test_speakmate_voice_requires_capture_to_repeat_turn_chain(tmp_path):
    voice = speakmate_v1_contracts()[1]
    journeys = tuple(item for item in speakmate_v1_journeys() if item.capability_id == "VOICE")
    service = RuntimeAcceptanceService(RuntimeAcceptanceStore(tmp_path))
    value = service.plan(run(capabilities=(voice,), journeys=journeys))
    value = service.mark_implemented(value.product_id, value.run_id, NOW)
    value = service.record_automated_verification(value.product_id, value.run_id, automated_evidence(), NOW)
    selected = journeys[:-1]
    values = tuple(item for index, target in enumerate(selected) for item in evidence_for(target, index))
    results = tuple(
        JourneyResult(target.journey_id, EvidenceOutcome.PASS,
                      tuple(item.evidence_id for item in evidence_for(target, index)), NOW)
        for index, target in enumerate(selected)
    )
    with pytest.raises(RuntimeAcceptanceError, match="voice.repeat_turn"):
        service.record_runtime_verification(value.product_id, value.run_id, values, results, NOW)


def test_deterministic_audio_fixture_requires_hashed_bounded_media():
    fixture = DeterministicAudioFixture(
        "english-turn-1",
        "artifact://fixtures/english-turn-1.wav",
        hashlib.sha256(b"deterministic-wav").hexdigest(),
        "audio/wav",
        16000,
        1,
        1500,
        "Hello, I would like to practice English.",
    )
    assert fixture.expected_transcript.startswith("Hello")
