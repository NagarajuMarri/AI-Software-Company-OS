"""Governed orchestration for ASCOS V1 hardening and founder acceptance."""

from __future__ import annotations

from datetime import datetime, timezone

from runtime.end_to_end_product_pilot import (
    ARTIFACT_STATUS as PILOT_ARTIFACT_STATUS,
    END_TO_END_PRODUCT_PILOT_CAPABILITIES,
    PILOT_STAGE_IDS,
    PRODUCTION_STATE as PILOT_PRODUCTION_STATE,
    EndToEndProductPilotArtifact,
)
from runtime.v1_hardening_acceptance.errors import (
    V1HardeningConflict,
    V1HardeningPolicyError,
)
from runtime.v1_hardening_acceptance.models import (
    DOCUMENTATION_IDS,
    V1_HARDENING_ACTIONS,
    V1_HARDENING_CAPABILITIES,
    V1_HARDENING_TOOL_IDS,
    V1HardeningAcceptanceArtifact,
    V1HardeningAuthority,
    V1HardeningSourceSnapshot,
    V1HardeningWorkOrder,
    artifact_id_for,
    canonical_digest,
    hardening_policy_digests_for,
)
from runtime.v1_hardening_acceptance.persistence import (
    FileV1HardeningAcceptanceArtifactStore,
)
from runtime.v1_hardening_acceptance.provider import V1HardeningProvider


