"""Governed Day 35 complete runtime-acceptance service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from runtime.complete_runtime_acceptance.errors import (
    RuntimeAcceptanceConflict,
    RuntimeAcceptanceNotFound,
    RuntimeAcceptancePolicyError,
)
from runtime.complete_runtime_acceptance.models import (
    COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS,
    COMPLETE_RUNTIME_ACCEPTANCE_CAPABILITIES,
    COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS,
    CompleteRuntimeAcceptanceArtifact,
    CompleteRuntimeAcceptanceAuthority,
    CompleteRuntimeAcceptanceWorkOrder,
    RuntimeAcceptanceObservation,
    artifact_id_for,
)
from runtime.complete_runtime_acceptance.persistence import (
    FileCompleteRuntimeAcceptanceArtifactStore,
)
from runtime.complete_runtime_acceptance.provider import (
    CompleteRuntimeAcceptanceProvider,
)
from runtime.managed_product_browser import BrowserJourneyPlan, BrowserJourneyPlanStore
from runtime.managed_product_runtime import ManagedProductRuntimeConfiguration
from runtime.managed_product_runtime.models import endpoint_origin
from runtime.managed_product_runtime.persistence import RuntimeConfigurationStore
from runtime.preview_deployment import (
    ARTIFACT_STATUS as PREVIEW_ARTIFACT_STATUS,
    ENVIRONMENT_STATE as PREVIEW_ENVIRONMENT_STATE,
    PILOT_STATUS,
    PRODUCTION_STATE as PREVIEW_PRODUCTION_STATE,
    FilePreviewDeploymentArtifactStore,
    PreviewDeploymentArtifact,
)


class CompleteRuntimeAcceptanceService:
    """Verify exact sources, run one complete browser plan, and persist its result."""

    def __init__(
        self,
        provider: CompleteRuntimeAcceptanceProvider,
        preview_store: FilePreviewDeploymentArtifactStore,
        configuration_store: RuntimeConfigurationStore,
        plan_store: BrowserJourneyPlanStore,
        artifact_store: FileCompleteRuntimeAcceptanceArtifactStore,
        *,
        clock=None,  # noqa: ANN001
    ) -> None:
        if not isinstance(provider, CompleteRuntimeAcceptanceProvider):
            raise TypeError("Complete runtime-acceptance provider is invalid")
        if not isinstance(preview_store, FilePreviewDeploymentArtifactStore):
            raise TypeError("Preview artifact store is invalid")
        if not isinstance(configuration_store, RuntimeConfigurationStore):
            raise TypeError("Runtime configuration store is invalid")
        if not isinstance(plan_store, BrowserJourneyPlanStore):
            raise TypeError("Browser journey-plan store is invalid")
        if not isinstance(artifact_store, FileCompleteRuntimeAcceptanceArtifactStore):
            raise TypeError("Complete runtime-acceptance artifact store is invalid")
        self._provider = provider
        self._preview_store = preview_store
        self._configuration_store = configuration_store
        self._plan_store = plan_store
        self._artifact_store = artifact_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        work_order: CompleteRuntimeAcceptanceWorkOrder,
        authority: CompleteRuntimeAcceptanceAuthority,
        preview_artifact: PreviewDeploymentArtifact,
        runtime_configuration: ManagedProductRuntimeConfiguration,
        browser_plan: BrowserJourneyPlan,
    ) -> CompleteRuntimeAcceptanceArtifact:
        if not isinstance(work_order, CompleteRuntimeAcceptanceWorkOrder):
            raise RuntimeAcceptancePolicyError("Runtime-acceptance work order is invalid")
        if not isinstance(authority, CompleteRuntimeAcceptanceAuthority):
            raise RuntimeAcceptancePolicyError("Runtime-acceptance authority is invalid")
        if not isinstance(preview_artifact, PreviewDeploymentArtifact):
            raise RuntimeAcceptancePolicyError("Runtime-acceptance preview source is invalid")
        if not isinstance(runtime_configuration, ManagedProductRuntimeConfiguration):
            raise RuntimeAcceptancePolicyError(
                "Runtime-acceptance configuration source is invalid"
            )
        if not isinstance(browser_plan, BrowserJourneyPlan):
            raise RuntimeAcceptancePolicyError("Runtime-acceptance browser plan is invalid")

        try:
            existing = self._artifact_store.load(work_order.tenant_id, execution_id)
        except RuntimeAcceptanceNotFound:
            existing = None
        if existing is not None:
            if not (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.preview_artifact_digest == preview_artifact.digest
                and existing.runtime_configuration_digest == runtime_configuration.digest
                and existing.browser_plan_digest == browser_plan.digest
            ):
                raise RuntimeAcceptanceConflict(
                    "Runtime-acceptance retry does not match the immutable execution"
                )
            return existing

        now = self._clock()
        self._authorize(
            execution_id,
            work_order,
            authority,
            preview_artifact,
            runtime_configuration,
            browser_plan,
            now,
        )
        observation = self._provider.execute(
            work_order,
            authority,
            runtime_configuration,
            browser_plan,
        )
        self._validate_observation(work_order, authority, observation)
        artifact = CompleteRuntimeAcceptanceArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            preview_artifact_id=preview_artifact.artifact_id,
            preview_artifact_digest=preview_artifact.digest,
            github_delivery_artifact_digest=preview_artifact.github_delivery_artifact_digest,
            devops_artifact_digest=preview_artifact.devops_artifact_digest,
            coding_review_artifact_digest=preview_artifact.coding_review_artifact_digest,
            workspace_artifact_digest=preview_artifact.workspace_artifact_digest,
            orchestration_artifact_digest=preview_artifact.orchestration_artifact_digest,
            qa_artifact_digest=preview_artifact.qa_artifact_digest,
            security_artifact_digest=preview_artifact.security_artifact_digest,
            product_id=work_order.product_id,
            repository_id=work_order.repository_id,
            repository_full_name=work_order.repository_full_name,
            feature_branch=work_order.feature_branch,
            approved_commit=work_order.approved_commit,
            approved_tree=work_order.approved_tree,
            preview_environment_id=work_order.preview_environment_id,
            preview_url=work_order.preview_url,
            deployment_revision=work_order.deployment_revision,
            runtime_configuration_id=work_order.runtime_configuration_id,
            runtime_configuration_revision=work_order.runtime_configuration_revision,
            runtime_configuration_digest=runtime_configuration.digest,
            acceptance_run_id=work_order.acceptance_run_id,
            acceptance_profile_id=work_order.acceptance_profile_id,
            acceptance_profile_version=work_order.acceptance_profile_version,
            acceptance_profile_digest=work_order.acceptance_profile_digest,
            browser_plan_id=work_order.browser_plan_id,
            browser_plan_digest=browser_plan.digest,
            browser_execution_digest=observation.browser_execution_digest,
            authority_digest=authority.digest,
            provider_id=observation.provider_id,
            provider_output_digest=observation.digest,
            capability_ids=work_order.capability_ids,
            journey_ids=work_order.journey_ids,
            journey_receipts=observation.journey_receipts,
            governance_capability_ids=COMPLETE_RUNTIME_ACCEPTANCE_CAPABILITIES,
            action_ids=COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS,
            tool_ids=COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS,
            browser_launch_count=observation.browser_launch_count,
            authenticated_session_count=observation.authenticated_session_count,
            evidence_artifact_count=observation.evidence_artifact_count,
            screenshot_count=observation.screenshot_count,
            generated_at=now,
            expires_at=min(preview_artifact.expires_at, now + timedelta(hours=8)),
        )
        return self._artifact_store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> CompleteRuntimeAcceptanceArtifact:
        return self._artifact_store.load(tenant_id, execution_id)

    def _authorize(
        self,
        execution_id: str,
        work_order: CompleteRuntimeAcceptanceWorkOrder,
        authority: CompleteRuntimeAcceptanceAuthority,
        preview: PreviewDeploymentArtifact,
        configuration: ManagedProductRuntimeConfiguration,
        plan: BrowserJourneyPlan,
        now: datetime,
    ) -> None:
        artifact_id_for(execution_id)
        if not work_order.issued_at <= now < work_order.expires_at:
            raise RuntimeAcceptancePolicyError(
                "Runtime-acceptance work order is not currently valid"
            )
        if not authority.issued_at <= now < authority.expires_at:
            raise RuntimeAcceptancePolicyError(
                "Runtime-acceptance authority is not currently valid"
            )
        if not preview.generated_at <= now < preview.expires_at:
            raise RuntimeAcceptancePolicyError(
                "The isolated preview is not currently valid for acceptance"
            )
        if not (
            authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.work_order_digest == work_order.digest
            and authority.preview_artifact_digest == work_order.preview_artifact_digest
            and authority.product_id == work_order.product_id
            and authority.acceptance_run_id == work_order.acceptance_run_id
            and authority.browser_plan_digest == work_order.browser_plan_digest
            and authority.approved_commit == work_order.approved_commit
            and authority.preview_environment_id == work_order.preview_environment_id
            and authority.allowed_action_ids == COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS
            and authority.allowed_tool_ids == COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS
            and len(work_order.journey_ids) <= authority.max_journeys
            and len(work_order.login_secret_reference_ids)
            <= authority.max_secret_references
        ):
            raise RuntimeAcceptancePolicyError(
                "Runtime-acceptance authority does not match the exact work order"
            )

        persisted_preview = self._preview_store.load(
            preview.tenant_id, preview.execution_id
        )
        if persisted_preview != preview:
            raise RuntimeAcceptancePolicyError(
                "Runtime acceptance requires the exact persisted preview artifact"
            )
        if not (
            preview.digest == work_order.preview_artifact_digest
            and preview.tenant_id == work_order.tenant_id
            and preview.opportunity_id == work_order.opportunity_id
            and preview.repository_id == work_order.repository_id
            and preview.repository_full_name == work_order.repository_full_name
            and preview.feature_branch == work_order.feature_branch
            and preview.approved_commit
            == preview.deployed_commit
            == work_order.approved_commit
            and preview.approved_tree == preview.deployed_tree == work_order.approved_tree
            and preview.preview_environment_id == work_order.preview_environment_id
            and preview.preview_url == work_order.preview_url
            and preview.deployment_revision == work_order.deployment_revision
            and preview.configuration_digest == work_order.preview_configuration_digest
            and preview.environment_state == PREVIEW_ENVIRONMENT_STATE
            and preview.production_state == PREVIEW_PRODUCTION_STATE
            and preview.status == PREVIEW_ARTIFACT_STATUS
            and preview.pilot_status == PILOT_STATUS
            and all(item.status_code == 200 for item in preview.health_receipts)
            and preview.production_deployment_count
            == preview.merge_count
            == preview.release_count
            == preview.billing_count
            == preview.secret_value_exposure_count
            == preview.unapproved_network_call_count
            == preview.general_command_count
            == 0
        ):
            raise RuntimeAcceptancePolicyError(
                "Day 34 preview source is not exact, healthy, and non-production"
            )

        persisted_configuration = self._configuration_store.get_revision(
            work_order.product_id,
            work_order.runtime_configuration_id,
            work_order.runtime_configuration_revision,
        )
        if persisted_configuration != configuration:
            raise RuntimeAcceptancePolicyError(
                "Runtime acceptance requires the exact persisted configuration"
            )
        expected_repository = (
            f"https://github.com/{work_order.repository_full_name}"
        )
        actual_repository = configuration.repository_url.removesuffix(".git")
        if not (
            configuration.project_id == work_order.product_id
            and configuration.configuration_id == work_order.runtime_configuration_id
            and configuration.revision == work_order.runtime_configuration_revision
            and configuration.digest == work_order.runtime_configuration_digest
            and actual_repository == expected_repository
            and configuration.branch == work_order.feature_branch
            and configuration.commit_sha == work_order.approved_commit
            and endpoint_origin(configuration.frontend_url)
            == work_order.preview_url.rstrip("/")
            and configuration.acceptance_profile_id
            == work_order.acceptance_profile_id
            and configuration.acceptance_profile_version
            == work_order.acceptance_profile_version
            and configuration.acceptance_profile_digest
            == work_order.acceptance_profile_digest
        ):
            raise RuntimeAcceptancePolicyError(
                "Runtime configuration drifted from the approved preview contract"
            )

        persisted_plan = self._plan_store.load(
            work_order.product_id,
            work_order.acceptance_run_id,
            work_order.browser_plan_id,
        )
        if persisted_plan != plan:
            raise RuntimeAcceptancePolicyError(
                "Runtime acceptance requires the exact persisted browser plan"
            )
        capability_ids = tuple(dict.fromkeys(item.capability_id for item in plan.journeys))
        journey_ids = tuple(item.journey_id for item in plan.journeys)
        secret_references = tuple(
            sorted(
                item.secret_reference
                for item in plan.inputs
                if item.secret_reference is not None
            )
        )
        if not (
            plan.plan_id == work_order.browser_plan_id
            and plan.run_id == work_order.acceptance_run_id
            and plan.product_id == work_order.product_id
            and plan.configuration_id == work_order.runtime_configuration_id
            and plan.configuration_revision == work_order.runtime_configuration_revision
            and plan.configuration_digest == work_order.runtime_configuration_digest
            and plan.commit_sha == work_order.approved_commit
            and plan.acceptance_profile_id == work_order.acceptance_profile_id
            and plan.acceptance_profile_version == work_order.acceptance_profile_version
            and plan.acceptance_profile_digest == work_order.acceptance_profile_digest
            and plan.digest == work_order.browser_plan_digest
            and capability_ids == work_order.capability_ids
            and journey_ids == work_order.journey_ids
            and work_order.authentication_journey_id in journey_ids
            and secret_references == work_order.login_secret_reference_ids
        ):
            raise RuntimeAcceptancePolicyError(
                "Browser plan drifted from the complete runtime-acceptance contract"
            )

    @staticmethod
    def _validate_observation(
        work_order: CompleteRuntimeAcceptanceWorkOrder,
        authority: CompleteRuntimeAcceptanceAuthority,
        observation: RuntimeAcceptanceObservation,
    ) -> None:
        if not isinstance(observation, RuntimeAcceptanceObservation):
            raise RuntimeAcceptancePolicyError("Runtime provider result is invalid")
        if not (
            observation.product_id == work_order.product_id
            and observation.acceptance_run_id == work_order.acceptance_run_id
            and observation.browser_plan_id == work_order.browser_plan_id
            and observation.browser_plan_digest == work_order.browser_plan_digest
            and observation.runtime_configuration_digest
            == work_order.runtime_configuration_digest
            and observation.acceptance_profile_digest
            == work_order.acceptance_profile_digest
            and observation.approved_commit == work_order.approved_commit
            and observation.preview_environment_id
            == work_order.preview_environment_id
            and observation.preview_url == work_order.preview_url
            and tuple(item.journey_id for item in observation.journey_receipts)
            == work_order.journey_ids
            and tuple(
                dict.fromkeys(
                    item.capability_id for item in observation.journey_receipts
                )
            )
            == work_order.capability_ids
            and observation.browser_launch_count <= authority.max_browser_launches
            and len(observation.journey_receipts) <= authority.max_journeys
            and observation.console_error_count
            == observation.network_failure_count
            == observation.raw_secret_exposure_count
            == observation.repository_write_count
            == observation.preview_mutation_count
            == observation.production_deployment_count
            == observation.merge_count
            == observation.release_count
            == observation.billing_count
            == observation.pilot_selection_count
            == 0
        ):
            raise RuntimeAcceptancePolicyError(
                "Runtime provider result does not match the authorized exact acceptance"
            )
