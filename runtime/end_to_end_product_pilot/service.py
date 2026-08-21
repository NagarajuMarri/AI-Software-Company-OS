"""Governed Day 36 service for the first end-to-end product pilot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from runtime.complete_runtime_acceptance import (
    ARTIFACT_STATUS as RUNTIME_ARTIFACT_STATUS,
    AUTHENTICATION_STATE as RUNTIME_AUTHENTICATION_STATE,
    BROWSER_STATE as RUNTIME_BROWSER_STATE,
    JOURNEY_STATE as RUNTIME_JOURNEY_STATE,
    PREVIEW_STATE as RUNTIME_PREVIEW_STATE,
    PRODUCTION_STATE as RUNTIME_PRODUCTION_STATE,
    FileCompleteRuntimeAcceptanceArtifactStore,
    CompleteRuntimeAcceptanceArtifact,
)
from runtime.customer_application.models import CustomerProductRequest, ProductRequestStage
from runtime.customer_application.persistence import FileCustomerProductRequestStore
from runtime.customer_prd.approval_models import CustomerPrdApproval
from runtime.customer_prd.approval_persistence import FileCustomerPrdApprovalStore
from runtime.customer_prd.models import CustomerPrdDraft
from runtime.customer_prd.persistence import FileCustomerPrdStore
from runtime.customer_roadmap.approval_models import CustomerRoadmapApproval
from runtime.customer_roadmap.approval_persistence import FileCustomerRoadmapApprovalStore
from runtime.customer_roadmap.models import CustomerRoadmapDraft
from runtime.customer_roadmap.persistence import FileCustomerRoadmapStore
from runtime.end_to_end_product_pilot.errors import (
    ProductPilotConflict,
    ProductPilotNotFound,
    ProductPilotPolicyError,
)
from runtime.end_to_end_product_pilot.models import (
    END_TO_END_PRODUCT_PILOT_ACTIONS,
    END_TO_END_PRODUCT_PILOT_CAPABILITIES,
    END_TO_END_PRODUCT_PILOT_TOOL_IDS,
    PILOT_STAGE_IDS,
    EndToEndProductPilotArtifact,
    EndToEndProductPilotAuthority,
    EndToEndProductPilotWorkOrder,
    ProductPilotSourceSnapshot,
    artifact_id_for,
    product_binding_digest_for,
)
from runtime.end_to_end_product_pilot.persistence import (
    FileEndToEndProductPilotArtifactStore,
)
from runtime.end_to_end_product_pilot.provider import EndToEndProductPilotProvider
from runtime.preview_deployment import (
    ARTIFACT_STATUS as PREVIEW_ARTIFACT_STATUS,
    ENVIRONMENT_STATE as PREVIEW_ENVIRONMENT_STATE,
    PILOT_STATUS as SOURCE_PILOT_STATUS,
    PRODUCTION_STATE as PREVIEW_PRODUCTION_STATE,
    PULL_REQUEST_STATE as PREVIEW_PULL_REQUEST_STATE,
    FilePreviewDeploymentArtifactStore,
    PreviewDeploymentArtifact,
)


class EndToEndProductPilotService:
    """Verify the entire persisted source chain and save one terminal pilot artifact."""

    def __init__(
        self,
        provider: EndToEndProductPilotProvider,
        request_store: FileCustomerProductRequestStore,
        prd_store: FileCustomerPrdStore,
        prd_approval_store: FileCustomerPrdApprovalStore,
        roadmap_store: FileCustomerRoadmapStore,
        roadmap_approval_store: FileCustomerRoadmapApprovalStore,
        preview_store: FilePreviewDeploymentArtifactStore,
        runtime_acceptance_store: FileCompleteRuntimeAcceptanceArtifactStore,
        artifact_store: FileEndToEndProductPilotArtifactStore,
        *,
        clock=None,  # noqa: ANN001
    ) -> None:
        expected = (
            (provider, EndToEndProductPilotProvider, "provider"),
            (request_store, FileCustomerProductRequestStore, "request store"),
            (prd_store, FileCustomerPrdStore, "PRD store"),
            (prd_approval_store, FileCustomerPrdApprovalStore, "PRD approval store"),
            (roadmap_store, FileCustomerRoadmapStore, "roadmap store"),
            (
                roadmap_approval_store,
                FileCustomerRoadmapApprovalStore,
                "roadmap approval store",
            ),
            (preview_store, FilePreviewDeploymentArtifactStore, "preview store"),
            (
                runtime_acceptance_store,
                FileCompleteRuntimeAcceptanceArtifactStore,
                "runtime-acceptance store",
            ),
            (artifact_store, FileEndToEndProductPilotArtifactStore, "artifact store"),
        )
        for value, kind, label in expected:
            if not isinstance(value, kind):
                raise TypeError(f"Product-pilot {label} is invalid")
        self._provider = provider
        self._request_store = request_store
        self._prd_store = prd_store
        self._prd_approval_store = prd_approval_store
        self._roadmap_store = roadmap_store
        self._roadmap_approval_store = roadmap_approval_store
        self._preview_store = preview_store
        self._runtime_store = runtime_acceptance_store
        self._artifact_store = artifact_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        work_order: EndToEndProductPilotWorkOrder,
        authority: EndToEndProductPilotAuthority,
        product_request: CustomerProductRequest,
        prd: CustomerPrdDraft,
        prd_approval: CustomerPrdApproval,
        roadmap: CustomerRoadmapDraft,
        roadmap_approval: CustomerRoadmapApproval,
        preview: PreviewDeploymentArtifact,
        runtime_acceptance: CompleteRuntimeAcceptanceArtifact,
    ) -> EndToEndProductPilotArtifact:
        expected = (
            (work_order, EndToEndProductPilotWorkOrder, "work order"),
            (authority, EndToEndProductPilotAuthority, "authority"),
            (product_request, CustomerProductRequest, "customer idea"),
            (prd, CustomerPrdDraft, "PRD"),
            (prd_approval, CustomerPrdApproval, "PRD approval"),
            (roadmap, CustomerRoadmapDraft, "roadmap"),
            (roadmap_approval, CustomerRoadmapApproval, "roadmap approval"),
            (preview, PreviewDeploymentArtifact, "preview"),
            (
                runtime_acceptance,
                CompleteRuntimeAcceptanceArtifact,
                "runtime acceptance",
            ),
        )
        for value, kind, label in expected:
            if not isinstance(value, kind):
                raise ProductPilotPolicyError(f"Product-pilot {label} is invalid")

        existing = self._existing(work_order.tenant_id, execution_id)
        if existing is not None:
            if not (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.source_request_digest == product_request.digest
                and existing.runtime_acceptance_artifact_digest == runtime_acceptance.digest
            ):
                raise ProductPilotConflict(
                    "Product-pilot retry does not match the immutable execution"
                )
            return existing

        now = self._clock()
        self._authorize(work_order, authority, now)
        self._validate_persisted_sources(
            work_order,
            product_request,
            prd,
            prd_approval,
            roadmap,
            roadmap_approval,
            preview,
            runtime_acceptance,
            now,
        )
        snapshot = self._snapshot(
            work_order,
            product_request,
            prd,
            prd_approval,
            roadmap,
            roadmap_approval,
            preview,
            runtime_acceptance,
        )
        observation = self._provider.execute(work_order, authority, snapshot)
        expected_stage_sources = (
            product_request.digest,
            prd_approval.digest,
            roadmap_approval.digest,
            runtime_acceptance.orchestration_artifact_digest,
            runtime_acceptance.coding_review_artifact_digest,
            runtime_acceptance.github_delivery_artifact_digest,
            preview.digest,
            runtime_acceptance.digest,
        )
        if (
            tuple(item.stage_id for item in observation.stage_receipts) != PILOT_STAGE_IDS
            or tuple(item.source_digest for item in observation.stage_receipts)
            != expected_stage_sources
            or observation.snapshot_digest != snapshot.digest
            or observation.source_record_count != authority.max_source_records
            or len(observation.stage_receipts) != authority.max_stage_receipts
        ):
            raise ProductPilotPolicyError("Product-pilot evidence does not bind exact sources")

        artifact = EndToEndProductPilotArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            authority_digest=authority.digest,
            tenant_id=work_order.tenant_id,
            customer_id=work_order.customer_id,
            request_id=work_order.request_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            pilot_id=work_order.pilot_id,
            customer_product_id=work_order.customer_product_id,
            runtime_product_id=work_order.runtime_product_id,
            product_binding_digest=work_order.product_binding_digest,
            source_request_digest=product_request.digest,
            prd_digest=prd.digest,
            prd_approval_digest=prd_approval.digest,
            roadmap_digest=roadmap.digest,
            roadmap_approval_digest=roadmap_approval.digest,
            orchestration_artifact_digest=runtime_acceptance.orchestration_artifact_digest,
            workspace_artifact_digest=runtime_acceptance.workspace_artifact_digest,
            coding_review_artifact_digest=runtime_acceptance.coding_review_artifact_digest,
            qa_artifact_digest=runtime_acceptance.qa_artifact_digest,
            security_artifact_digest=runtime_acceptance.security_artifact_digest,
            github_delivery_artifact_digest=runtime_acceptance.github_delivery_artifact_digest,
            devops_artifact_digest=runtime_acceptance.devops_artifact_digest,
            preview_artifact_digest=preview.digest,
            runtime_acceptance_artifact_digest=runtime_acceptance.digest,
            runtime_configuration_digest=runtime_acceptance.runtime_configuration_digest,
            acceptance_profile_digest=runtime_acceptance.acceptance_profile_digest,
            browser_plan_digest=runtime_acceptance.browser_plan_digest,
            browser_execution_digest=runtime_acceptance.browser_execution_digest,
            repository_full_name=work_order.repository_full_name,
            feature_branch=work_order.feature_branch,
            approved_commit=work_order.approved_commit,
            approved_tree=work_order.approved_tree,
            draft_pull_request_number=work_order.draft_pull_request_number,
            preview_environment_id=work_order.preview_environment_id,
            preview_url=work_order.preview_url,
            journey_ids=work_order.journey_ids,
            provider_id=observation.provider_id,
            provider_output_digest=observation.digest,
            stage_receipts=observation.stage_receipts,
            governance_capability_ids=END_TO_END_PRODUCT_PILOT_CAPABILITIES,
            action_ids=END_TO_END_PRODUCT_PILOT_ACTIONS,
            tool_ids=END_TO_END_PRODUCT_PILOT_TOOL_IDS,
            source_record_count=observation.source_record_count,
            completed_journey_count=observation.completed_journey_count,
            passed_journey_count=observation.passed_journey_count,
            report_count=observation.report_count,
            generated_at=now,
            expires_at=min(runtime_acceptance.expires_at, now + timedelta(hours=8)),
        )
        return self._artifact_store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> EndToEndProductPilotArtifact:
        return self._artifact_store.load(tenant_id, execution_id)

    def _existing(self, tenant_id: str, execution_id: str) -> EndToEndProductPilotArtifact | None:
        try:
            return self._artifact_store.load(tenant_id, execution_id)
        except ProductPilotNotFound:
            return None

    @staticmethod
    def _authorize(
        work_order: EndToEndProductPilotWorkOrder,
        authority: EndToEndProductPilotAuthority,
        now: datetime,
    ) -> None:
        if not work_order.issued_at <= now < work_order.expires_at:
            raise ProductPilotPolicyError("Product-pilot work order is not currently valid")
        if not authority.issued_at <= now < authority.expires_at:
            raise ProductPilotPolicyError("Product-pilot authority is not currently valid")
        if not (
            authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.pilot_id == work_order.pilot_id
            and authority.work_order_digest == work_order.digest
            and authority.source_request_digest == work_order.source_request_digest
            and authority.roadmap_approval_digest == work_order.roadmap_approval_digest
            and authority.runtime_acceptance_artifact_digest
            == work_order.runtime_acceptance_artifact_digest
            and authority.product_binding_digest == work_order.product_binding_digest
            and authority.allowed_action_ids == END_TO_END_PRODUCT_PILOT_ACTIONS
            and authority.allowed_tool_ids == END_TO_END_PRODUCT_PILOT_TOOL_IDS
            and len(work_order.journey_ids) <= authority.max_journeys
        ):
            raise ProductPilotPolicyError("Product-pilot authority does not match the work order")

    def _validate_persisted_sources(
        self,
        order: EndToEndProductPilotWorkOrder,
        request: CustomerProductRequest,
        prd: CustomerPrdDraft,
        prd_approval: CustomerPrdApproval,
        roadmap: CustomerRoadmapDraft,
        roadmap_approval: CustomerRoadmapApproval,
        preview: PreviewDeploymentArtifact,
        runtime: CompleteRuntimeAcceptanceArtifact,
        now: datetime,
    ) -> None:
        persisted = (
            self._request_store.load(order.customer_id, order.request_id),
            self._prd_store.load(order.customer_id, order.request_id),
            self._prd_approval_store.load(order.customer_id, order.request_id),
            self._roadmap_store.load(order.customer_id, order.request_id),
            self._roadmap_approval_store.load(order.customer_id, order.request_id),
            self._preview_store.load(preview.tenant_id, preview.execution_id),
            self._runtime_store.load(runtime.tenant_id, runtime.execution_id),
        )
        supplied = (request, prd, prd_approval, roadmap, roadmap_approval, preview, runtime)
        if persisted != supplied:
            raise ProductPilotPolicyError("Product pilot requires exact persisted sources")

        if not (
            request.stage is ProductRequestStage.SUBMITTED
            and request.customer_id == prd.customer_id == prd_approval.customer_id
            == roadmap.customer_id == roadmap_approval.customer_id == order.customer_id
            and request.request_id == prd.request_id == prd_approval.request_id
            == roadmap.request_id == roadmap_approval.request_id == order.request_id
            and request.digest == prd.source_request_digest
            == prd_approval.source_request_digest == roadmap.source_request_digest
            == roadmap_approval.source_request_digest == order.source_request_digest
            and prd.digest == prd_approval.prd_digest == roadmap.prd_digest
            == roadmap_approval.prd_digest == order.prd_digest
            and prd_approval.digest == roadmap.prd_approval_digest
            == roadmap_approval.prd_approval_digest == order.prd_approval_digest
            and roadmap.digest == roadmap_approval.roadmap_digest == order.roadmap_digest
            and roadmap_approval.digest == order.roadmap_approval_digest
            and prd.product_id == prd_approval.product_id == roadmap.product_id
            == roadmap_approval.product_id == order.customer_product_id
            and prd.prd_id == prd_approval.prd_id == roadmap.prd_id
            == roadmap_approval.prd_id
        ):
            raise ProductPilotPolicyError("Customer idea, locked PRD, or roadmap chain drifted")

        expected_binding = product_binding_digest_for(
            order.pilot_id,
            order.customer_product_id,
            order.runtime_product_id,
            request.digest,
        )
        if expected_binding != order.product_binding_digest:
            raise ProductPilotPolicyError("Pilot customer/runtime product binding is invalid")

        if not preview.generated_at <= now < preview.expires_at:
            raise ProductPilotPolicyError("Pilot preview is not currently valid")
        if not runtime.generated_at <= now < runtime.expires_at:
            raise ProductPilotPolicyError("Pilot runtime acceptance is not currently valid")
        if not (
            preview.digest == order.preview_artifact_digest
            and runtime.preview_artifact_digest == preview.digest
            and runtime.digest == order.runtime_acceptance_artifact_digest
            and runtime.tenant_id == preview.tenant_id == order.tenant_id
            and runtime.opportunity_id == preview.opportunity_id == order.opportunity_id
            and runtime.product_id == order.runtime_product_id
            and runtime.repository_full_name == preview.repository_full_name
            == order.repository_full_name
            and runtime.feature_branch == preview.feature_branch == order.feature_branch
            and runtime.approved_commit == preview.approved_commit
            == preview.deployed_commit == order.approved_commit
            and runtime.approved_tree == preview.approved_tree
            == preview.deployed_tree == order.approved_tree
            and preview.draft_pull_request_number == order.draft_pull_request_number
            and runtime.preview_environment_id == preview.preview_environment_id
            == order.preview_environment_id
            and runtime.preview_url == preview.preview_url == order.preview_url
            and runtime.journey_ids == order.journey_ids
            and runtime.github_delivery_artifact_digest
            == preview.github_delivery_artifact_digest
            and runtime.coding_review_artifact_digest
            == preview.coding_review_artifact_digest
            and runtime.orchestration_artifact_digest
            == preview.orchestration_artifact_digest
            and runtime.qa_artifact_digest == preview.qa_artifact_digest
            and runtime.security_artifact_digest == preview.security_artifact_digest
            and runtime.status == RUNTIME_ARTIFACT_STATUS
            and runtime.preview_state == RUNTIME_PREVIEW_STATE
            and runtime.authentication_state == RUNTIME_AUTHENTICATION_STATE
            and runtime.journey_state == RUNTIME_JOURNEY_STATE
            and runtime.browser_state == RUNTIME_BROWSER_STATE
            and runtime.production_state == RUNTIME_PRODUCTION_STATE
            and preview.status == PREVIEW_ARTIFACT_STATUS
            and preview.pull_request_state == PREVIEW_PULL_REQUEST_STATE
            and preview.environment_state == PREVIEW_ENVIRONMENT_STATE
            and preview.production_state == PREVIEW_PRODUCTION_STATE
            and preview.pilot_status == runtime.pilot_status == SOURCE_PILOT_STATUS
            and all(item.outcome == "PASS" for item in runtime.journey_receipts)
        ):
            raise ProductPilotPolicyError("Execution, draft PR, preview, or runtime chain drifted")
        if not (
            runtime.browser_launch_count == 1
            and runtime.authenticated_session_count == len(runtime.journey_ids)
            and runtime.screenshot_count == len(runtime.journey_ids)
            and runtime.console_error_count == runtime.network_failure_count
            == runtime.raw_secret_exposure_count == runtime.repository_write_count
            == runtime.preview_mutation_count == runtime.production_deployment_count
            == runtime.merge_count == runtime.release_count == runtime.billing_count
            == runtime.pilot_selection_count == 0
            and preview.production_deployment_count == preview.merge_count
            == preview.release_count == preview.billing_count
            == preview.secret_value_exposure_count == preview.unapproved_network_call_count
            == preview.general_command_count == 0
        ):
            raise ProductPilotPolicyError("Pilot source chain crossed a prohibited boundary")

    @staticmethod
    def _snapshot(
        order: EndToEndProductPilotWorkOrder,
        request: CustomerProductRequest,
        prd: CustomerPrdDraft,
        prd_approval: CustomerPrdApproval,
        roadmap: CustomerRoadmapDraft,
        roadmap_approval: CustomerRoadmapApproval,
        preview: PreviewDeploymentArtifact,
        runtime: CompleteRuntimeAcceptanceArtifact,
    ) -> ProductPilotSourceSnapshot:
        return ProductPilotSourceSnapshot(
            pilot_id=order.pilot_id,
            source_request_digest=request.digest,
            prd_digest=prd.digest,
            prd_approval_digest=prd_approval.digest,
            roadmap_digest=roadmap.digest,
            roadmap_approval_digest=roadmap_approval.digest,
            orchestration_artifact_digest=runtime.orchestration_artifact_digest,
            coding_review_artifact_digest=runtime.coding_review_artifact_digest,
            github_delivery_artifact_digest=runtime.github_delivery_artifact_digest,
            preview_artifact_digest=preview.digest,
            runtime_acceptance_artifact_digest=runtime.digest,
            product_binding_digest=order.product_binding_digest,
            repository_full_name=order.repository_full_name,
            feature_branch=order.feature_branch,
            approved_commit=order.approved_commit,
            approved_tree=order.approved_tree,
            draft_pull_request_number=order.draft_pull_request_number,
            preview_environment_id=order.preview_environment_id,
            preview_url=order.preview_url,
            journey_ids=order.journey_ids,
        )