class V1HardeningAcceptanceService:
    """Verify the final V1 control package without approving or releasing it."""

    def __init__(
        self,
        provider: V1HardeningProvider,
        pilot_store,  # noqa: ANN001
        artifact_store: FileV1HardeningAcceptanceArtifactStore,
        *,
        clock=None,  # noqa: ANN001
    ) -> None:
        self.provider = provider
        self.pilot_store = pilot_store
        self.artifact_store = artifact_store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        work_order: V1HardeningWorkOrder,
        authority: V1HardeningAuthority,
        pilot: EndToEndProductPilotArtifact,
    ) -> V1HardeningAcceptanceArtifact:
        now = self.clock()
        existing = self.artifact_store.find(work_order.tenant_id, execution_id)
        if existing is not None:
            if (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.source_pilot_artifact_digest == pilot.digest
            ):
                return existing
            raise V1HardeningConflict("Day 37 retry changed immutable inputs")
        self._validate_authority(work_order, authority, now)
        persisted = self.pilot_store.load(
            work_order.tenant_id, work_order.source_pilot_execution_id
        )
        if persisted != pilot:
            raise V1HardeningPolicyError("Day 36 pilot is not the exact persisted artifact")
        self._validate_pilot(work_order, pilot)
        snapshot = self._snapshot(work_order, pilot)
        observation = self.provider.execute(work_order, authority, snapshot)
        if (
            observation.provider_id != self.provider.provider_id
            or observation.pilot_id != pilot.pilot_id
            or observation.snapshot_digest != snapshot.digest
        ):
            raise V1HardeningPolicyError("Day 37 provider output changed source identity")
        artifact = V1HardeningAcceptanceArtifact(
            artifact_id=artifact_id_for(work_order.tenant_id, execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            authority_digest=authority.digest,
            tenant_id=work_order.tenant_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            pilot_id=pilot.pilot_id,
            source_pilot_execution_id=pilot.execution_id,
            source_pilot_artifact_digest=pilot.digest,
            security_artifact_digest=pilot.security_artifact_digest,
            devops_artifact_digest=pilot.devops_artifact_digest,
            documentation_artifact_digest=canonical_digest(
                {
                    "orchestration_artifact_digest": pilot.orchestration_artifact_digest,
                    "documentation_ids": DOCUMENTATION_IDS,
                }
            ),
            runtime_acceptance_artifact_digest=pilot.runtime_acceptance_artifact_digest,
            repository_full_name=pilot.repository_full_name,
            feature_branch=pilot.feature_branch,
            approved_commit=pilot.approved_commit,
            approved_tree=pilot.approved_tree,
            draft_pull_request_number=pilot.draft_pull_request_number,
            preview_url=pilot.preview_url,
            journey_ids=pilot.journey_ids,
            provider_id=observation.provider_id,
            provider_output_digest=observation.digest,
            control_receipts=observation.control_receipts,
            monitoring_receipts=observation.monitoring_receipts,
            documentation_ids=observation.documentation_ids,
            governance_capability_ids=V1_HARDENING_CAPABILITIES,
            action_ids=V1_HARDENING_ACTIONS,
            tool_ids=V1_HARDENING_TOOL_IDS,
            backup_copy_count=observation.backup_copy_count,
            recovery_drill_count=observation.recovery_drill_count,
            audit_entry_count=observation.audit_entry_count,
            monitoring_signal_count=len(observation.monitoring_receipts),
            documentation_record_count=len(observation.documentation_ids),
            founder_uat_journey_count=len(pilot.journey_ids),
            report_count=observation.report_count,
            generated_at=now,
            expires_at=work_order.expires_at,
        )
        self.artifact_store.save(artifact)
        self.artifact_store.verify_backup(artifact)
        return artifact

    def get(self, tenant_id: str, execution_id: str) -> V1HardeningAcceptanceArtifact:
        return self.artifact_store.load(tenant_id, execution_id)

    @staticmethod
    def _validate_authority(
        work_order: V1HardeningWorkOrder,
        authority: V1HardeningAuthority,
        now: datetime,
    ) -> None:
        if not work_order.issued_at <= now < work_order.expires_at:
            raise V1HardeningPolicyError("Day 37 work order is not current")
        if not authority.issued_at <= now < authority.expires_at:
            raise V1HardeningPolicyError("Day 37 authority is not current")
        if (
            authority.tenant_id != work_order.tenant_id
            or authority.assignment_id != work_order.assignment_id
            or authority.pilot_id != work_order.pilot_id
            or authority.work_order_digest != work_order.digest
            or authority.source_pilot_artifact_digest != work_order.source_pilot_artifact_digest
            or authority.control_source_digests != work_order.control_source_digests
        ):
            raise V1HardeningPolicyError("Day 37 authority binding is invalid")

    @staticmethod
    def _validate_pilot(
        work_order: V1HardeningWorkOrder,
        pilot: EndToEndProductPilotArtifact,
    ) -> None:
        if (
            pilot.tenant_id != work_order.tenant_id
            or pilot.execution_id != work_order.source_pilot_execution_id
            or pilot.pilot_id != work_order.pilot_id
            or pilot.digest != work_order.source_pilot_artifact_digest
            or pilot.repository_full_name != work_order.repository_full_name
            or pilot.feature_branch != work_order.feature_branch
            or pilot.approved_commit != work_order.approved_commit
            or pilot.approved_tree != work_order.approved_tree
            or pilot.draft_pull_request_number != work_order.draft_pull_request_number
            or pilot.preview_url != work_order.preview_url
            or pilot.journey_ids != work_order.journey_ids
        ):
            raise V1HardeningPolicyError("Day 36 pilot identity or digest drifted")
        if work_order.control_source_digests != hardening_policy_digests_for(pilot.digest):
            raise V1HardeningPolicyError("Day 37 hardening contract digest drifted")
        if (
            pilot.status != PILOT_ARTIFACT_STATUS
            or pilot.production_state != PILOT_PRODUCTION_STATE
            or tuple(item.stage_id for item in pilot.stage_receipts) != PILOT_STAGE_IDS
            or pilot.governance_capability_ids != END_TO_END_PRODUCT_PILOT_CAPABILITIES
            or pilot.source_record_count != 7
            or pilot.completed_journey_count != pilot.passed_journey_count
            or pilot.passed_journey_count != len(work_order.journey_ids)
        ):
            raise V1HardeningPolicyError("Day 36 pilot is not terminal and complete")
        if any(
            value != 0
            for value in (
                pilot.repository_write_count,
                pilot.pull_request_mutation_count,
                pilot.preview_mutation_count,
                pilot.merge_count,
                pilot.production_deployment_count,
                pilot.release_count,
                pilot.billing_count,
                pilot.risk_acceptance_count,
                pilot.day37_action_count,
            )
        ):
            raise V1HardeningPolicyError("Day 36 pilot contains prohibited effects")

    @staticmethod
    def _snapshot(
        work_order: V1HardeningWorkOrder,
        pilot: EndToEndProductPilotArtifact,
    ) -> V1HardeningSourceSnapshot:
        return V1HardeningSourceSnapshot(
            pilot_id=pilot.pilot_id,
            source_pilot_artifact_digest=pilot.digest,
            security_artifact_digest=pilot.security_artifact_digest,
            devops_artifact_digest=pilot.devops_artifact_digest,
            documentation_artifact_digest=canonical_digest(
                {
                    "orchestration_artifact_digest": pilot.orchestration_artifact_digest,
                    "documentation_ids": DOCUMENTATION_IDS,
                }
            ),
            runtime_acceptance_artifact_digest=pilot.runtime_acceptance_artifact_digest,
            repository_full_name=pilot.repository_full_name,
            feature_branch=pilot.feature_branch,
            approved_commit=pilot.approved_commit,
            approved_tree=pilot.approved_tree,
            draft_pull_request_number=pilot.draft_pull_request_number,
            preview_url=pilot.preview_url,
            journey_ids=pilot.journey_ids,
            control_source_digests=work_order.control_source_digests,
            monitoring_signal_ids=work_order.monitoring_signal_ids,
            documentation_ids=work_order.documentation_ids,
        )
