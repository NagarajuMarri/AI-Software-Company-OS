"""Closed browser provider composition for Day 35 runtime acceptance."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runtime.complete_runtime_acceptance.errors import RuntimeAcceptancePolicyError
from runtime.complete_runtime_acceptance.models import (
    CompleteRuntimeAcceptanceAuthority,
    CompleteRuntimeAcceptanceWorkOrder,
    RuntimeAcceptanceObservation,
    RuntimeJourneyReceipt,
    canonical_digest,
)
from runtime.managed_product_browser import (
    BrowserArtifactStore,
    BrowserExecutionStage,
    BrowserInputResolver,
    BrowserJourneyPlan,
    ManagedProductBrowserProvider,
)
from runtime.managed_product_runtime import ManagedProductRuntimeConfiguration
from runtime.managed_product_runtime.models import endpoint_origin
from runtime.runtime_acceptance import EvidenceKind, EvidenceOutcome


@runtime_checkable
class CompleteRuntimeAcceptanceProvider(Protocol):
    def execute(
        self,
        work_order: CompleteRuntimeAcceptanceWorkOrder,
        authority: CompleteRuntimeAcceptanceAuthority,
        configuration: ManagedProductRuntimeConfiguration,
        plan: BrowserJourneyPlan,
    ) -> RuntimeAcceptanceObservation: ...


class ControlledCompleteRuntimeAcceptanceProvider:
    """Resolve scoped inputs and run one exact declarative plan in Chromium."""

    provider_id = "controlled-complete-runtime-acceptance-v1"

    def __init__(
        self,
        browser_provider: ManagedProductBrowserProvider,
        input_resolver: BrowserInputResolver,
        artifact_store: BrowserArtifactStore,
    ) -> None:
        if not isinstance(browser_provider, ManagedProductBrowserProvider):
            raise TypeError("Managed browser provider is invalid")
        if not isinstance(input_resolver, BrowserInputResolver):
            raise TypeError("Browser input resolver is invalid")
        if not isinstance(artifact_store, BrowserArtifactStore):
            raise TypeError("Browser artifact store is invalid")
        self._browser_provider = browser_provider
        self._input_resolver = input_resolver
        self._artifact_store = artifact_store
        self.execution_count = 0

    def execute(
        self,
        work_order: CompleteRuntimeAcceptanceWorkOrder,
        authority: CompleteRuntimeAcceptanceAuthority,
        configuration: ManagedProductRuntimeConfiguration,
        plan: BrowserJourneyPlan,
    ) -> RuntimeAcceptanceObservation:
        if not isinstance(work_order, CompleteRuntimeAcceptanceWorkOrder) or not isinstance(
            authority, CompleteRuntimeAcceptanceAuthority
        ):
            raise RuntimeAcceptancePolicyError("Runtime provider authority input is invalid")
        if not isinstance(configuration, ManagedProductRuntimeConfiguration) or not isinstance(
            plan, BrowserJourneyPlan
        ):
            raise RuntimeAcceptancePolicyError("Runtime provider contract input is invalid")
        if endpoint_origin(configuration.frontend_url) != work_order.preview_url.rstrip("/"):
            raise RuntimeAcceptancePolicyError(
                "Browser provider target does not match the exact approved preview"
            )
        secret_references = tuple(
            sorted(
                item.secret_reference
                for item in plan.inputs
                if item.secret_reference is not None
            )
        )
        if secret_references != work_order.login_secret_reference_ids:
            raise RuntimeAcceptancePolicyError(
                "Browser plan login references do not match the authorized opaque set"
            )
        if len(secret_references) > authority.max_secret_references:
            raise RuntimeAcceptancePolicyError("Browser login reference budget was exceeded")
        secret_input_ids = {
            item.input_id for item in plan.inputs if item.secret_reference is not None
        }
        if any(
            not secret_input_ids
            <= {step.input_id for step in journey.steps if step.input_id}
            or not any(step.action.value == "CLICK" for step in journey.steps)
            for journey in plan.journeys
        ):
            raise RuntimeAcceptancePolicyError(
                "Every isolated runtime journey must perform scoped authentication"
            )

        inputs: dict[str, str] = {}
        redactions: list[str] = []
        try:
            for binding in plan.inputs:
                if binding.public_value is not None:
                    inputs[binding.input_id] = binding.public_value
                    continue
                assert binding.secret_reference is not None
                try:
                    value = self._input_resolver.resolve(binding.secret_reference)
                except Exception as error:
                    raise RuntimeAcceptancePolicyError(
                        "Opaque browser input resolution failed before Chromium launched"
                    ) from error
                if (
                    not isinstance(value, str)
                    or not value
                    or len(value) > 8_192
                    or "\0" in value
                ):
                    raise RuntimeAcceptancePolicyError(
                        "Resolved browser input is outside policy"
                    )
                inputs[binding.input_id] = value
                redactions.append(value)
            self.execution_count += 1
            try:
                result = self._browser_provider.execute(
                    plan,
                    configuration,
                    inputs,
                    tuple(redactions),
                    self._artifact_store,
                )
            except Exception as error:
                raise RuntimeAcceptancePolicyError(
                    "Isolated Chromium execution failed"
                ) from error
        finally:
            inputs.clear()
            redactions.clear()

        if (
            result.run_id != plan.run_id
            or result.product_id != plan.product_id
            or result.plan_id != plan.plan_id
            or result.plan_digest != plan.digest
            or result.commit_sha != plan.commit_sha
            or result.stage is not BrowserExecutionStage.COMPLETED
            or result.failure_code is not None
        ):
            raise RuntimeAcceptancePolicyError(
                "Browser result did not complete the exact authorized plan"
            )
        results = {item.journey_id: item for item in result.journey_results}
        evidence_by_journey = {
            journey.journey_id: tuple(
                item for item in result.evidence if item.journey_id == journey.journey_id
            )
            for journey in plan.journeys
        }
        if set(results) != {item.journey_id for item in plan.journeys}:
            raise RuntimeAcceptancePolicyError(
                "Browser result did not cover every declared module journey"
            )
        receipts: list[RuntimeJourneyReceipt] = []
        required_kinds = {
            EvidenceKind.BROWSER,
            EvidenceKind.BROWSER_CONSOLE,
            EvidenceKind.BROWSER_NETWORK,
            EvidenceKind.SCREENSHOT,
        }
        for journey in plan.journeys:
            result_item = results[journey.journey_id]
            evidence = evidence_by_journey[journey.journey_id]
            kinds = {item.kind for item in evidence}
            screenshots = tuple(
                item for item in evidence if item.kind is EvidenceKind.SCREENSHOT
            )
            if (
                result_item.outcome is not EvidenceOutcome.PASS
                or any(item.outcome is not EvidenceOutcome.PASS for item in evidence)
                or not required_kinds <= kinds
                or len(screenshots) != 1
                or set(result_item.evidence_ids) != {item.evidence_id for item in evidence}
            ):
                raise RuntimeAcceptancePolicyError(
                    "A declared runtime journey lacks complete passing browser evidence"
                )
            receipts.append(
                RuntimeJourneyReceipt(
                    journey_id=journey.journey_id,
                    capability_id=journey.capability_id,
                    title=journey.title,
                    outcome="PASS",
                    evidence_count=len(evidence),
                    evidence_digest=_evidence_digest(evidence),
                    screenshot_digest=screenshots[0].digest,
                    completed_at=result_item.completed_at,
                )
            )
        if work_order.authentication_journey_id not in results:
            raise RuntimeAcceptancePolicyError(
                "The exact authentication journey was not completed"
            )
        observation = RuntimeAcceptanceObservation(
            provider_id=self.provider_id,
            product_id=plan.product_id,
            acceptance_run_id=plan.run_id,
            browser_plan_id=plan.plan_id,
            browser_plan_digest=plan.digest,
            runtime_configuration_digest=configuration.digest,
            acceptance_profile_digest=plan.acceptance_profile_digest,
            approved_commit=plan.commit_sha,
            preview_environment_id=work_order.preview_environment_id,
            preview_url=work_order.preview_url,
            browser_execution_digest=result.digest,
            journey_receipts=tuple(receipts),
            browser_launch_count=1,
            authenticated_session_count=len(receipts),
            evidence_artifact_count=len(result.evidence),
            screenshot_count=len(receipts),
        )
        if len(observation.journey_receipts) > authority.max_journeys:
            raise RuntimeAcceptancePolicyError("Runtime journey budget was exceeded")
        return observation


def _evidence_digest(evidence) -> str:  # noqa: ANN001
    return canonical_digest(
        [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "digest": item.digest,
                "artifact_uri": item.artifact_uri,
                "observed_at": item.observed_at.isoformat(),
            }
            for item in sorted(evidence, key=lambda item: item.evidence_id)
        ]
    )
