"""Governed Day 34 preview-deployment orchestration and reconciliation."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from runtime.github_delivery import (
    ARTIFACT_STATUS as GITHUB_ARTIFACT_STATUS,
    DELIVERY_STATE as GITHUB_DELIVERY_STATE,
    PILOT_STATUS as GITHUB_PILOT_STATUS,
    PULL_REQUEST_STATE as GITHUB_PULL_REQUEST_STATE,
    FileGitHubDeliveryArtifactStore,
    GitHubDeliveryArtifact,
)
from runtime.preview_deployment.errors import (
    PreviewDeploymentConflict,
    PreviewDeploymentNotFound,
    PreviewDeploymentPolicyError,
)
from runtime.preview_deployment.models import (
    ARTIFACT_STATUS,
    DEPLOYMENT_STATE,
    ENVIRONMENT_STATE,
    MIGRATION_STATE,
    MONITORING_STATE,
    PILOT_STATUS,
    PREVIEW_DEPLOYMENT_ACTIONS,
    PREVIEW_DEPLOYMENT_CAPABILITIES,
    PREVIEW_DEPLOYMENT_TOOL_IDS,
    PRODUCTION_STATE,
    PULL_REQUEST_STATE,
    ROLLBACK_STATE,
    SOURCE_STATE,
    PreviewDeploymentArtifact,
    PreviewDeploymentAuthority,
    PreviewDeploymentObservation,
    PreviewDeploymentWorkOrder,
    artifact_id_for,
    canonical_digest,
)
from runtime.preview_deployment.persistence import FilePreviewDeploymentArtifactStore
from runtime.preview_deployment.provider import PreviewDeploymentProvider
from runtime.workforce_devops import (
    ARTIFACT_STATUS as DEVOPS_ARTIFACT_STATUS,
    EXECUTION_STATE as DEVOPS_EXECUTION_STATE,
    PILOT_STATUS as DEVOPS_PILOT_STATUS,
    PREVIEW_ENVIRONMENT_CLASS,
    DevOpsWorkArtifact,
    FileDevOpsArtifactStore,
)


class PreviewDeploymentService:
    """Validate exact Day 28/33 sources and authorize one isolated preview effect."""

    def __init__(
        self,
        provider: PreviewDeploymentProvider,
        github_delivery_store: FileGitHubDeliveryArtifactStore,
        devops_store: FileDevOpsArtifactStore,
        preview_store: FilePreviewDeploymentArtifactStore,
        *,
        clock=None,  # noqa: ANN001
    ) -> None:
        self._provider = provider
        self._github_delivery_store = github_delivery_store
        self._devops_store = devops_store
        self._store = preview_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        work_order: PreviewDeploymentWorkOrder,
        authority: PreviewDeploymentAuthority,
        github_delivery_artifact: GitHubDeliveryArtifact,
        devops_artifact: DevOpsWorkArtifact,
    ) -> PreviewDeploymentArtifact:
        if not isinstance(work_order, PreviewDeploymentWorkOrder) or not isinstance(
            authority, PreviewDeploymentAuthority
        ):
            raise PreviewDeploymentPolicyError("Preview deployment input is invalid")
        existing = self._existing(work_order.tenant_id, execution_id)
        if existing is not None:
            if not (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.github_delivery_artifact_digest == github_delivery_artifact.digest
                and existing.devops_artifact_digest == devops_artifact.digest
            ):
                raise PreviewDeploymentConflict(
                    "Preview execution already has different immutable state"
                )
            return existing

        self._validate_github_delivery(work_order, github_delivery_artifact)
        self._validate_devops(work_order, github_delivery_artifact, devops_artifact)
        self._validate_authority(work_order, authority, self._clock())
        observation = self._provider.deploy(work_order, authority)
        if not isinstance(observation, PreviewDeploymentObservation):
            raise PreviewDeploymentPolicyError("Preview provider observation is invalid")
        self._validate_observation(work_order, authority, observation)
        generated_at = self._clock()
        artifact = PreviewDeploymentArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            github_delivery_artifact_id=github_delivery_artifact.artifact_id,
            github_delivery_artifact_digest=github_delivery_artifact.digest,
            devops_artifact_id=devops_artifact.artifact_id,
            devops_artifact_digest=devops_artifact.digest,
            coding_review_artifact_digest=github_delivery_artifact.coding_review_artifact_digest,
            workspace_artifact_digest=github_delivery_artifact.workspace_artifact_digest,
            orchestration_artifact_digest=github_delivery_artifact.orchestration_artifact_digest,
            qa_artifact_digest=github_delivery_artifact.qa_artifact_digest,
            security_artifact_digest=github_delivery_artifact.security_artifact_digest,
            repository_id=work_order.repository_id,
            repository_full_name=work_order.repository_full_name,
            feature_branch=work_order.feature_branch,
            approved_commit=work_order.approved_commit,
            approved_tree=work_order.approved_tree,
            draft_pull_request_number=work_order.draft_pull_request_number,
            draft_pull_request_digest=work_order.draft_pull_request_digest,
            preview_environment_id=work_order.preview_environment_id,
            preview_url=work_order.preview_url,
            preview_plan_digest=work_order.preview_plan_digest,
            migration_plan_digest=work_order.migration_plan_digest,
            deployment_plan_digest=work_order.deployment_plan_digest,
            monitoring_plan_digest=work_order.monitoring_plan_digest,
            rollback_plan_digest=work_order.rollback_plan_digest,
            configuration_digest=work_order.configuration_digest,
            secret_reference_count=len(work_order.secret_reference_ids),
            provider_id=observation.provider_id,
            authority_digest=authority.digest,
            capability_ids=PREVIEW_DEPLOYMENT_CAPABILITIES,
            action_ids=PREVIEW_DEPLOYMENT_ACTIONS,
            tool_ids=PREVIEW_DEPLOYMENT_TOOL_IDS,
            environment_class=observation.environment_class,
            deployed_commit=observation.deployed_commit,
            deployed_tree=observation.deployed_tree,
            deployment_revision=observation.deployment_revision,
            health_receipts=observation.health_receipts,
            platform_call_count=observation.platform_call_count,
            credential_handle_count=observation.credential_handle_count,
            provider_output_digest=observation.digest,
            generated_at=generated_at,
            expires_at=generated_at + timedelta(minutes=work_order.preview_ttl_minutes),
            deployment_count=observation.deployment_count,
            migration_count=observation.migration_count,
            monitoring_configuration_count=observation.monitoring_configuration_count,
            rollback_count=observation.rollback_count,
            production_deployment_count=observation.production_deployment_count,
            merge_count=observation.merge_count,
            release_count=observation.release_count,
            billing_count=observation.billing_count,
            secret_value_exposure_count=observation.secret_value_exposure_count,
            unapproved_network_call_count=observation.unapproved_network_call_count,
            general_command_count=observation.general_command_count,
            source_state=SOURCE_STATE,
            pull_request_state=PULL_REQUEST_STATE,
            environment_state=ENVIRONMENT_STATE,
            deployment_state=DEPLOYMENT_STATE,
            migration_state=MIGRATION_STATE,
            monitoring_state=MONITORING_STATE,
            rollback_state=ROLLBACK_STATE,
            production_state=PRODUCTION_STATE,
            status=ARTIFACT_STATUS,
            pilot_status=PILOT_STATUS,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> PreviewDeploymentArtifact:
        return self._store.load(tenant_id, execution_id)

    def _existing(self, tenant_id: str, execution_id: str) -> PreviewDeploymentArtifact | None:
        try:
            return self._store.load(tenant_id, execution_id)
        except PreviewDeploymentNotFound:
            return None

    def _validate_github_delivery(
        self,
        work_order: PreviewDeploymentWorkOrder,
        artifact: GitHubDeliveryArtifact,
    ) -> None:
        if not isinstance(artifact, GitHubDeliveryArtifact):
            raise PreviewDeploymentPolicyError("Preview GitHub-delivery source is invalid")
        if not (
            artifact.digest == work_order.github_delivery_artifact_digest
            and artifact.tenant_id == work_order.tenant_id
            and artifact.opportunity_id == work_order.opportunity_id
            and artifact.repository_id == work_order.repository_id
            and artifact.repository_full_name == work_order.repository_full_name
            and artifact.feature_branch == work_order.feature_branch
            and artifact.commit_sha == work_order.approved_commit
            and artifact.commit_tree == work_order.approved_tree
            and artifact.remote_branch_sha == work_order.approved_commit
            and artifact.pull_request.number == work_order.draft_pull_request_number
            and artifact.pull_request.digest == work_order.draft_pull_request_digest
            and artifact.pull_request.head_commit == work_order.approved_commit
            and artifact.pull_request.draft
            and artifact.pull_request.state == "OPEN"
            and not artifact.pull_request.merged
            and artifact.status == GITHUB_ARTIFACT_STATUS
            and artifact.pull_request_state == GITHUB_PULL_REQUEST_STATE
            and artifact.delivery_state == GITHUB_DELIVERY_STATE
            and artifact.pilot_status == GITHUB_PILOT_STATUS == PILOT_STATUS
            and (artifact.commit_count, artifact.push_count, artifact.pull_request_count)
            == (1, 1, 1)
            and artifact.force_push_count == artifact.merge_count == artifact.deployment_count == 0
            and artifact.release_count == 0
        ):
            raise PreviewDeploymentPolicyError(
                "Preview deployment requires the exact successful Day 33 delivery artifact"
            )
        persisted = self._github_delivery_store.load(artifact.tenant_id, artifact.execution_id)
        if persisted != artifact:
            raise PreviewDeploymentPolicyError(
                "Preview GitHub-delivery source is not exact persisted state"
            )

    def _validate_devops(
        self,
        work_order: PreviewDeploymentWorkOrder,
        delivery: GitHubDeliveryArtifact,
        artifact: DevOpsWorkArtifact,
    ) -> None:
        plans = (
            artifact.preview_environment,
            artifact.migration_plan,
            artifact.deployment_plan,
            artifact.monitoring_plan,
            artifact.rollback_plan,
        ) if isinstance(artifact, DevOpsWorkArtifact) else ()
        if not (
            isinstance(artifact, DevOpsWorkArtifact)
            and artifact.digest == work_order.devops_artifact_digest
            and artifact.tenant_id == work_order.tenant_id
            and artifact.opportunity_id == work_order.opportunity_id
            and artifact.qa_artifact_digest == delivery.qa_artifact_digest
            and artifact.security_artifact_digest == delivery.security_artifact_digest
            and artifact.status == DEVOPS_ARTIFACT_STATUS
            and artifact.pilot_status == DEVOPS_PILOT_STATUS == PILOT_STATUS
            and all(plan.execution_state == DEVOPS_EXECUTION_STATE for plan in plans)
            and artifact.preview_environment.environment_class == PREVIEW_ENVIRONMENT_CLASS
            and artifact.deployment_plan.target_environment == PREVIEW_ENVIRONMENT_CLASS
            and artifact.monitoring_plan.target_environment == PREVIEW_ENVIRONMENT_CLASS
            and artifact.rollback_plan.target_environment == PREVIEW_ENVIRONMENT_CLASS
            and _plan_digest(artifact.preview_environment) == work_order.preview_plan_digest
            and _plan_digest(artifact.migration_plan) == work_order.migration_plan_digest
            and _plan_digest(artifact.deployment_plan) == work_order.deployment_plan_digest
            and _plan_digest(artifact.monitoring_plan) == work_order.monitoring_plan_digest
            and _plan_digest(artifact.rollback_plan) == work_order.rollback_plan_digest
        ):
            raise PreviewDeploymentPolicyError(
                "Preview deployment requires the exact matching persisted Day 28 DevOps plans"
            )
        persisted = self._devops_store.load(artifact.tenant_id, artifact.execution_id)
        if persisted != artifact:
            raise PreviewDeploymentPolicyError("Preview DevOps source is not exact persisted state")

    @staticmethod
    def _validate_authority(
        work_order: PreviewDeploymentWorkOrder,
        authority: PreviewDeploymentAuthority,
        now: datetime,
    ) -> None:
        if not (
            authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.work_order_digest == work_order.digest
            and authority.github_delivery_artifact_digest
            == work_order.github_delivery_artifact_digest
            and authority.devops_artifact_digest == work_order.devops_artifact_digest
            and authority.repository_id == work_order.repository_id
            and authority.approved_commit == work_order.approved_commit
            and authority.preview_environment_id == work_order.preview_environment_id
            and authority.allowed_action_ids == PREVIEW_DEPLOYMENT_ACTIONS
            and authority.allowed_tool_ids == PREVIEW_DEPLOYMENT_TOOL_IDS
            and len(work_order.health_check_urls) <= authority.max_health_checks
            and len(work_order.secret_reference_ids) <= authority.max_secret_references
            and authority.issued_at <= now < authority.expires_at
            and work_order.issued_at <= now < work_order.expires_at
        ):
            raise PreviewDeploymentPolicyError("Preview deployment authority is invalid or expired")

    @staticmethod
    def _validate_observation(
        work_order: PreviewDeploymentWorkOrder,
        authority: PreviewDeploymentAuthority,
        observation: PreviewDeploymentObservation,
    ) -> None:
        if not (
            observation.environment_id == work_order.preview_environment_id
            and observation.environment_class == PREVIEW_ENVIRONMENT_CLASS
            and observation.preview_url == work_order.preview_url
            and observation.deployed_commit == work_order.approved_commit
            and observation.deployed_tree == work_order.approved_tree
            and observation.configuration_digest == work_order.configuration_digest
            and tuple(item.url for item in observation.health_receipts)
            == work_order.health_check_urls
            and observation.platform_call_count <= authority.max_platform_calls
            and observation.credential_handle_count == len(work_order.secret_reference_ids)
            and (observation.deployment_count, observation.migration_count)
            == (1, 1)
            and observation.monitoring_configuration_count == 1
            and observation.rollback_count
            == observation.production_deployment_count
            == observation.merge_count
            == observation.release_count
            == observation.billing_count
            == observation.secret_value_exposure_count
            == observation.unapproved_network_call_count
            == observation.general_command_count
            == 0
        ):
            raise PreviewDeploymentPolicyError(
                "Preview provider result does not match the authorized exact deployment"
            )


def _plan_digest(value: Any) -> str:
    return canonical_digest(asdict(value))
