"""Browser-provider wrapper that derives locked authentication evidence safely."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from runtime.managed_product_authentication.contracts import (
    AuthenticationVerificationPlanStore,
)
from runtime.managed_product_authentication.errors import AuthenticationVerificationError
from runtime.managed_product_authentication.models import AuthenticationVerificationPlan
from runtime.managed_product_browser.contracts import (
    BrowserArtifactStore,
    ManagedProductBrowserProvider,
)
from runtime.managed_product_browser.errors import BrowserArtifactError
from runtime.managed_product_browser.models import (
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserJourneyPlan,
)
from runtime.managed_product_runtime.models import ManagedProductRuntimeConfiguration
from runtime.runtime_acceptance.models import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
)


class AuthenticationEvidenceBrowserProvider:
    """Add persistence/security evidence only from passed locked browser assertions."""

    def __init__(
        self,
        provider_id: str,
        verification_id: str,
        plan_store: AuthenticationVerificationPlanStore,
        browser_provider: ManagedProductBrowserProvider,
    ) -> None:
        self.provider_id = provider_id
        self.verification_id = verification_id
        self.plan_store = plan_store
        self.browser_provider = browser_provider

    def execute(
        self,
        plan: BrowserJourneyPlan,
        configuration: ManagedProductRuntimeConfiguration,
        inputs: dict[str, str],
        redactions: tuple[str, ...],
        artifact_store: BrowserArtifactStore,
    ) -> BrowserExecutionResult:
        verification = self.plan_store.load(
            plan.product_id, plan.run_id, self.verification_id
        )
        self._authorize(verification, plan, configuration)
        browser = self.browser_provider.execute(
            plan, configuration, inputs, redactions, artifact_store
        )
        if browser.stage is not BrowserExecutionStage.COMPLETED:
            return browser
        try:
            evidence, results = self._verify(
                verification, browser, artifact_store
            )
        except (AuthenticationVerificationError, BrowserArtifactError):
            evidence, results = self._failure_evidence(
                verification, browser, artifact_store
            )
            return replace(
                browser,
                stage=BrowserExecutionStage.FAILED,
                evidence=browser.evidence + evidence,
                journey_results=results,
                completed_at=_now(),
                failure_code="AUTHENTICATION_EVIDENCE_FAILED",
            )
        return replace(
            browser,
            evidence=browser.evidence + evidence,
            journey_results=results,
            completed_at=_now(),
        )

    def _authorize(
        self,
        verification: AuthenticationVerificationPlan,
        browser: BrowserJourneyPlan,
        configuration: ManagedProductRuntimeConfiguration,
    ) -> None:
        if verification.provider_id != self.provider_id:
            raise AuthenticationVerificationError(
                "Authentication provider does not match persisted authority"
            )
        verification_binding = (
            verification.run_id,
            verification.product_id,
            verification.browser_plan_id,
            verification.browser_plan_digest,
            verification.configuration_id,
            verification.configuration_revision,
            verification.configuration_digest,
            verification.commit_sha,
            verification.acceptance_profile_id,
            verification.acceptance_profile_version,
            verification.acceptance_profile_digest,
        )
        browser_binding = (
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
        )
        if verification_binding != browser_binding:
            raise AuthenticationVerificationError(
                "Authentication plan does not match browser authority"
            )
        configuration_binding = (
            configuration.project_id,
            configuration.configuration_id,
            configuration.revision,
            configuration.digest,
            configuration.commit_sha,
            configuration.acceptance_profile_id,
            configuration.acceptance_profile_version,
            configuration.acceptance_profile_digest,
        )
        expected_configuration = (
            verification.product_id,
            verification.configuration_id,
            verification.configuration_revision,
            verification.configuration_digest,
            verification.commit_sha,
            verification.acceptance_profile_id,
            verification.acceptance_profile_version,
            verification.acceptance_profile_digest,
        )
        if configuration_binding != expected_configuration:
            raise AuthenticationVerificationError(
                "Authentication plan does not match runtime configuration"
            )
        browser_journeys = tuple(item.journey_id for item in browser.journeys)
        verification_journeys = tuple(item.journey_id for item in verification.journeys)
        if browser_journeys != verification_journeys or any(
            item.capability_id != "AUTHENTICATION" for item in browser.journeys
        ):
            raise AuthenticationVerificationError(
                "Authentication browser plan does not cover the locked journeys"
            )
        steps = {
            item.journey_id: {step.step_id for step in item.steps}
            for item in browser.journeys
        }
        if any(
            not set(item.required_step_ids) <= steps[item.journey_id]
            for item in verification.journeys
        ):
            raise AuthenticationVerificationError(
                "Authentication verification references an undeclared browser step"
            )

    def _verify(
        self,
        verification: AuthenticationVerificationPlan,
        browser: BrowserExecutionResult,
        artifact_store: BrowserArtifactStore,
    ) -> tuple[tuple[EvidenceArtifact, ...], tuple[JourneyResult, ...]]:
        by_journey: dict[str, list[EvidenceArtifact]] = {}
        for item in browser.evidence:
            by_journey.setdefault(item.journey_id, []).append(item)
        prior_results = {item.journey_id: item for item in browser.journey_results}
        generated: list[EvidenceArtifact] = []
        results: list[JourneyResult] = []
        for contract in verification.journeys:
            prior = prior_results.get(contract.journey_id)
            if prior is None or prior.outcome is not EvidenceOutcome.PASS:
                raise AuthenticationVerificationError(
                    "Authentication journey lacks passing browser evidence"
                )
            summaries = [
                item
                for item in by_journey.get(contract.journey_id, ())
                if item.kind is EvidenceKind.BROWSER
            ]
            if len(summaries) != 1:
                raise AuthenticationVerificationError(
                    "Authentication journey requires one browser summary"
                )
            summary = summaries[0]
            payload = artifact_store.read_json(summary.artifact_uri, summary.digest)
            if not isinstance(payload, dict):
                raise AuthenticationVerificationError(
                    "Authentication browser summary is malformed"
                )
            steps = payload.get("steps")
            if (
                payload.get("plan_digest") != verification.browser_plan_digest
                or payload.get("journey_id") != contract.journey_id
                or payload.get("outcome") != EvidenceOutcome.PASS.value
                or not isinstance(steps, list)
            ):
                raise AuthenticationVerificationError(
                    "Authentication browser summary does not match authority"
                )
            passed = {
                value.get("step_id")
                for value in steps
                if isinstance(value, dict) and value.get("outcome") == "PASS"
            }
            if not set(contract.required_step_ids) <= passed:
                raise AuthenticationVerificationError(
                    "Authentication claim lacks a passed browser assertion"
                )
            created = self._evidence_for_contract(
                verification, contract, summary, artifact_store, EvidenceOutcome.PASS
            )
            generated.extend(created)
            results.append(
                JourneyResult(
                    contract.journey_id,
                    EvidenceOutcome.PASS,
                    prior.evidence_ids + tuple(item.evidence_id for item in created),
                    _now(),
                )
            )
        return tuple(generated), tuple(results)

    def _failure_evidence(
        self,
        verification: AuthenticationVerificationPlan,
        browser: BrowserExecutionResult,
        artifact_store: BrowserArtifactStore,
    ) -> tuple[tuple[EvidenceArtifact, ...], tuple[JourneyResult, ...]]:
        prior_results = {item.journey_id: item for item in browser.journey_results}
        generated: list[EvidenceArtifact] = []
        results: list[JourneyResult] = []
        for contract in verification.journeys:
            created = self._evidence_for_contract(
                verification, contract, None, artifact_store, EvidenceOutcome.FAIL
            )
            generated.extend(created)
            prior_ids = prior_results[contract.journey_id].evidence_ids
            results.append(
                JourneyResult(
                    contract.journey_id,
                    EvidenceOutcome.FAIL,
                    prior_ids + tuple(item.evidence_id for item in created),
                    _now(),
                )
            )
        return tuple(generated), tuple(results)

    def _evidence_for_contract(
        self,
        verification: AuthenticationVerificationPlan,
        contract,
        source: EvidenceArtifact | None,
        artifact_store: BrowserArtifactStore,
        outcome: EvidenceOutcome,
    ) -> tuple[EvidenceArtifact, ...]:
        values: list[EvidenceArtifact] = []
        observed = _now()
        for kind in contract.evidence_kinds:
            payload = {
                "schema_version": 1,
                "verification_id": verification.verification_id,
                "verification_digest": verification.digest,
                "browser_plan_digest": verification.browser_plan_digest,
                "journey_id": contract.journey_id,
                "evidence_kind": kind.value,
                "outcome": outcome.value,
                "claims": [value.value for value in contract.claims],
                "required_step_ids": list(contract.required_step_ids),
                "source_browser_evidence_id": None if source is None else source.evidence_id,
                "source_browser_digest": None if source is None else source.digest,
            }
            uri, digest = artifact_store.write_json(
                verification.product_id, verification.run_id, payload
            )
            suffix = "persistence" if kind is EvidenceKind.PERSISTENCE else "security"
            values.append(
                EvidenceArtifact(
                    f"{verification.run_id}.{contract.journey_id}.authentication-{suffix}",
                    verification.run_id,
                    "AUTHENTICATION",
                    contract.journey_id,
                    kind,
                    outcome,
                    verification.commit_sha,
                    uri,
                    digest,
                    observed,
                    "Locked authentication claims verified from exact browser assertions"
                    if outcome is EvidenceOutcome.PASS
                    else "Authentication claim verification failed closed",
                    (
                        ("verification_digest", verification.digest),
                        ("provider_id", verification.provider_id),
                    ),
                )
            )
        return tuple(values)


def _now() -> datetime:
    return datetime.now(timezone.utc)
