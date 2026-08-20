from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json

import pytest

from runtime.managed_product_browser import (
    BrowserExecutionResult,
    BrowserExecutionStage,
    ContentAddressedBrowserArtifactStore,
)
from runtime.managed_product_pwa import (
    AcceptanceSubmissionError,
    AcceptanceSubmissionPlan,
    CapabilityExecutionReference,
    FileAcceptanceSubmissionStore,
    FilePwaVerificationPlanStore,
    LOCKED_CAPABILITY_ORDER,
    LOCKED_PWA_CLAIMS,
    PwaExecutionPolicy,
    PwaPlanError,
    PwaVerificationPlan,
    RuntimeAcceptanceAggregator,
)
from runtime.managed_product_pwa.provider import _safe_url, _validate_manifest
from runtime.runtime_acceptance import (
    AcceptanceStage,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
    RuntimeAcceptanceRun,
    RuntimeAcceptanceService,
    RuntimeAcceptanceStore,
    speakmate_v1_profile,
)


NOW = datetime(2026, 8, 18, 8, tzinfo=timezone.utc)
SHA = "a" * 40
CONFIG_DIGEST = "b" * 64


def _pwa_plan() -> PwaVerificationPlan:
    profile = speakmate_v1_profile()
    return PwaVerificationPlan(
        "pwa-plan-v1",
        "runtime-run",
        "spoken-english-ai",
        "runtime-v1",
        1,
        CONFIG_DIGEST,
        SHA,
        profile.profile_id,
        profile.version,
        profile.digest,
        "playwright-pwa-v1",
        "/",
        "/manifest.webmanifest",
        "/service-worker.js",
        "app-shell",
        "SpeakMate ready",
        LOCKED_PWA_CLAIMS,
        "ascos",
        NOW,
    )


def _staged_acceptance(tmp_path):
    profile = speakmate_v1_profile()
    store = RuntimeAcceptanceStore(tmp_path / "acceptance")
    service = RuntimeAcceptanceService(store)
    run = RuntimeAcceptanceRun(
        "runtime-run",
        "spoken-english-ai",
        "1.0",
        SHA,
        AcceptanceStage.PLANNED,
        profile.capabilities,
        profile.journeys,
        NOW,
        NOW,
        runtime_configuration_id="runtime-v1",
        runtime_configuration_revision=1,
        runtime_configuration_digest=CONFIG_DIGEST,
        acceptance_profile_id=profile.profile_id,
        acceptance_profile_version=profile.version,
        acceptance_profile_digest=profile.digest,
    )
    service.plan(run)
    service.mark_implemented(run.product_id, run.run_id, NOW)
    automated = tuple(
        EvidenceArtifact(
            f"runtime-run.automated.{kind.value}",
            run.run_id,
            "AUTHENTICATION",
            "authentication.registration",
            kind,
            EvidenceOutcome.PASS,
            SHA,
            f"artifact://automated/{kind.value}",
            hashlib.sha256(kind.value.encode()).hexdigest(),
            NOW,
            f"Verified {kind.value}",
        )
        for kind in (EvidenceKind.CODE, EvidenceKind.AUTOMATED_TEST)
    )
    service.record_automated_verification(run.product_id, run.run_id, automated, NOW)
    return service


def _capability_result(profile, capability_id, artifacts):
    journeys = tuple(
        item for item in profile.journeys if item.capability_id == capability_id
    )
    evidence = []
    results = []
    for journey_index, journey in enumerate(journeys):
        journey_evidence = []
        required = journey.required_evidence
        if capability_id == "AUTHENTICATION" and journey_index == 0:
            required += (EvidenceKind.MIGRATION, EvidenceKind.SERVICE_STARTUP)
        for kind in required:
            uri, digest = artifacts.write_json(
                "spoken-english-ai",
                "runtime-run",
                {
                    "capability_id": capability_id,
                    "journey_id": journey.journey_id,
                    "kind": kind.value,
                    "outcome": "PASS",
                },
            )
            item = EvidenceArtifact(
                f"runtime-run.{journey.journey_id}.{kind.value}",
                "runtime-run",
                capability_id,
                journey.journey_id,
                kind,
                EvidenceOutcome.PASS,
                SHA,
                uri,
                digest,
                NOW,
                f"Verified {kind.value}",
            )
            evidence.append(item)
            journey_evidence.append(item.evidence_id)
        results.append(
            JourneyResult(journey.journey_id, EvidenceOutcome.PASS, tuple(journey_evidence), NOW)
        )
    plan_id = f"{capability_id.casefold()}-plan-v1"
    plan_digest = hashlib.sha256(plan_id.encode()).hexdigest()
    return BrowserExecutionResult(
        "runtime-run",
        "spoken-english-ai",
        plan_id,
        plan_digest,
        SHA,
        BrowserExecutionStage.COMPLETED,
        tuple(evidence),
        tuple(results),
        NOW,
        NOW,
    )


