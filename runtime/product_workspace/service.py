"""Exact-orchestration-bound composition for ASCOS Day 31 workspaces."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from runtime.product_workspace.errors import (
    ProductWorkspaceConflict,
    ProductWorkspaceNotFound,
    ProductWorkspacePolicyError,
)
from runtime.product_workspace.models import (
    ARTIFACT_STATUS,
    BRANCH_STATE,
    PILOT_STATUS,
    SOURCE_STATE,
    WORKSPACE_ACTIONS,
    WORKSPACE_CAPABILITIES,
    WORKSPACE_STATE,
    WORKSPACE_TOOL_IDS,
    ProductWorkspaceArtifact,
    ProductWorkspaceAuthority,
    ProductWorkspaceWorkOrder,
    WorkspacePreparationObservation,
    artifact_id_for,
)
from runtime.product_workspace.persistence import FileProductWorkspaceArtifactStore
from runtime.product_workspace.provider import ProductWorkspaceProvider
from runtime.workforce_orchestration import (
    ARTIFACT_STATUS as ORCHESTRATION_ARTIFACT_STATUS,
    PILOT_STATUS as ORCHESTRATION_PILOT_STATUS,
    FileOrchestrationArtifactStore,
    MultiAgentOrchestrationArtifact,
)


class ProductWorkspaceService:
    """Create one exact-base workspace without running product implementation."""

    def __init__(
        self,
        provider: ProductWorkspaceProvider,
        orchestration_store: FileOrchestrationArtifactStore,
        store: FileProductWorkspaceArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._orchestration_store = orchestration_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        work_order: ProductWorkspaceWorkOrder,
        authority: ProductWorkspaceAuthority,
        orchestration_artifact: MultiAgentOrchestrationArtifact,
        source_repository: Path,
    ) -> ProductWorkspaceArtifact:
        if not isinstance(work_order, ProductWorkspaceWorkOrder):
            raise ProductWorkspacePolicyError("Product workspace work order is invalid")
        if not isinstance(orchestration_artifact, MultiAgentOrchestrationArtifact):
            raise ProductWorkspacePolicyError("Product workspace orchestration source is invalid")
        if not isinstance(source_repository, Path):
            raise ProductWorkspacePolicyError("Product workspace source repository is invalid")
        existing = self._existing(work_order.tenant_id, execution_id)
        if existing is not None:
            if not (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.orchestration_artifact_digest == orchestration_artifact.digest
                and existing.repository_identity == work_order.repository_identity
                and existing.base_commit == work_order.expected_base_commit
                and existing.feature_branch == work_order.feature_branch
                and existing.workspace_id == work_order.workspace_id
            ):
                raise ProductWorkspaceConflict(
                    "Product workspace execution already has different immutable state"
                )
            return existing

        self._validate_source(work_order, orchestration_artifact)
        self._validate_authority(work_order, authority, orchestration_artifact, self._clock())
        observation = self._provider.prepare(source_repository, work_order, authority)
        self._validate_observation(work_order, authority, observation)
        artifact = ProductWorkspaceArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            orchestration_artifact_id=orchestration_artifact.artifact_id,
            orchestration_artifact_digest=orchestration_artifact.digest,
            repository_id=work_order.repository_id,
            repository_identity=work_order.repository_identity,
            provider_id=observation.provider_id,
            authority_digest=authority.digest,
            capability_ids=WORKSPACE_CAPABILITIES,
            action_ids=WORKSPACE_ACTIONS,
            tool_ids=WORKSPACE_TOOL_IDS,
            workspace_id=work_order.workspace_id,
            workspace_relative_path=observation.workspace_relative_path,
            base_branch=work_order.base_branch,
            base_commit=work_order.expected_base_commit,
            base_tree=observation.source_tree_before,
            feature_branch=work_order.feature_branch,
            workspace_head=observation.workspace_head,
            workspace_tree=observation.workspace_tree,
            git_command_count=observation.git_command_count,
            network_call_count=observation.network_call_count,
            general_command_count=observation.general_command_count,
            product_file_write_count=observation.product_file_write_count,
            unrelated_path_change_count=observation.unrelated_path_change_count,
            provider_output_digest=observation.digest,
            generated_at=self._clock(),
            source_state=SOURCE_STATE,
            workspace_state=WORKSPACE_STATE,
            branch_state=BRANCH_STATE,
            status=ARTIFACT_STATUS,
            pilot_status=PILOT_STATUS,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> ProductWorkspaceArtifact:
        return self._store.load(tenant_id, execution_id)

    def _existing(self, tenant_id: str, execution_id: str) -> ProductWorkspaceArtifact | None:
        try:
            return self._store.load(tenant_id, execution_id)
        except ProductWorkspaceNotFound:
            return None

    def _validate_source(
        self,
        work_order: ProductWorkspaceWorkOrder,
        orchestration: MultiAgentOrchestrationArtifact,
    ) -> None:
        if not (
            orchestration.tenant_id == work_order.tenant_id
            and orchestration.opportunity_id == work_order.opportunity_id
            and orchestration.digest == work_order.orchestration_artifact_digest
            and orchestration.status == ORCHESTRATION_ARTIFACT_STATUS
            and orchestration.pilot_status == ORCHESTRATION_PILOT_STATUS == PILOT_STATUS
        ):
            raise ProductWorkspacePolicyError(
                "Product workspace requires the exact approved Day 30 orchestration source"
            )
        try:
            persisted = self._orchestration_store.load(
                orchestration.tenant_id, orchestration.execution_id
            )
        except Exception as error:
            raise ProductWorkspacePolicyError(
                "Product workspace orchestration source is not persisted"
            ) from error
        if persisted != orchestration:
            raise ProductWorkspacePolicyError(
                "Product workspace orchestration source does not match persisted state"
            )

    @staticmethod
    def _validate_authority(
        work_order: ProductWorkspaceWorkOrder,
        authority: ProductWorkspaceAuthority,
        orchestration: MultiAgentOrchestrationArtifact,
        now: datetime,
    ) -> None:
        if not isinstance(authority, ProductWorkspaceAuthority):
            raise ProductWorkspacePolicyError("Product workspace authority is invalid")
        if not (
            authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.work_order_digest == work_order.digest
            and authority.orchestration_artifact_digest == orchestration.digest
            and authority.allowed_action_ids == WORKSPACE_ACTIONS
            and authority.allowed_tool_ids == WORKSPACE_TOOL_IDS
            and authority.max_workspaces == 1
            and not authority.network_allowed
            and not authority.source_file_writes_allowed
            and not authority.workspace_file_mutation_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.issued_at <= now <= authority.expires_at
        ):
            raise ProductWorkspacePolicyError(
                "Product workspace authority, source, assignment, tool, or time boundary does not match"
            )

    @staticmethod
    def _validate_observation(
        work_order: ProductWorkspaceWorkOrder,
        authority: ProductWorkspaceAuthority,
        observation: WorkspacePreparationObservation,
    ) -> None:
        if not isinstance(observation, WorkspacePreparationObservation):
            raise ProductWorkspacePolicyError("Product workspace provider observation is invalid")
        if not (
            observation.workspace_relative_path == work_order.workspace_id
            and observation.source_branch_before == work_order.base_branch
            and observation.source_branch_after == work_order.base_branch
            and observation.workspace_branch == work_order.feature_branch
            and observation.source_head_before == work_order.expected_base_commit
            and observation.source_head_after == work_order.expected_base_commit
            and observation.workspace_head == work_order.expected_base_commit
            and observation.source_tree_before == observation.source_tree_after
            and observation.workspace_tree == observation.source_tree_before
            and observation.git_command_count <= authority.max_tool_calls
            and observation.network_call_count == 0
            and observation.general_command_count == 0
            and observation.product_file_write_count == 0
            and observation.unrelated_path_change_count == 0
            and observation.source_state == SOURCE_STATE
            and observation.workspace_state == WORKSPACE_STATE
            and observation.branch_state == BRANCH_STATE
        ):
            raise ProductWorkspacePolicyError(
                "Product workspace provider crossed its exact-base or no-write boundary"
            )
