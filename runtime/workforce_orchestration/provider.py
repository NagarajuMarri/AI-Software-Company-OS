"""Provider-neutral planning contract for governed Day 30 orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runtime.workforce_orchestration.models import (
    CONFLICT_STATE,
    ESCALATION_STATE,
    EXECUTION_STATE,
    HANDOFF_STATE,
    WORK_STATUS,
    ConflictRoute,
    ContextPackage,
    DependencyNode,
    EscalationRecord,
    HandoffRecord,
    OrchestrationAuthority,
    OrchestrationDraft,
    OrchestrationSourceKind,
    OrchestrationStatusReport,
    OrchestrationWorkOrder,
    ParallelWave,
    SourceBinding,
    context_digest,
)


@runtime_checkable
class OrchestrationPlanningProvider(Protocol):
    """Replaceable planning boundary with no tools or operational effects."""

    @property
    def provider_id(self) -> str: ...

    def plan(
        self,
        work_order: OrchestrationWorkOrder,
        authority: OrchestrationAuthority,
        sources: tuple[SourceBinding, ...],
    ) -> OrchestrationDraft: ...


class DeterministicOrchestrationProvider:
    """Deterministic reference provider used for founder-safe Day 30 verification."""

    def __init__(self, provider_id: str = "deterministic-workforce-orchestration-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("Orchestration provider ID is invalid")
        self._provider_id = provider_id
        self.execution_count = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def plan(
        self,
        work_order: OrchestrationWorkOrder,
        authority: OrchestrationAuthority,
        sources: tuple[SourceBinding, ...],
    ) -> OrchestrationDraft:
        if not isinstance(work_order, OrchestrationWorkOrder):
            raise ValueError("Orchestration provider work order is invalid")
        if not isinstance(authority, OrchestrationAuthority):
            raise ValueError("Orchestration provider authority is invalid")
        if not isinstance(sources, tuple) or any(not isinstance(item, SourceBinding) for item in sources):
            raise ValueError("Orchestration provider sources are invalid")
        self.execution_count += 1
        return _draft(sources, authority.max_parallel_workstreams)


def _draft(sources: tuple[SourceBinding, ...], max_parallel: int) -> OrchestrationDraft:
    by_kind = {item.kind: item.artifact_digest for item in sources}
    if len(by_kind) != 11:
        raise ValueError("Orchestration provider requires eleven exact sources")
    ceo = by_kind[OrchestrationSourceKind.CEO]
    pm = by_kind[OrchestrationSourceKind.PRODUCT_MANAGER]
    architecture = by_kind[OrchestrationSourceKind.ARCHITECTURE]
    backend = by_kind[OrchestrationSourceKind.BACKEND_ENGINEERING]
    frontend = by_kind[OrchestrationSourceKind.FRONTEND_ENGINEERING]
    ai = by_kind[OrchestrationSourceKind.AI_ENGINEERING]
    data = by_kind[OrchestrationSourceKind.DATA_ENGINEERING]
    qa = by_kind[OrchestrationSourceKind.QA]
    security = by_kind[OrchestrationSourceKind.SECURITY]
    devops = by_kind[OrchestrationSourceKind.DEVOPS]
    documentation = by_kind[OrchestrationSourceKind.DOCUMENTATION]
    engineering = (backend, frontend, ai, data)

    nodes = (
        _node("node-ceo", "CEO", "Frame the bounded opportunity", (), (ceo,)),
        _node("node-product-manager", "Product Manager", "Clarify scope and plan", ("node-ceo",), (ceo, pm)),
        _node("node-architecture", "Software Architect", "Propose source-bound architecture", ("node-product-manager",), (pm, architecture)),
        _node("node-backend", "Backend Engineer", "Prepare Backend implementation instructions", ("node-architecture",), (architecture, backend)),
        _node("node-frontend", "Frontend Engineer", "Prepare Frontend implementation instructions", ("node-architecture",), (architecture, frontend)),
        _node("node-ai", "AI Engineer", "Prepare AI implementation instructions", ("node-architecture",), (architecture, ai)),
        _node("node-data", "Data Engineer", "Prepare Data implementation instructions", ("node-architecture",), (architecture, data)),
        _node("node-qa", "QA Engineer", "Prepare exact-source test specifications", ("node-backend", "node-frontend", "node-ai", "node-data"), (architecture, *engineering, qa)),
        _node("node-security", "Security Engineer", "Prepare threat and check specifications", ("node-qa",), (architecture, *engineering, qa, security)),
        _node("node-devops", "DevOps Engineer", "Prepare non-production operational plans", ("node-security",), (architecture, *engineering, qa, security, devops)),
        _node("node-documentation", "Documentation Engineer", "Prepare source-validated documentation", ("node-devops",), (architecture, *engineering, qa, security, devops, documentation)),
    )
    waves = (
        _wave(1, ("node-ceo",)),
        _wave(2, ("node-product-manager",)),
        _wave(3, ("node-architecture",)),
        _wave(4, ("node-backend", "node-frontend", "node-ai", "node-data"), min(4, max_parallel)),
        _wave(5, ("node-qa",)),
        _wave(6, ("node-security",)),
        _wave(7, ("node-devops",)),
        _wave(8, ("node-documentation",)),
        ParallelWave(
            wave_id="wave-9-human-gate",
            sequence=9,
            node_ids=("node-human-review",),
            entry_checks=("All draft handoffs and escalation routes are complete",),
            exit_checks=("A human explicitly authorizes any later workspace execution",),
            max_parallelism=1,
            execution_state=EXECUTION_STATE,
        ),
    )
    fields = ("artifact_id", "artifact_digest", "status", "bounded_summary")
    excluded = ("credentials", "secrets", "raw customer data", "local paths")
    contexts = tuple(
        ContextPackage(
            context_id=f"context-{node.node_id.removeprefix('node-')}",
            target_node_id=node.node_id,
            allowed_source_digests=node.source_artifact_digests,
            included_fields=fields,
            excluded_data_classes=excluded,
            context_digest=context_digest(node.node_id, node.source_artifact_digests, fields),
        )
        for node in nodes
    )
    handoffs = (
        _handoff("handoff-ceo-product", ("node-ceo",), ("node-product-manager",), (ceo,)),
        _handoff("handoff-product-architecture", ("node-product-manager",), ("node-architecture",), (pm,)),
        _handoff("handoff-architecture-engineering", ("node-architecture",), ("node-backend", "node-frontend", "node-ai", "node-data"), (architecture,)),
        _handoff("handoff-engineering-qa", ("node-backend", "node-frontend", "node-ai", "node-data"), ("node-qa",), engineering),
        _handoff("handoff-qa-security", ("node-qa",), ("node-security",), (*engineering, qa)),
        _handoff("handoff-security-devops", ("node-security",), ("node-devops",), (qa, security)),
        _handoff("handoff-devops-documentation", ("node-devops",), ("node-documentation",), (security, devops)),
    )
    conflicts = (
        ConflictRoute(
            conflict_id="conflict-interface-ownership",
            participant_node_ids=("node-backend", "node-frontend", "node-ai", "node-data"),
            subject="Conflicting interface ownership or incompatible integration assumptions",
            detection_rule="Two Engineering artifacts claim the same interface or disagree with the exact Architecture source",
            resolution_owner="Software Architect with human review",
            resolution_policy="Block affected downstream nodes, preserve both claims, and request one source-bound architecture decision",
            downstream_blocked=True,
            state=CONFLICT_STATE,
        ),
        ConflictRoute(
            conflict_id="conflict-quality-implementation",
            participant_node_ids=("node-qa", "node-backend", "node-frontend", "node-ai", "node-data"),
            subject="QA evidence conflicts with an Engineering implementation specification",
            detection_rule="A QA acceptance or defect record cannot be reconciled with its exact Engineering source",
            resolution_owner="Responsible Engineering role and QA Engineer under human review",
            resolution_policy="Return the bounded issue to the owning Engineering node and retain QA as an independent gate",
            downstream_blocked=True,
            state=CONFLICT_STATE,
        ),
        ConflictRoute(
            conflict_id="conflict-security-release",
            participant_node_ids=("node-security", "node-devops", "node-documentation"),
            subject="Security constraints conflict with operational or release preparation",
            detection_rule="A critical Security finding or boundary is absent from DevOps or release documentation",
            resolution_owner="Human Security and release authorities",
            resolution_policy="Block operational progression; no agent may accept risk or weaken the Security source",
            downstream_blocked=True,
            state=CONFLICT_STATE,
        ),
    )
    escalations = (
        _escalation("escalation-architecture-drift", "Architecture digest or interface ownership changes after Engineering planning", "Founder and Architecture authority", (architecture, *engineering)),
        _escalation("escalation-security-risk", "A Security conflict requires risk acceptance, remediation priority, or scope change", "Human Security risk owner and founder", (security, qa)),
        _escalation("escalation-release-gate", "Deployment, release, customer publication, or product workspace execution is requested", "Founder release authority", (devops, documentation)),
    )
    status = OrchestrationStatusReport(
        state=WORK_STATUS,
        completed_items=(
            "Bound eleven exact persisted workforce sources in canonical order",
            "Planned nine dependency waves with four Engineering workstreams in parallel",
            "Prepared bounded context packages and seven draft handoffs",
            "Prepared three fail-closed conflict routes and three human escalation records",
        ),
        next_actions=(
            "Human-review the orchestration graph, context boundaries, conflicts, and escalations",
            "Authorize Day 31 isolated product workspace separately after founder acceptance",
        ),
        blockers=("No isolated product workspace or product-execution authority exists",),
        escalations=("Any source drift, unresolved conflict, risk acceptance, deployment, or release request requires a human decision",),
    )
    return OrchestrationDraft(nodes, waves, contexts, handoffs, conflicts, escalations, status)


def _node(node_id: str, owner: str, objective: str, dependencies: tuple[str, ...], digests: tuple[str, ...]) -> DependencyNode:
    return DependencyNode(node_id, owner, objective, dependencies, digests, EXECUTION_STATE)


def _wave(sequence: int, nodes: tuple[str, ...], max_parallelism: int | None = None) -> ParallelWave:
    return ParallelWave(
        wave_id=f"wave-{sequence}",
        sequence=sequence,
        node_ids=nodes,
        entry_checks=("Every dependency source digest is exact and persisted",),
        exit_checks=("Draft output remains within role and authority boundaries",),
        max_parallelism=len(nodes) if max_parallelism is None else max_parallelism,
        execution_state=EXECUTION_STATE,
    )


def _handoff(
    handoff_id: str,
    sources: tuple[str, ...],
    targets: tuple[str, ...],
    digests: tuple[str, ...],
) -> HandoffRecord:
    return HandoffRecord(
        handoff_id=handoff_id,
        source_node_ids=sources,
        target_node_ids=targets,
        artifact_digests=digests,
        acceptance_checks=(
            "Target receives only the allowlisted exact-source context",
            "Handoff remains draft and is not dispatched to a workspace or external channel",
        ),
        state=HANDOFF_STATE,
    )


def _escalation(
    escalation_id: str,
    trigger: str,
    owner: str,
    digests: tuple[str, ...],
) -> EscalationRecord:
    return EscalationRecord(
        escalation_id=escalation_id,
        trigger=trigger,
        human_owner=owner,
        required_evidence_digests=digests,
        permitted_decisions=("APPROVE_EXACT_BOUNDED_CHANGE", "REQUEST_REVISION", "REJECT"),
        state=ESCALATION_STATE,
    )
