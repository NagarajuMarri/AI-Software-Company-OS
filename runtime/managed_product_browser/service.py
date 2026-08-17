"""Exact-authority orchestration across environment, browser, and evidence stores."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from runtime.managed_product_browser.contracts import (
    BrowserArtifactStore,
    BrowserExecutionStore,
    BrowserInputResolver,
    BrowserJourneyPlanStore,
    ManagedProductBrowserProvider,
)
from runtime.managed_product_browser.errors import (
    BrowserAuthorityError,
    BrowserProviderUnavailable,
)
from runtime.managed_product_browser.models import (
    BrowserExecutionPolicy,
    BrowserExecutionRequest,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserJourneyPlan,
)
from runtime.managed_product_environment.models import (
    EnvironmentExecutionRequest,
    EnvironmentObservationKind,
    EnvironmentObservationOutcome,
    EnvironmentStage,
)
from runtime.managed_product_environment.service import ManagedProductEnvironmentService
from runtime.managed_product_runtime.models import (
    ManagedProductRuntimeConfiguration,
    endpoint_origin,
)
from runtime.runtime_acceptance.models import (
    AcceptanceStage,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
)
from runtime.runtime_acceptance.persistence import RuntimeAcceptanceStore


_ENVIRONMENT_EVIDENCE = {
    EnvironmentObservationKind.MIGRATION: EvidenceKind.MIGRATION,
    EnvironmentObservationKind.SERVICE_STARTUP: EvidenceKind.SERVICE_STARTUP,
    EnvironmentObservationKind.READINESS: EvidenceKind.READINESS,
}
_BROWSER_EVIDENCE = {
    EvidenceKind.BROWSER,
    EvidenceKind.BROWSER_CONSOLE,
    EvidenceKind.BROWSER_NETWORK,
    EvidenceKind.SCREENSHOT,
}


class ManagedProductBrowserService:
    """Run one immutable browser plan while its exact managed environment is ready."""

    def __init__(
        self,
        acceptance_store: RuntimeAcceptanceStore,
        plan_store: BrowserJourneyPlanStore,
        execution_store: BrowserExecutionStore,
        environment_service: ManagedProductEnvironmentService,
        input_resolver: BrowserInputResolver,
        policy: BrowserExecutionPolicy,
        provider: ManagedProductBrowserProvider,
        artifact_store: BrowserArtifactStore,
    ) -> None:
        self.acceptance_store = acceptance_store
        self.plan_store = plan_store
        self.execution_store = execution_store
        self.environment_service = environment_service
        self.input_resolver = input_resolver
        self.policy = policy
        self.provider = provider
        self.artifact_store = artifact_store

    def execute(self, request: BrowserExecutionRequest) -> BrowserExecutionResult:
        existing = self.execution_store.find(
            request.product_id, request.run_id, request.plan_id
        )
        if existing is not None:
            if existing.plan_digest != request.plan_digest:
                raise BrowserAuthorityError(
                    "Stored browser execution does not match the requested plan"
                )
            for artifact in existing.evidence:
                self.artifact_store.verify(artifact.artifact_uri, artifact.digest)
            return existing

        run = self.acceptance_store.load(request.product_id, request.run_id)
        if run is None:
            raise BrowserAuthorityError("Unknown runtime acceptance run")
        if run.stage is not AcceptanceStage.AUTOMATED_VERIFIED:
            raise BrowserAuthorityError(
                "Browser execution requires exact automated verification first"
            )
        plan = self.plan_store.load(
            request.product_id, request.run_id, request.plan_id
        )
        if plan.digest != request.plan_digest:
            raise BrowserAuthorityError(
                "Browser execution request does not match the immutable plan"
            )
        configuration = self.environment_service.configuration_store.get_revision(
            plan.product_id,
            plan.configuration_id,
            plan.configuration_revision,
        )
        self._authorize(run, plan, configuration)

        environment_request = EnvironmentExecutionRequest(
            plan.run_id,
            plan.product_id,
            plan.configuration_id,
            plan.configuration_revision,
            plan.configuration_digest,
        )

        def browser_probe(
            exact_configuration: ManagedProductRuntimeConfiguration,
        ) -> BrowserExecutionResult:
            inputs: dict[str, str] = {}
            redactions: list[str] = []
            try:
                try:
                    for binding in plan.inputs:
                        if binding.public_value is not None:
                            inputs[binding.input_id] = binding.public_value
                        else:
                            assert binding.secret_reference is not None
                            value = self._resolve_input(binding.secret_reference)
                            inputs[binding.input_id] = value
                            redactions.append(value)
                    return self.provider.execute(
                        plan,
                        exact_configuration,
                        inputs,
                        tuple(redactions),
                        self.artifact_store,
                    )
                except (BrowserAuthorityError, BrowserProviderUnavailable) as error:
                    code = (
                        "BROWSER_INPUT_RESOLUTION_FAILED"
                        if isinstance(error, BrowserAuthorityError)
                        else "BROWSER_PROVIDER_UNAVAILABLE"
                    )
                    now = _now()
                    return BrowserExecutionResult(
                        plan.run_id,
                        plan.product_id,
                        plan.plan_id,
                        plan.digest,
                        plan.commit_sha,
                        BrowserExecutionStage.FAILED,
                        (),
                        (),
                        now,
                        now,
                        code,
                    )
            finally:
                inputs.clear()
                redactions.clear()

        execution = self.environment_service.verify_with_ready_probe(
            environment_request, browser_probe
        )
        environment_result = execution.environment_result
        browser_result = execution.probe_result
        if browser_result is None:
            stage = (
                BrowserExecutionStage.RECONCILIATION_REQUIRED
                if environment_result.stage is EnvironmentStage.RECONCILIATION_REQUIRED
                else BrowserExecutionStage.FAILED
            )
            browser_result = BrowserExecutionResult(
                plan.run_id,
                plan.product_id,
                plan.plan_id,
                plan.digest,
                plan.commit_sha,
                stage,
                (),
                (),
                environment_result.started_at,
                environment_result.completed_at,
                environment_result.failure_code or "ENVIRONMENT_NOT_READY",
            )
            return self.execution_store.save(browser_result)

        if (
            browser_result.run_id != plan.run_id
            or browser_result.product_id != plan.product_id
            or browser_result.plan_id != plan.plan_id
            or browser_result.plan_digest != plan.digest
            or browser_result.commit_sha != plan.commit_sha
        ):
            raise BrowserAuthorityError(
                "Browser provider result does not match its exact execution authority"
            )
        self._validate_provider_result(plan, browser_result)
        if not (
            environment_result.started_at
            <= browser_result.started_at
            <= browser_result.completed_at
            <= environment_result.completed_at
        ):
            raise BrowserAuthorityError(
                "Browser provider timestamps do not fit the managed environment window"
            )

        environment_evidence = self._environment_evidence(
            plan, environment_result.observations
        )
        terminal_stage = browser_result.stage
        failure_code = browser_result.failure_code
        if environment_result.stage is EnvironmentStage.RECONCILIATION_REQUIRED:
            terminal_stage = BrowserExecutionStage.RECONCILIATION_REQUIRED
            failure_code = environment_result.failure_code or failure_code
        elif environment_result.stage is not EnvironmentStage.STOPPED:
            terminal_stage = BrowserExecutionStage.FAILED
            failure_code = environment_result.failure_code or failure_code
        value = replace(
            browser_result,
            stage=terminal_stage,
            evidence=environment_evidence + browser_result.evidence,
            started_at=min(browser_result.started_at, environment_result.started_at),
            completed_at=max(browser_result.completed_at, environment_result.completed_at),
            failure_code=failure_code,
        )
        return self.execution_store.save(value)

    def _validate_provider_result(
        self,
        plan: BrowserJourneyPlan,
        result: BrowserExecutionResult,
    ) -> None:
        planned = {item.journey_id: item for item in plan.journeys}
        evidence_ids = [item.evidence_id for item in result.evidence]
        result_ids = [item.journey_id for item in result.journey_results]
        if len(evidence_ids) != len(set(evidence_ids)) or len(result_ids) != len(
            set(result_ids)
        ):
            raise BrowserAuthorityError("Browser provider returned duplicate evidence")
        if not set(result_ids) <= set(planned):
            raise BrowserAuthorityError("Browser provider returned an undeclared journey")
        evidence = {item.evidence_id: item for item in result.evidence}
        for item in result.evidence:
            journey = planned.get(item.journey_id)
            if (
                journey is None
                or item.run_id != plan.run_id
                or item.commit_sha != plan.commit_sha
                or item.capability_id != journey.capability_id
                or item.kind not in _BROWSER_EVIDENCE
            ):
                raise BrowserAuthorityError(
                    "Browser provider evidence escaped its exact journey authority"
                )
            self.artifact_store.verify(item.artifact_uri, item.digest)
        for journey_result in result.journey_results:
            linked = [evidence.get(item) for item in journey_result.evidence_ids]
            if any(item is None for item in linked) or any(
                item is not None and item.journey_id != journey_result.journey_id
                for item in linked
            ):
                raise BrowserAuthorityError(
                    "Browser journey result references unavailable evidence"
                )
            if journey_result.outcome is EvidenceOutcome.PASS:
                kinds = {item.kind for item in linked if item is not None}
                if kinds != _BROWSER_EVIDENCE or any(
                    item is not None and item.outcome is not EvidenceOutcome.PASS
                    for item in linked
                ):
                    raise BrowserAuthorityError(
                        "Passing browser journey lacks complete passing evidence"
                    )
        if result.stage is BrowserExecutionStage.COMPLETED:
            if set(result_ids) != set(planned) or any(
                item.outcome is not EvidenceOutcome.PASS
                for item in result.journey_results
            ):
                raise BrowserAuthorityError(
                    "Completed browser result does not cover every planned journey"
                )

    def _authorize(self, run, plan: BrowserJourneyPlan, configuration) -> None:  # noqa: ANN001
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
            raise BrowserAuthorityError(
                "Browser plan does not match the exact runtime acceptance binding"
            )
        if (
            configuration.project_id != plan.product_id
            or configuration.configuration_id != plan.configuration_id
            or configuration.revision != plan.configuration_revision
            or configuration.digest != plan.configuration_digest
            or configuration.commit_sha != plan.commit_sha
            or configuration.acceptance_profile_id != plan.acceptance_profile_id
            or configuration.acceptance_profile_version
            != plan.acceptance_profile_version
            or configuration.acceptance_profile_digest
            != plan.acceptance_profile_digest
        ):
            raise BrowserAuthorityError(
                "Browser plan does not match the persisted runtime configuration"
            )
        declared = {
            item.journey_id: item
            for item in run.journeys
            if item.customer_facing
        }
        planned = {item.journey_id: item for item in plan.journeys}
        if set(declared) != set(planned):
            raise BrowserAuthorityError(
                "Browser plan must cover every declared customer-facing journey"
            )
        for journey_id, specification in planned.items():
            contract = declared[journey_id]
            if (
                specification.capability_id != contract.capability_id
                or specification.title != contract.title
            ):
                raise BrowserAuthorityError(
                    "Browser journey does not match its locked acceptance contract"
                )
        if self.provider.provider_id not in self.policy.allowed_provider_ids:
            raise BrowserAuthorityError("Browser provider is not currently approved")
        origins = {
            endpoint_origin(value) for value in configuration.allowed_origins
        }
        if not origins <= self.policy.allowed_origins:
            raise BrowserAuthorityError("Browser origin is not currently approved")
        for binding in plan.inputs:
            if binding.secret_reference is None:
                continue
            if (
                binding.secret_reference not in self.policy.allowed_secret_references
                and not any(
                    binding.secret_reference.startswith(prefix)
                    for prefix in self.policy.allowed_secret_reference_prefixes
                )
            ):
                raise BrowserAuthorityError(
                    "Browser secret reference is not currently approved"
                )

    def _resolve_input(self, reference: str) -> str:
        failed = False
        value: str | None = None
        try:
            value = self.input_resolver.resolve(reference)
        except Exception:
            failed = True
        if (
            failed
            or not isinstance(value, str)
            or not value
            or len(value) > 8_192
            or "\0" in value
        ):
            raise BrowserAuthorityError(
                "An approved browser secret reference could not be resolved"
            )
        return value

    def _environment_evidence(
        self,
        plan: BrowserJourneyPlan,
        observations: tuple,
    ) -> tuple[EvidenceArtifact, ...]:
        journey = plan.journeys[0]
        artifacts: list[EvidenceArtifact] = []
        for index, observation in enumerate(observations):
            evidence_kind = _ENVIRONMENT_EVIDENCE.get(observation.kind)
            if evidence_kind is None:
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
                    "exit_code": observation.exit_code,
                    "configuration_digest": plan.configuration_digest,
                },
            )
            artifacts.append(
                EvidenceArtifact(
                    f"{plan.run_id}.{journey.journey_id}.environment-{index}",
                    plan.run_id,
                    journey.capability_id,
                    journey.journey_id,
                    evidence_kind,
                    EvidenceOutcome.PASS
                    if observation.outcome is EnvironmentObservationOutcome.PASS
                    else EvidenceOutcome.FAIL,
                    plan.commit_sha,
                    uri,
                    digest,
                    observation.completed_at,
                    observation.summary,
                    (("configuration_digest", plan.configuration_digest),),
                )
            )
        return tuple(artifacts)


def _now() -> datetime:
    return datetime.now(timezone.utc)
