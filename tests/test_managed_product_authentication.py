from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json

import pytest

from runtime.managed_product_authentication import (
    AuthenticationClaim,
    AuthenticationEvidenceBrowserProvider,
    AuthenticationJourneyVerification,
    AuthenticationPlanError,
    AuthenticationVerificationError,
    AuthenticationVerificationPlan,
    FileAuthenticationVerificationPlanStore,
    InMemoryAuthenticationVerificationPlanStore,
    LOCKED_AUTHENTICATION_CLAIMS,
)
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
from runtime.runtime_acceptance import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
    speakmate_v1_profile,
)
from runtime.runtime_acceptance.profiles import AUTHENTICATION_JOURNEYS


NOW = datetime(2026, 8, 17, 8, tzinfo=timezone.utc)
SHA = "a" * 40


def configuration() -> ManagedProductRuntimeConfiguration:
    profile = speakmate_v1_profile()
    return ManagedProductRuntimeConfiguration(
        "runtime",
        "speakmate",
        1,
        "https://github.com/example/speakmate.git",
        "main",
        SHA,
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


def browser_plan(config: ManagedProductRuntimeConfiguration | None = None) -> BrowserJourneyPlan:
    config = config or configuration()
    profile = speakmate_v1_profile()
    journeys = tuple(
        BrowserJourneySpecification(
            journey.journey_id,
            journey.capability_id,
            journey.title,
            "/auth",
            (
                BrowserStep(
                    f"{journey.journey_id}.verified",
                    BrowserActionKind.ASSERT_VISIBLE,
                    BrowserLocator(BrowserLocatorKind.TEXT, "Verified"),
                ),
            ),
        )
        for journey in profile.journeys
        if journey.capability_id == "AUTHENTICATION"
    )
    return BrowserJourneyPlan(
        "authentication-browser",
        "acceptance-run",
        config.project_id,
        config.configuration_id,
        config.revision,
        config.digest,
        config.commit_sha,
        profile.profile_id,
        profile.version,
        profile.digest,
        journeys,
        (),
        "test",
        NOW,
    )


def verification_plan(
    browser: BrowserJourneyPlan | None = None,
) -> AuthenticationVerificationPlan:
    browser = browser or browser_plan()
    profile = speakmate_v1_profile()
    evidence = {
        item.journey_id: tuple(
            kind
            for kind in item.required_evidence
            if kind in {EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY}
        )
        for item in profile.journeys
        if item.capability_id == "AUTHENTICATION"
    }
    journeys = tuple(
        AuthenticationJourneyVerification(
            journey_id,
            (f"{journey_id}.verified",),
            LOCKED_AUTHENTICATION_CLAIMS[journey_id],
            evidence[journey_id],
        )
        for journey_id in AUTHENTICATION_JOURNEYS
    )
    return AuthenticationVerificationPlan(
        "authentication-v1",
        browser.run_id,
        browser.product_id,
        browser.plan_id,
        browser.digest,
        browser.configuration_id,
        browser.configuration_revision,
        browser.configuration_digest,
        browser.commit_sha,
        browser.acceptance_profile_id,
        browser.acceptance_profile_version,
        browser.acceptance_profile_digest,
        "playwright-authentication-v1",
        journeys,
        "test",
        NOW,
    )


class PassingBrowserProvider:
    provider_id = "playwright-chromium"

    def __init__(self, *, omit_step: bool = False) -> None:
        self.omit_step = omit_step
        self.calls = 0

    def execute(self, plan, configuration, inputs, redactions, artifact_store):
        del configuration, inputs, redactions
        self.calls += 1
        evidence = []
        results = []
        for journey in plan.journeys:
            ids = []
            for kind in (
                EvidenceKind.BROWSER,
                EvidenceKind.BROWSER_CONSOLE,
                EvidenceKind.BROWSER_NETWORK,
                EvidenceKind.SCREENSHOT,
            ):
                if kind is EvidenceKind.SCREENSHOT:
                    uri, digest = artifact_store.write_bytes(
                        plan.product_id,
                        plan.run_id,
                        b"\x89PNG\r\n\x1a\nfake",
                        "png",
                    )
                else:
                    payload = {
                        "plan_digest": plan.digest,
                        "journey_id": journey.journey_id,
                        "outcome": "PASS",
                        "steps": []
                        if self.omit_step
                        else [
                            {
                                "step_id": step.step_id,
                                "outcome": "PASS",
                            }
                            for step in journey.steps
                        ],
                    }
                    uri, digest = artifact_store.write_json(
                        plan.product_id, plan.run_id, payload
                    )
                suffix = kind.value.casefold()
                item = EvidenceArtifact(
                    f"{plan.run_id}.{journey.journey_id}.{suffix}",
                    plan.run_id,
                    journey.capability_id,
                    journey.journey_id,
                    kind,
                    EvidenceOutcome.PASS,
                    plan.commit_sha,
                    uri,
                    digest,
                    NOW,
                    "Browser check passed",
                )
                evidence.append(item)
                ids.append(item.evidence_id)
            results.append(
                JourneyResult(journey.journey_id, EvidenceOutcome.PASS, tuple(ids), NOW)
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


def test_locked_authentication_plan_is_deeply_immutable_and_digest_sensitive():
    value = verification_plan()
    assert tuple(item.journey_id for item in value.journeys) == AUTHENTICATION_JOURNEYS
    assert value.digest != replace(value, created_by="other").digest
    with pytest.raises(ValueError, match="locked journey"):
        replace(
            value.journeys[0],
            claims=(AuthenticationClaim.LOGIN_SUCCEEDED,),
        )
    with pytest.raises(ValueError, match="every locked journey"):
        replace(value, journeys=value.journeys[:-1])
    with pytest.raises(ValueError, match="step IDs"):
        AuthenticationJourneyVerification(  # type: ignore[arg-type]
            "authentication.registration",
            ["step"],
            LOCKED_AUTHENTICATION_CLAIMS["authentication.registration"],
            (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
        )


def test_authentication_plan_store_is_write_once_restart_safe_and_tamper_evident(tmp_path):
    value = verification_plan()
    store = FileAuthenticationVerificationPlanStore(tmp_path / "plans")
    store.save(value)
    restored = FileAuthenticationVerificationPlanStore(tmp_path / "plans").load(
        value.product_id, value.run_id, value.verification_id
    )
    assert restored == value
    with pytest.raises(AuthenticationPlanError, match="immutable"):
        store.save(replace(value, created_by="different"))
    path = tmp_path / "plans" / value.product_id / value.run_id / f"{value.verification_id}.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["plan"]["created_by"] = "tampered"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(AuthenticationPlanError, match="corrupt"):
        store.load(value.product_id, value.run_id, value.verification_id)


def test_authentication_plan_store_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "plans"
    store = FileAuthenticationVerificationPlanStore(root)
    (root / "speakmate").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AuthenticationPlanError, match="symlink"):
        store.save(verification_plan())
    assert list(outside.iterdir()) == []


def test_authentication_evidence_wraps_exact_browser_claims(tmp_path):
    browser = browser_plan()
    verification = verification_plan(browser)
    plans = InMemoryAuthenticationVerificationPlanStore()
    plans.save(verification)
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    underlying = PassingBrowserProvider()
    provider = AuthenticationEvidenceBrowserProvider(
        verification.provider_id,
        verification.verification_id,
        plans,
        underlying,
    )
    result = provider.execute(browser, configuration(), {}, (), artifacts)
    assert result.stage is BrowserExecutionStage.COMPLETED
    assert underlying.calls == 1
    auth = [
        item
        for item in result.evidence
        if item.kind in {EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY}
    ]
    assert len(auth) == 10
    assert all(item.outcome is EvidenceOutcome.PASS for item in auth)
    for item in auth:
        payload = artifacts.read_json(item.artifact_uri, item.digest)
        assert payload["verification_digest"] == verification.digest
        assert payload["source_browser_digest"]
        assert "correct-horse-battery-staple" not in json.dumps(payload)
    assert all(item.outcome is EvidenceOutcome.PASS for item in result.journey_results)


def test_authentication_evidence_fails_closed_when_claim_step_did_not_pass(tmp_path):
    browser = browser_plan()
    verification = verification_plan(browser)
    plans = InMemoryAuthenticationVerificationPlanStore()
    plans.save(verification)
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "artifacts")
    provider = AuthenticationEvidenceBrowserProvider(
        verification.provider_id,
        verification.verification_id,
        plans,
        PassingBrowserProvider(omit_step=True),
    )
    result = provider.execute(browser, configuration(), {}, (), artifacts)
    assert result.stage is BrowserExecutionStage.FAILED
    assert result.failure_code == "AUTHENTICATION_EVIDENCE_FAILED"
    assert all(item.outcome is EvidenceOutcome.FAIL for item in result.journey_results)
    assert any(item.kind is EvidenceKind.SECURITY for item in result.evidence)


def test_authentication_authority_mismatch_blocks_before_browser_effect(tmp_path):
    browser = browser_plan()
    verification = replace(verification_plan(browser), commit_sha="b" * 40)
    plans = InMemoryAuthenticationVerificationPlanStore()
    plans.save(verification)
    underlying = PassingBrowserProvider()
    provider = AuthenticationEvidenceBrowserProvider(
        verification.provider_id,
        verification.verification_id,
        plans,
        underlying,
    )
    with pytest.raises(AuthenticationVerificationError, match="browser authority"):
        provider.execute(
            browser,
            configuration(),
            {},
            (),
            ContentAddressedBrowserArtifactStore(tmp_path / "artifacts"),
        )
    assert underlying.calls == 0
