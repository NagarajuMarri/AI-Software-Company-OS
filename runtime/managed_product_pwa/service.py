"""Exact-authority PWA execution and safe complete-capability submission."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from runtime.managed_product_browser.contracts import (
    BrowserArtifactStore,
    BrowserExecutionStore,
)
from runtime.managed_product_browser.models import (
    BrowserExecutionResult,
    BrowserExecutionStage,
)
from runtime.managed_product_environment.models import (
    EnvironmentExecutionRequest,
    EnvironmentObservationKind,
    EnvironmentObservationOutcome,
    EnvironmentStage,
)
from runtime.managed_product_environment.service import ManagedProductEnvironmentService
from runtime.managed_product_pwa.contracts import (
    AcceptanceSubmissionStore,
    PwaVerificationPlanStore,
)
from runtime.managed_product_pwa.errors import (
    AcceptanceSubmissionError,
    PwaVerificationError,
)
from runtime.managed_product_pwa.models import (
    AcceptanceSubmissionPlan,
    AcceptanceSubmissionReceipt,
    LOCKED_CAPABILITY_ORDER,
    PwaExecutionPolicy,
    PwaVerificationPlan,
)
from runtime.managed_product_pwa.provider import PlaywrightPwaProvider
from runtime.managed_product_runtime.models import endpoint_origin
from runtime.runtime_acceptance.models import (
    AcceptanceStage,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
    RuntimeAcceptanceRun,
)
from runtime.runtime_acceptance.service import RuntimeAcceptanceService


_ENVIRONMENT_EVIDENCE = {
    EnvironmentObservationKind.MIGRATION: EvidenceKind.MIGRATION,
    EnvironmentObservationKind.SERVICE_STARTUP: EvidenceKind.SERVICE_STARTUP,
    EnvironmentObservationKind.READINESS: EvidenceKind.READINESS,
}
_PWA_ALLOWED = {
    EvidenceKind.BROWSER,
    EvidenceKind.BROWSER_CONSOLE,
    EvidenceKind.BROWSER_NETWORK,
    EvidenceKind.SCREENSHOT,
    EvidenceKind.PWA,
}


class ManagedProductPwaService:
    """Run one immutable PWA plan while its exact managed environment is ready."""

    def __init__(
        self,
        acceptance_service: RuntimeAcceptanceService,
        plan_store: PwaVerificationPlanStore,
        execution_store: BrowserExecutionStore,
        environment_service: ManagedProductEnvironmentService,
        artifact_store: BrowserArtifactStore,
        policy: PwaExecutionPolicy,
        provider: PlaywrightPwaProvider,
    ) -> None:
        self.acceptance_service = acceptance_service
        self.plan_store = plan_store
        self.execution_store = execution_store
        self.environment_service = environment_service
        self.artifact_store = artifact_store
        self.policy = policy
        self.provider = provider

    def execute(
        self, product_id: str, run_id: str, plan_id: str, plan_digest: str
    ) -> BrowserExecutionResult:
        existing = self.execution_store.find(product_id, run_id, plan_id)
        if existing is not None:
            if existing.plan_digest != plan_digest:
                raise PwaVerificationError(
                    "Stored PWA execution does not match the requested plan"
                )
            self._verify_artifacts(existing)
            return existing
        plan = self.plan_store.load(product_id, run_id, plan_id)
        if plan.digest != plan_digest:
            raise PwaVerificationError("PWA execution request does not match authority")
        run = self.acceptance_service.store.load(product_id, run_id)
        if run is None or run.stage is not AcceptanceStage.AUTOMATED_VERIFIED:
            raise PwaVerificationError(
                "PWA verification requires exact automated verification first"
            )
        configuration = self.environment_service.configuration_store.get_revision(
            product_id, plan.configuration_id, plan.configuration_revision
        )
        self._authorize(run, plan, configuration)
        request = EnvironmentExecutionRequest(
            run_id,
            product_id,
            plan.configuration_id,
            plan.configuration_revision,
            plan.configuration_digest,
        )
        execution = self.environment_service.verify_with_ready_probe(
            request,
            lambda exact: self.provider.execute(plan, exact, self.artifact_store),
        )
        environment = execution.environment_result
        result = execution.probe_result
        if result is None:
            stage = (
                BrowserExecutionStage.RECONCILIATION_REQUIRED
                if environment.stage is EnvironmentStage.RECONCILIATION_REQUIRED
                else BrowserExecutionStage.FAILED
            )
            value = BrowserExecutionResult(
                plan.run_id,
                plan.product_id,
                plan.plan_id,
                plan.digest,
                plan.commit_sha,
                stage,
                (),
                (),
                environment.started_at,
                environment.completed_at,
                environment.failure_code or "ENVIRONMENT_NOT_READY",
            )
            return self.execution_store.save(value)
        if (
            result.run_id != plan.run_id
            or result.product_id != plan.product_id
            or result.plan_id != plan.plan_id
            or result.plan_digest != plan.digest
            or result.commit_sha != plan.commit_sha
        ):
            raise PwaVerificationError("PWA provider result escaped exact authority")
        if not (
            environment.started_at
            <= result.started_at
            <= result.completed_at
            <= environment.completed_at
        ):
            raise PwaVerificationError("PWA timestamps escaped the environment window")
        self._validate_provider_result(result)
        environment_evidence = self._environment_evidence(plan, environment.observations)
        journey_results = result.journey_results
        if journey_results:
            only = journey_results[0]
            journey_results = (
                replace(
                    only,
                    evidence_ids=only.evidence_ids
                    + tuple(item.evidence_id for item in environment_evidence),
                ),
            )
        stage = result.stage
        failure_code = result.failure_code
        if environment.stage is EnvironmentStage.RECONCILIATION_REQUIRED:
            stage = BrowserExecutionStage.RECONCILIATION_REQUIRED
            failure_code = environment.failure_code or failure_code
        elif environment.stage is not EnvironmentStage.STOPPED:
            stage = BrowserExecutionStage.FAILED
            failure_code = environment.failure_code or failure_code
        value = replace(
            result,
            stage=stage,
            evidence=result.evidence + environment_evidence,
            journey_results=journey_results,
            started_at=min(result.started_at, environment.started_at),
            completed_at=max(result.completed_at, environment.completed_at),
            failure_code=failure_code,
        )
        return self.execution_store.save(value)

    def _authorize(self, run, plan: PwaVerificationPlan, configuration) -> None:  # noqa: ANN001
        run_binding = (
            run.product_id,
            run.run_id,
            run.commit_sha,
            run.runtime_configuration_id,
            run.runtime_configuration_revision,
            run.runtime_configuration_digest,
            run.acceptance_profile_id,
            run.acceptance_profile_version,
            run.acceptance_profile_digest,
        )
        plan_binding = (
            plan.product_id,
            plan.run_id,
            plan.commit_sha,
            plan.configuration_id,
            plan.configuration_revision,
            plan.configuration_digest,
            plan.acceptance_profile_id,
            plan.acceptance_profile_version,
            plan.acceptance_profile_digest,
        )
        if run_binding != plan_binding:
            raise PwaVerificationError("PWA plan does not match runtime acceptance")
        configuration_binding = (
            configuration.project_id,
            configuration.commit_sha,
            configuration.configuration_id,
            configuration.revision,
            configuration.digest,
            configuration.acceptance_profile_id,
            configuration.acceptance_profile_version,
            configuration.acceptance_profile_digest,
        )
        expected_configuration = (
            plan.product_id,
            plan.commit_sha,
            plan.configuration_id,
            plan.configuration_revision,
            plan.configuration_digest,
            plan.acceptance_profile_id,
            plan.acceptance_profile_version,
            plan.acceptance_profile_digest,
        )
        if configuration_binding != expected_configuration:
            raise PwaVerificationError("PWA plan does not match runtime configuration")
        pwa_journeys = tuple(
            item.journey_id for item in run.journeys if item.capability_id == "PWA"
        )
        if pwa_journeys != ("pwa.install_launch",):
            raise PwaVerificationError("PWA plan does not match the locked journey")
        if self.provider.provider_id != plan.provider_id:
            raise PwaVerificationError("PWA provider does not match immutable authority")
        if self.provider.provider_id not in self.policy.allowed_provider_ids:
            raise PwaVerificationError("PWA provider is not currently approved")
        origins = {endpoint_origin(value) for value in configuration.allowed_origins}
        if not origins <= self.policy.allowed_origins:
            raise PwaVerificationError("PWA origin is not currently approved")

    def _validate_provider_result(self, result: BrowserExecutionResult) -> None:
        if len(result.journey_results) != 1 or result.journey_results[0].journey_id != (
            "pwa.install_launch"
        ):
            raise PwaVerificationError("PWA provider returned the wrong journey")
        if any(
            item.capability_id != "PWA"
            or item.journey_id != "pwa.install_launch"
            or item.kind not in _PWA_ALLOWED
            for item in result.evidence
        ):
            raise PwaVerificationError("PWA provider returned unauthorized evidence")
        self._verify_artifacts(result)
        if result.stage is BrowserExecutionStage.COMPLETED:
            kinds = {item.kind for item in result.evidence}
            if not _PWA_ALLOWED <= kinds:
                raise PwaVerificationError("Passing PWA result lacks complete evidence")

    def _verify_artifacts(self, result: BrowserExecutionResult) -> None:
        for item in result.evidence:
            self.artifact_store.verify(item.artifact_uri, item.digest)

    def _environment_evidence(
        self, plan: PwaVerificationPlan, observations: tuple
    ) -> tuple[EvidenceArtifact, ...]:
        values = []
        for index, observation in enumerate(observations):
            kind = _ENVIRONMENT_EVIDENCE.get(observation.kind)
            if kind is None:
                continue
            uri, digest = self.artifact_store.write_json(
                plan.product_id,
                plan.run_id,
                {
                    "kind": observation.kind.value,
                    "subject_id": observation.subject_id,
                    "outcome": observation.outcome.value,
                    "started_at": observation.started_at.isoformat(),
                    "completed_at": observation.completed_at.isoformat(),
                    "summary": observation.summary,
                    "output_digest": observation.output_digest,
                },
            )
            suffix = kind.value.removesuffix("_EVIDENCE").lower().replace("_", "-")
            values.append(
                EvidenceArtifact(
                    f"{plan.run_id}.pwa.install_launch.environment-{index}-{suffix}",
                    plan.run_id,
                    "PWA",
                    "pwa.install_launch",
                    kind,
                    EvidenceOutcome.PASS
                    if observation.outcome is EnvironmentObservationOutcome.PASS
                    else EvidenceOutcome.FAIL,
                    plan.commit_sha,
                    uri,
                    digest,
                    observation.completed_at,
                    observation.summary,
                )
            )
        return tuple(values)


class RuntimeAcceptanceAggregator:
    """Submit only complete, digest-verified capability slices to Milestone 15."""

    def __init__(
        self,
        acceptance_service: RuntimeAcceptanceService,
        submission_store: AcceptanceSubmissionStore,
        artifact_store: BrowserArtifactStore,
    ) -> None:
        self.acceptance_service = acceptance_service
        self.submission_store = submission_store
        self.artifact_store = artifact_store

    def register(self, plan: AcceptanceSubmissionPlan) -> AcceptanceSubmissionPlan:
        run = self.acceptance_service.store.load(plan.product_id, plan.run_id)
        if run is None:
            raise AcceptanceSubmissionError("Unknown runtime acceptance run")
        self._authorize_plan(run, plan)
        return self.submission_store.save_plan(plan)

    def submit(
        self,
        product_id: str,
        run_id: str,
        submission_id: str,
        results: tuple[BrowserExecutionResult, ...],
        now: datetime,
    ) -> RuntimeAcceptanceRun:
        plan = self.submission_store.load_plan(product_id, run_id, submission_id)
        receipt = self.submission_store.find_receipt(product_id, run_id, submission_id)
        run = self.acceptance_service.store.load(product_id, run_id)
        if run is None:
            raise AcceptanceSubmissionError("Unknown runtime acceptance run")
        self._authorize_plan(run, plan)
        if receipt is not None:
            if (
                receipt.submission_digest != plan.digest
                or receipt.runtime_evidence_digest != run.evidence_digest
                or receipt.source_result_digests
                != tuple(item.result_digest for item in plan.sources)
                or run.stage is not AcceptanceStage.RUNTIME_VERIFIED
            ):
                raise AcceptanceSubmissionError("Stored submission receipt is stale")
            return run
        evidence, journeys = self._validate_sources(run, plan, results)
        if run.stage is AcceptanceStage.AUTOMATED_VERIFIED:
            run = self.acceptance_service.record_runtime_verification(
                product_id, run_id, evidence, journeys, now
            )
        elif run.stage is AcceptanceStage.RUNTIME_VERIFIED:
            runtime_evidence = tuple(
                item
                for item in run.evidence
                if item.kind not in {EvidenceKind.CODE, EvidenceKind.AUTOMATED_TEST}
            )
            if runtime_evidence != evidence or run.journey_results != journeys:
                raise AcceptanceSubmissionError(
                    "Existing runtime verification cannot be reconciled to submission"
                )
        else:
            raise AcceptanceSubmissionError(
                "Submission requires automated or matching runtime verification"
            )
        receipt = AcceptanceSubmissionReceipt(
            plan.submission_id,
            plan.digest,
            run.run_id,
            run.product_id,
            run.evidence_digest,
            tuple(item.result_digest for item in plan.sources),
            now,
        )
        self.submission_store.save_receipt(receipt)
        return run

    @staticmethod
    def _authorize_plan(run: RuntimeAcceptanceRun, plan: AcceptanceSubmissionPlan) -> None:
        binding = (
            run.run_id,
            run.product_id,
            run.commit_sha,
            run.runtime_configuration_id,
            run.runtime_configuration_revision,
            run.runtime_configuration_digest,
            run.acceptance_profile_id,
            run.acceptance_profile_version,
            run.acceptance_profile_digest,
        )
        expected = (
            plan.run_id,
            plan.product_id,
            plan.commit_sha,
            plan.configuration_id,
            plan.configuration_revision,
            plan.configuration_digest,
            plan.acceptance_profile_id,
            plan.acceptance_profile_version,
            plan.acceptance_profile_digest,
        )
        if binding != expected:
            raise AcceptanceSubmissionError(
                "Submission plan does not match exact runtime authority"
            )
        capabilities = tuple(item.capability_id for item in run.capabilities if item.locked)
        if capabilities != LOCKED_CAPABILITY_ORDER:
            raise AcceptanceSubmissionError("Submission capabilities are incomplete")
        expected_journeys = {
            item.capability_id: tuple(
                journey.journey_id
                for journey in run.journeys
                if journey.capability_id == item.capability_id
            )
            for item in run.capabilities
            if item.locked
        }
        for source in plan.sources:
            if expected_journeys.get(source.capability_id) != source.journey_ids:
                raise AcceptanceSubmissionError(
                    "Submission source does not cover its locked capability"
                )

    def _validate_sources(
        self,
        run: RuntimeAcceptanceRun,
        plan: AcceptanceSubmissionPlan,
        results: tuple[BrowserExecutionResult, ...],
    ) -> tuple[tuple[EvidenceArtifact, ...], tuple[JourneyResult, ...]]:
        if not isinstance(results, tuple) or len(results) != len(plan.sources):
            raise AcceptanceSubmissionError("Submission requires exactly three results")
        evidence: list[EvidenceArtifact] = []
        journeys: list[JourneyResult] = []
        for source, result in zip(plan.sources, results, strict=True):
            result_journeys = tuple(item.journey_id for item in result.journey_results)
            result_capabilities = {
                item.capability_id for item in result.evidence if item.journey_id in result_journeys
            }
            if (
                result.stage is not BrowserExecutionStage.COMPLETED
                or result.run_id != plan.run_id
                or result.product_id != plan.product_id
                or result.commit_sha != plan.commit_sha
                or result.plan_id != source.plan_id
                or result.plan_digest != source.plan_digest
                or result.digest != source.result_digest
                or result_journeys != source.journey_ids
                or result_capabilities != {source.capability_id}
            ):
                raise AcceptanceSubmissionError(
                    "Capability result does not match immutable submission authority"
                )
            available = {item.evidence_id for item in result.evidence}
            if any(not set(item.evidence_ids) <= available for item in result.journey_results):
                raise AcceptanceSubmissionError("Capability result has broken evidence links")
            for item in result.evidence:
                self.artifact_store.verify(item.artifact_uri, item.digest)
            evidence.extend(result.evidence)
            journeys.extend(result.journey_results)
        evidence_ids = tuple(item.evidence_id for item in evidence)
        journey_ids = tuple(item.journey_id for item in journeys)
        if (
            len(evidence_ids) != len(set(evidence_ids))
            or len(journey_ids) != len(set(journey_ids))
            or set(journey_ids) != {item.journey_id for item in run.journeys}
        ):
            raise AcceptanceSubmissionError(
                "Aggregated capability evidence is duplicate or incomplete"
            )
        return tuple(evidence), tuple(journeys)


def _now() -> datetime:
    return datetime.now(timezone.utc)
