"""Governed exact-source composition for ASCOS Day 30 orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from runtime.agents import AgentRole
from runtime.workforce_architecture import ArchitectureProposalArtifact, FileArchitectureArtifactStore
from runtime.workforce_devops import DevOpsWorkArtifact, FileDevOpsArtifactStore
from runtime.workforce_documentation import DocumentationWorkArtifact, FileDocumentationArtifactStore
from runtime.workforce_engineering import ENGINEERING_ROLES, EngineeringWorkArtifact, FileEngineeringArtifactStore
from runtime.workforce_leadership import FileLeadershipArtifactStore, LeadershipArtifact, LeadershipArtifactKind
from runtime.workforce_orchestration.errors import (
    WorkforceOrchestrationConflict,
    WorkforceOrchestrationNotFound,
    WorkforceOrchestrationPolicyError,
)
from runtime.workforce_orchestration.models import (
    ARTIFACT_STATUS,
    EXECUTION_STATE,
    ORCHESTRATION_ACTIONS,
    ORCHESTRATION_CAPABILITIES,
    PILOT_STATUS,
    SOURCE_ORDER,
    MultiAgentOrchestrationArtifact,
    OrchestrationAuthority,
    OrchestrationDraft,
    OrchestrationSourceKind,
    OrchestrationWorkOrder,
    SourceBinding,
    artifact_id_for,
    source_set_digest,
)
from runtime.workforce_orchestration.persistence import FileOrchestrationArtifactStore
from runtime.workforce_orchestration.provider import OrchestrationPlanningProvider
from runtime.workforce_qa import FileQAArtifactStore, QAWorkArtifact
from runtime.workforce_security import FileSecurityArtifactStore, SecurityWorkArtifact


class MultiAgentOrchestrationService:
    """Plan governed coordination without executing agents or product operations."""

    def __init__(
        self,
        provider: OrchestrationPlanningProvider,
        leadership_store: FileLeadershipArtifactStore,
        architecture_store: FileArchitectureArtifactStore,
        engineering_store: FileEngineeringArtifactStore,
        qa_store: FileQAArtifactStore,
        security_store: FileSecurityArtifactStore,
        devops_store: FileDevOpsArtifactStore,
        documentation_store: FileDocumentationArtifactStore,
        store: FileOrchestrationArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(provider, OrchestrationPlanningProvider):
            raise TypeError("Orchestration provider does not implement the planning contract")
        expected = (
            (leadership_store, FileLeadershipArtifactStore, "leadership store"),
            (architecture_store, FileArchitectureArtifactStore, "architecture store"),
            (engineering_store, FileEngineeringArtifactStore, "Engineering store"),
            (qa_store, FileQAArtifactStore, "QA store"),
            (security_store, FileSecurityArtifactStore, "Security store"),
            (devops_store, FileDevOpsArtifactStore, "DevOps store"),
            (documentation_store, FileDocumentationArtifactStore, "Documentation store"),
            (store, FileOrchestrationArtifactStore, "orchestration store"),
        )
        for value, kind, label in expected:
            if not isinstance(value, kind):
                raise TypeError(f"Orchestration {label} is invalid")
        self._provider = provider
        self._leadership_store = leadership_store
        self._architecture_store = architecture_store
        self._engineering_store = engineering_store
        self._qa_store = qa_store
        self._security_store = security_store
        self._devops_store = devops_store
        self._documentation_store = documentation_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        work_order: OrchestrationWorkOrder,
        authority: OrchestrationAuthority,
        leadership_artifacts: tuple[LeadershipArtifact, ...],
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact,
        devops_artifact: DevOpsWorkArtifact,
        documentation_artifact: DocumentationWorkArtifact,
    ) -> MultiAgentOrchestrationArtifact:
        """Create or reopen one immutable exact-source orchestration artifact."""

        bindings = self._validate_sources(
            work_order,
            leadership_artifacts,
            architecture,
            engineering_artifacts,
            qa_artifact,
            security_artifact,
            devops_artifact,
            documentation_artifact,
        )
        binding_digest = source_set_digest(bindings)
        self._validate_authority(work_order, authority, binding_digest)
        try:
            existing = self._store.load(work_order.tenant_id, execution_id)
        except WorkforceOrchestrationNotFound:
            existing = None
        if existing is not None:
            if not (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.source_set_digest == binding_digest
                and existing.source_bindings == bindings
                and existing.provider_id == self._provider.provider_id
            ):
                raise WorkforceOrchestrationConflict(
                    "Orchestration execution conflicts with immutable persisted state"
                )
            return existing

        draft = self._provider.plan(work_order, authority, bindings)
        self._validate_draft(draft, bindings, authority)
        artifact = MultiAgentOrchestrationArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            provider_id=self._provider.provider_id,
            authority_digest=authority.digest,
            source_set_digest=binding_digest,
            source_bindings=bindings,
            capability_ids=ORCHESTRATION_CAPABILITIES,
            action_ids=ORCHESTRATION_ACTIONS,
            dependency_nodes=draft.dependency_nodes,
            parallel_waves=draft.parallel_waves,
            context_packages=draft.context_packages,
            handoffs=draft.handoffs,
            conflicts=draft.conflicts,
            escalations=draft.escalations,
            status_report=draft.status_report,
            provider_output_digest=draft.digest,
            generated_at=self._clock(),
            execution_state=EXECUTION_STATE,
            status=ARTIFACT_STATUS,
            pilot_status=PILOT_STATUS,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> MultiAgentOrchestrationArtifact:
        return self._store.load(tenant_id, execution_id)

    def _validate_sources(
        self,
        work_order: OrchestrationWorkOrder,
        leadership: tuple[LeadershipArtifact, ...],
        architecture: ArchitectureProposalArtifact,
        engineering: tuple[EngineeringWorkArtifact, ...],
        qa: QAWorkArtifact,
        security: SecurityWorkArtifact,
        devops: DevOpsWorkArtifact,
        documentation: DocumentationWorkArtifact,
    ) -> tuple[SourceBinding, ...]:
        if (
            not isinstance(work_order, OrchestrationWorkOrder)
            or not isinstance(leadership, tuple)
            or len(leadership) != 2
            or any(not isinstance(item, LeadershipArtifact) for item in leadership)
            or not isinstance(architecture, ArchitectureProposalArtifact)
            or not isinstance(engineering, tuple)
            or len(engineering) != 4
            or any(not isinstance(item, EngineeringWorkArtifact) for item in engineering)
            or not isinstance(qa, QAWorkArtifact)
            or not isinstance(security, SecurityWorkArtifact)
            or not isinstance(devops, DevOpsWorkArtifact)
            or not isinstance(documentation, DocumentationWorkArtifact)
        ):
            raise WorkforceOrchestrationPolicyError("Orchestration sources are invalid")
        ceo, product = leadership
        engineering_digests = tuple(item.digest for item in engineering)
        all_sources = (*leadership, architecture, *engineering, qa, security, devops, documentation)
        tenant_ids = {item.tenant_id for item in all_sources} | {work_order.tenant_id}
        opportunity_ids = {item.opportunity_id for item in all_sources} | {work_order.opportunity_id}
        pilots = {item.pilot_status for item in all_sources} | {work_order.pilot_status}
        if not (
            len(tenant_ids) == len(opportunity_ids) == len(pilots) == 1
            and pilots == {PILOT_STATUS}
            and ceo.kind is LeadershipArtifactKind.CEO_OPPORTUNITY_BRIEF
            and ceo.business_role is AgentRole.CEO
            and product.kind is LeadershipArtifactKind.PRODUCT_MANAGER_PLAN
            and product.business_role is AgentRole.PROJECT_MANAGER
            and product.upstream_artifact_digest == ceo.digest
            and tuple(item.digest for item in leadership) == work_order.leadership_artifact_digests
            and architecture.product_manager_artifact_digest == product.digest
            and architecture.digest == work_order.architecture_artifact_digest
            and tuple(item.business_role for item in engineering) == ENGINEERING_ROLES
            and engineering_digests == work_order.engineering_artifact_digests
            and all(item.architecture_artifact_digest == architecture.digest for item in engineering)
            and tuple(item.artifact_digest for item in qa.sources) == engineering_digests
            and qa.architecture_artifact_digest == architecture.digest
            and qa.digest == work_order.qa_artifact_digest
            and tuple(item.artifact_digest for item in security.sources) == engineering_digests
            and security.architecture_artifact_digest == architecture.digest
            and security.qa_artifact_digest == qa.digest
            and security.digest == work_order.security_artifact_digest
            and tuple(item.artifact_digest for item in devops.sources) == engineering_digests
            and devops.architecture_artifact_digest == architecture.digest
            and devops.qa_artifact_digest == qa.digest
            and devops.security_artifact_digest == security.digest
            and devops.digest == work_order.devops_artifact_digest
            and tuple(item.artifact_digest for item in documentation.sources) == engineering_digests
            and documentation.architecture_artifact_digest == architecture.digest
            and documentation.qa_artifact_digest == qa.digest
            and documentation.security_artifact_digest == security.digest
            and documentation.devops_artifact_digest == devops.digest
            and documentation.digest == work_order.documentation_artifact_digest
        ):
            raise WorkforceOrchestrationPolicyError(
                "Orchestration requires the exact Day 23-29 workforce source chain"
            )
        persisted = (
            all(self._leadership_store.load(item.tenant_id, item.execution_id) == item for item in leadership)
            and self._architecture_store.load(architecture.tenant_id, architecture.execution_id) == architecture
            and all(self._engineering_store.load(item.tenant_id, item.execution_id) == item for item in engineering)
            and self._qa_store.load(qa.tenant_id, qa.execution_id) == qa
            and self._security_store.load(security.tenant_id, security.execution_id) == security
            and self._devops_store.load(devops.tenant_id, devops.execution_id) == devops
            and self._documentation_store.load(documentation.tenant_id, documentation.execution_id) == documentation
        )
        if not persisted:
            raise WorkforceOrchestrationPolicyError(
                "Orchestration sources do not match persisted state"
            )
        artifact_records = (
            (ceo.artifact_id, ceo.digest, ceo.status),
            (product.artifact_id, product.digest, product.status),
            (architecture.artifact_id, architecture.digest, architecture.status),
            *((item.artifact_id, item.digest, item.status) for item in engineering),
            (qa.artifact_id, qa.digest, qa.status),
            (security.artifact_id, security.digest, security.status),
            (devops.artifact_id, devops.digest, devops.status),
            (documentation.artifact_id, documentation.digest, documentation.status),
        )
        return tuple(
            SourceBinding(kind, artifact_id, digest, status)
            for kind, (artifact_id, digest, status) in zip(
                SOURCE_ORDER, artifact_records, strict=True
            )
        )

    @staticmethod
    def _validate_authority(
        work_order: OrchestrationWorkOrder,
        authority: OrchestrationAuthority,
        binding_digest: str,
    ) -> None:
        if not isinstance(authority, OrchestrationAuthority):
            raise WorkforceOrchestrationPolicyError("Orchestration authority is invalid")
        if not (
            authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.work_order_digest == work_order.digest
            and authority.source_set_digest == binding_digest
            and authority.allowed_action_ids == ORCHESTRATION_ACTIONS
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
        ):
            raise WorkforceOrchestrationPolicyError(
                "Orchestration authority, source, assignment, tool, or time boundary does not match"
            )

    @staticmethod
    def _validate_draft(
        draft: OrchestrationDraft,
        bindings: tuple[SourceBinding, ...],
        authority: OrchestrationAuthority,
    ) -> None:
        if not isinstance(draft, OrchestrationDraft):
            raise WorkforceOrchestrationPolicyError("Orchestration provider draft is invalid")
        source_digests = {item.artifact_digest for item in bindings}
        node_ids = tuple(item.node_id for item in draft.dependency_nodes)
        if len(set(node_ids)) != len(node_ids):
            raise WorkforceOrchestrationPolicyError("Orchestration dependency nodes are duplicated")
        seen: set[str] = set()
        for node in draft.dependency_nodes:
            if not set(node.dependency_node_ids) <= seen:
                raise WorkforceOrchestrationPolicyError("Orchestration graph is not acyclic and ordered")
            if not set(node.source_artifact_digests) <= source_digests:
                raise WorkforceOrchestrationPolicyError("Orchestration node crossed its source boundary")
            seen.add(node.node_id)
        wave_nodes = tuple(node for wave in draft.parallel_waves[:-1] for node in wave.node_ids)
        if (
            tuple(wave.sequence for wave in draft.parallel_waves) != tuple(range(1, 10))
            or set(wave_nodes) != set(node_ids)
            or len(wave_nodes) != len(node_ids)
            or draft.parallel_waves[-1].node_ids != ("node-human-review",)
            or any(wave.max_parallelism > authority.max_parallel_workstreams for wave in draft.parallel_waves)
            or max(wave.max_parallelism for wave in draft.parallel_waves) < 2
        ):
            raise WorkforceOrchestrationPolicyError("Orchestration parallel-wave plan is invalid")
        context_targets = tuple(item.target_node_id for item in draft.context_packages)
        if context_targets != node_ids:
            raise WorkforceOrchestrationPolicyError("Orchestration context coverage is invalid")
        by_node = {item.node_id: item for item in draft.dependency_nodes}
        for context in draft.context_packages:
            if context.allowed_source_digests != by_node[context.target_node_id].source_artifact_digests:
                raise WorkforceOrchestrationPolicyError("Orchestration context source boundary drifted")
            if set(context.excluded_data_classes) != {
                "credentials", "secrets", "raw customer data", "local paths"
            }:
                raise WorkforceOrchestrationPolicyError("Orchestration context exclusions are incomplete")
        allowed_nodes = set(node_ids)
        for handoff in draft.handoffs:
            if not set(handoff.source_node_ids + handoff.target_node_ids) <= allowed_nodes:
                raise WorkforceOrchestrationPolicyError("Orchestration handoff references an unknown node")
            if not set(handoff.artifact_digests) <= source_digests:
                raise WorkforceOrchestrationPolicyError("Orchestration handoff crossed its source boundary")
        if any(not set(item.participant_node_ids) <= allowed_nodes for item in draft.conflicts):
            raise WorkforceOrchestrationPolicyError("Orchestration conflict route is invalid")
        if any(not set(item.required_evidence_digests) <= source_digests for item in draft.escalations):
            raise WorkforceOrchestrationPolicyError("Orchestration escalation evidence is invalid")