def _submission(results) -> AcceptanceSubmissionPlan:
    profile = speakmate_v1_profile()
    sources = tuple(
        CapabilityExecutionReference(
            capability_id,
            result.plan_id,
            result.plan_digest,
            result.digest,
            tuple(item.journey_id for item in result.journey_results),
        )
        for capability_id, result in zip(LOCKED_CAPABILITY_ORDER, results, strict=True)
    )
    return AcceptanceSubmissionPlan(
        "submission-v1",
        "runtime-run",
        "spoken-english-ai",
        "runtime-v1",
        1,
        CONFIG_DIGEST,
        SHA,
        profile.profile_id,
        profile.version,
        profile.digest,
        sources,
        "ascos",
        NOW,
    )


def test_pwa_plan_digest_binds_every_authority_field():
    plan = _pwa_plan()
    assert len(plan.digest) == 64
    assert replace(plan, shell_expected_text="Different shell").digest != plan.digest
    assert replace(plan, manifest_path="/app.webmanifest").digest != plan.digest
    assert replace(plan, commit_sha="c" * 40).digest != plan.digest


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("start_path", "relative"),
        ("start_path", "/a/../admin"),
        ("manifest_path", "/manifest.webmanifest?token=secret"),
        ("service_worker_path", "/%2e%2e/worker.js"),
        ("shell_test_id", "bad/id"),
        ("commit_sha", "A" * 40),
    ),
)
def test_pwa_plan_rejects_unsafe_or_ambiguous_authority(field, value):
    with pytest.raises(ValueError):
        replace(_pwa_plan(), **{field: value})


def test_pwa_plan_requires_every_locked_claim_in_order():
    with pytest.raises(ValueError, match="every locked claim"):
        replace(_pwa_plan(), claims=LOCKED_PWA_CLAIMS[:-1])
    with pytest.raises(ValueError, match="every locked claim"):
        replace(_pwa_plan(), claims=tuple(reversed(LOCKED_PWA_CLAIMS)))


def test_pwa_policy_rejects_credentialed_or_path_origins():
    with pytest.raises(ValueError, match="origin"):
        PwaExecutionPolicy(frozenset({"provider"}), frozenset({"https://u:p@example.com"}))
    with pytest.raises(ValueError, match="origin"):
        PwaExecutionPolicy(frozenset({"provider"}), frozenset({"https://example.com/app"}))
    with pytest.raises(ValueError, match="origin"):
        PwaExecutionPolicy(frozenset({"provider"}), frozenset({" https://example.com"}))
    assert PwaExecutionPolicy(
        frozenset({"provider"}), frozenset({"http://127.0.0.1:8123"})
    ).allowed_provider_ids == frozenset({"provider"})


def test_network_evidence_url_removes_credentials_query_and_fragment():
    safe = _safe_url("https://user:secret@example.com:8443/app?token=secret#value")
    assert safe == "https://example.com:8443/app"
    assert "user" not in safe and "secret" not in safe and "token" not in safe


def test_manifest_requires_exact_scope_paths_display_and_png_icons():
    plan = _pwa_plan()
    manifest = {
        "name": "SpeakMate",
        "short_name": "SpeakMate",
        "id": "/",
        "display": "standalone",
        "start_url": "/",
        "scope": "/",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    assert _validate_manifest(manifest, plan) == ("/icon-192.png", "/icon-512.png")
    with pytest.raises(ValueError, match="incomplete or mismatched"):
        _validate_manifest({**manifest, "start_url": "/other"}, plan)
    with pytest.raises(ValueError, match="required PNG"):
        _validate_manifest({**manifest, "icons": manifest["icons"][:1]}, plan)


def test_file_pwa_plan_is_write_once_restart_safe_and_tamper_evident(tmp_path):
    root = tmp_path / "plans"
    plan = _pwa_plan()
    store = FilePwaVerificationPlanStore(root)
    assert store.save(plan) == plan
    assert store.save(plan) == plan
    assert FilePwaVerificationPlanStore(root).load(
        plan.product_id, plan.run_id, plan.plan_id
    ) == plan
    with pytest.raises(PwaPlanError, match="immutable"):
        store.save(replace(plan, shell_expected_text="Changed"))
    path = root / plan.product_id / plan.run_id / f"{plan.plan_id}.pwa.json"
    envelope = json.loads(path.read_text())
    envelope["plan"]["shell_expected_text"] = "tampered"
    path.write_text(json.dumps(envelope))
    with pytest.raises(PwaPlanError, match="corrupt"):
        FilePwaVerificationPlanStore(root).load(plan.product_id, plan.run_id, plan.plan_id)


def test_file_pwa_plan_rejects_traversal_and_symlink(tmp_path):
    store = FilePwaVerificationPlanStore(tmp_path / "plans")
    with pytest.raises(PwaPlanError, match="unsafe"):
        store.load("../product", "runtime-run", "pwa-plan-v1")
    product = store.root / "spoken-english-ai"
    product.symlink_to(tmp_path)
    with pytest.raises(PwaPlanError, match="symlink"):
        store.load("spoken-english-ai", "runtime-run", "pwa-plan-v1")


def test_submission_requires_three_ordered_complete_capability_slices(tmp_path):
    profile = speakmate_v1_profile()
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    results = tuple(_capability_result(profile, item, artifacts) for item in LOCKED_CAPABILITY_ORDER)
    plan = _submission(results)
    assert tuple(item.capability_id for item in plan.sources) == LOCKED_CAPABILITY_ORDER
    with pytest.raises(ValueError, match="Authentication, Voice, and PWA"):
        replace(plan, sources=tuple(reversed(plan.sources)))
    with pytest.raises(ValueError, match="unique across"):
        replace(
            plan,
            sources=(plan.sources[0], replace(plan.sources[1], journey_ids=plan.sources[0].journey_ids), plan.sources[2]),
        )


def test_submission_plan_and_receipt_are_write_once_and_restart_safe(tmp_path):
    profile = speakmate_v1_profile()
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    results = tuple(_capability_result(profile, item, artifacts) for item in LOCKED_CAPABILITY_ORDER)
    plan = _submission(results)
    root = tmp_path / "submissions"
    store = FileAcceptanceSubmissionStore(root)
    assert store.save_plan(plan) == plan
    assert FileAcceptanceSubmissionStore(root).load_plan(
        plan.product_id, plan.run_id, plan.submission_id
    ) == plan
    with pytest.raises(AcceptanceSubmissionError, match="immutable"):
        store.save_plan(replace(plan, created_by="other"))


def test_aggregate_submission_advances_only_to_runtime_verified_and_is_idempotent(tmp_path):
    service = _staged_acceptance(tmp_path)
    profile = speakmate_v1_profile()
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    results = tuple(_capability_result(profile, item, artifacts) for item in LOCKED_CAPABILITY_ORDER)
    plan = _submission(results)
    root = tmp_path / "submissions"
    aggregator = RuntimeAcceptanceAggregator(
        service, FileAcceptanceSubmissionStore(root), artifacts
    )
    assert aggregator.register(plan) == plan
    verified = aggregator.submit(plan.product_id, plan.run_id, plan.submission_id, results, NOW)
    assert verified.stage is AcceptanceStage.RUNTIME_VERIFIED
    assert verified.evidence_digest
    assert tuple(item.journey_id for item in verified.journey_results) == tuple(
        item.journey_id for item in profile.journeys
    )
    restarted = RuntimeAcceptanceAggregator(
        RuntimeAcceptanceService(service.store), FileAcceptanceSubmissionStore(root), artifacts
    )
    assert restarted.submit(plan.product_id, plan.run_id, plan.submission_id, results, NOW) == verified
    assert service.store.load(plan.product_id, plan.run_id).stage is AcceptanceStage.RUNTIME_VERIFIED


def test_aggregate_submission_rejects_stale_incomplete_or_tampered_sources(tmp_path):
    service = _staged_acceptance(tmp_path)
    profile = speakmate_v1_profile()
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    results = tuple(_capability_result(profile, item, artifacts) for item in LOCKED_CAPABILITY_ORDER)
    plan = _submission(results)
    aggregator = RuntimeAcceptanceAggregator(
        service, FileAcceptanceSubmissionStore(tmp_path / "submissions"), artifacts
    )
    aggregator.register(plan)
    stale = replace(results[2], plan_digest="f" * 64)
    with pytest.raises(AcceptanceSubmissionError, match="immutable submission"):
        aggregator.submit(plan.product_id, plan.run_id, plan.submission_id, results[:2] + (stale,), NOW)
    first = results[0].evidence[0]
    artifacts.resolve(first.artifact_uri).write_bytes(b"tampered")
    with pytest.raises(Exception, match="integrity|digest|corrupt|match"):
        aggregator.submit(plan.product_id, plan.run_id, plan.submission_id, results, NOW)


def test_submission_plan_rejects_runtime_binding_mismatch(tmp_path):
    service = _staged_acceptance(tmp_path)
    profile = speakmate_v1_profile()
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    results = tuple(_capability_result(profile, item, artifacts) for item in LOCKED_CAPABILITY_ORDER)
    aggregator = RuntimeAcceptanceAggregator(
        service, FileAcceptanceSubmissionStore(tmp_path / "submissions"), artifacts
    )
    with pytest.raises(AcceptanceSubmissionError, match="exact runtime authority"):
        aggregator.register(replace(_submission(results), configuration_digest="c" * 64))
