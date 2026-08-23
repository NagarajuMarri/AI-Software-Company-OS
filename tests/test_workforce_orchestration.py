from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import stat

import pytest

from runtime.workforce_architecture import FileArchitectureArtifactStore
from runtime.workforce_devops import FileDevOpsArtifactStore
from runtime.workforce_documentation import FileDocumentationArtifactStore
from runtime.workforce_engineering import FileEngineeringArtifactStore
from runtime.workforce_leadership import FileLeadershipArtifactStore
from runtime.workforce_orchestration import (
    ARTIFACT_STATUS,
    CONFLICT_STATE,
    ESCALATION_STATE,
    EXECUTION_STATE,
    HANDOFF_STATE,
    ORCHESTRATION_ACTIONS,
    ORCHESTRATION_CAPABILITIES,
    PILOT_STATUS,
    WORK_STATUS,
    DeterministicOrchestrationProvider,
    FileOrchestrationArtifactStore,
    MultiAgentOrchestrationService,
    OrchestrationAuthority,
    OrchestrationDraft,
    OrchestrationSourceKind,
    OrchestrationWorkOrder,
    SourceBinding,
    WorkforceOrchestrationConflict,
    WorkforceOrchestrationCorrupt,
    WorkforceOrchestrationPolicyError,
    source_set_digest,
)
from runtime.workforce_qa import FileQAArtifactStore
from runtime.workforce_security import FileSecurityArtifactStore
from tests.test_workforce_documentation import _run_documentation
from tests.test_workforce_leadership import NOW


def _sources(tmp_path: Path):
    run = _run_documentation(tmp_path)
    _, _, intake, architecture, engineering, qa, security, devops, _, _, _, documentation = run
    leadership_store = FileLeadershipArtifactStore(tmp_path / "leadership-state")
    leadership = (
        leadership_store.load(intake.tenant_id, "execution-ceo-1"),
        leadership_store.load(intake.tenant_id, "execution-product-manager-1"),
    )
    return leadership, architecture, engineering, qa, security, devops, documentation


def _bindings(leadership, architecture, engineering, qa, security, devops, documentation):
    artifacts = (*leadership, architecture, *engineering, qa, security, devops, documentation)
    return tuple(
        SourceBinding(kind, item.artifact_id, item.digest, item.status)
        for kind, item in zip(tuple(OrchestrationSourceKind), artifacts, strict=True)
    )


def _work_order(leadership, architecture, engineering, qa, security, devops, documentation, **changes):
    values = {
        "work_order_id": "work-order-multi-agent-orchestration-1",
        "tenant_id": architecture.tenant_id,
        "opportunity_id": architecture.opportunity_id,
        "assignment_id": "assignment-multi-agent-orchestration-1",
        "leadership_artifact_digests": tuple(item.digest for item in leadership),
        "architecture_artifact_digest": architecture.digest,
        "engineering_artifact_digests": tuple(item.digest for item in engineering),
        "qa_artifact_digest": qa.digest,
        "security_artifact_digest": security.digest,
        "devops_artifact_digest": devops.digest,
        "documentation_artifact_digest": documentation.digest,
        "objectives": (
            "Plan exact dependency order",
            "Identify safe parallel work",
            "Share bounded source context",
            "Prepare explicit handoffs",
            "Route conflicts without silent overwrite",
            "Escalate human decisions without self-approval",
        ),
        "acceptance_checks": (
            "All eleven persisted workforce sources are exact and ordered",
            "The dependency graph is acyclic and complete",
            "Four Engineering roles share one bounded parallel wave",
            "Every context package has explicit source and exclusion boundaries",
            "Every handoff is draft and undispatched",
            "Conflicts block affected downstream work",
            "Escalations require a named human owner",
            "No workspace, repository, deployment, release, or pilot authority exists",
        ),
        "constraints": (
            "No tools, workspace, filesystem, repository, command, network, credentials, or live provider",
            "No agent execution, approval, risk acceptance, merge, deployment, release, billing, or pilot selection",
        ),
        "issued_at": NOW + timedelta(minutes=50),
    }
    values.update(changes)
    return OrchestrationWorkOrder(**values)


def _authority(order, bindings, **changes):
    values = {
        "authority_id": "authority-multi-agent-orchestration-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "work_order_digest": order.digest,
        "source_set_digest": source_set_digest(bindings),
        "allowed_action_ids": ORCHESTRATION_ACTIONS,
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=4),
        "max_parallel_workstreams": 4,
        "max_tool_calls": 0,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return OrchestrationAuthority(**values)


def _service(tmp_path: Path, provider=None):
    selected = provider or DeterministicOrchestrationProvider()
    service = MultiAgentOrchestrationService(
        selected,
        FileLeadershipArtifactStore(tmp_path / "leadership-state"),
        FileArchitectureArtifactStore(tmp_path / "architecture-state"),
        FileEngineeringArtifactStore(tmp_path / "engineering-state"),
        FileQAArtifactStore(tmp_path / "qa-state"),
        FileSecurityArtifactStore(tmp_path / "security-state"),
        FileDevOpsArtifactStore(tmp_path / "devops-state"),
        FileDocumentationArtifactStore(tmp_path / "documentation-state"),
        FileOrchestrationArtifactStore(tmp_path / "orchestration-state"),
        clock=lambda: NOW + timedelta(minutes=52),
    )
    return service, selected


def _run_orchestration(tmp_path: Path, *, provider=None):
    sources = _sources(tmp_path)
    bindings = _bindings(*sources)
    order = _work_order(*sources)
    authority = _authority(order, bindings)
    service, selected = _service(tmp_path, provider)
    artifact = service.run(
        execution_id="execution-multi-agent-orchestration-1",
        work_order=order,
        authority=authority,
        leadership_artifacts=sources[0],
        architecture=sources[1],
        engineering_artifacts=sources[2],
        qa_artifact=sources[3],
        security_artifact=sources[4],
        devops_artifact=sources[5],
        documentation_artifact=sources[6],
    )
    return service, selected, sources, bindings, order, authority, artifact


def test_orchestration_plans_dependencies_parallel_context_and_handoffs(tmp_path: Path) -> None:
    service, provider, _, bindings, _, _, artifact = _run_orchestration(tmp_path)
    assert provider.execution_count == 1
    assert artifact.source_bindings == bindings
    assert tuple(item.kind for item in artifact.source_bindings) == tuple(OrchestrationSourceKind)
    assert len(artifact.dependency_nodes) == 11
    assert len(artifact.parallel_waves) == 9
    engineering_wave = artifact.parallel_waves[3]
    assert engineering_wave.node_ids == ("node-backend", "node-frontend", "node-ai", "node-data")
    assert engineering_wave.max_parallelism == 4
    assert len(artifact.context_packages) == 11
    assert len(artifact.handoffs) == 7
    assert len(artifact.conflicts) == len(artifact.escalations) == 3
    assert artifact.status_report.state == WORK_STATUS
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_orchestration_has_zero_tools_and_no_operational_execution(tmp_path: Path) -> None:
    *_, authority, artifact = _run_orchestration(tmp_path)[-2:]
    assert authority.allowed_tool_ids == () and authority.max_tool_calls == 0
    assert authority.live_provider_allowed is False
    assert artifact.capability_ids == ORCHESTRATION_CAPABILITIES
    assert artifact.action_ids == ORCHESTRATION_ACTIONS
    assert artifact.execution_state == EXECUTION_STATE
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.dependency_nodes)
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.parallel_waves)
    assert all(item.state == HANDOFF_STATE for item in artifact.handoffs)
    assert all(item.state == CONFLICT_STATE and item.downstream_blocked for item in artifact.conflicts)
    assert all(item.state == ESCALATION_STATE for item in artifact.escalations)
    for forbidden in ("WRITE_PRODUCT_REPOSITORY", "RUN_COMMAND", "COMMIT", "MERGE", "DEPLOY", "RELEASE", "APPROVE", "SELECT_PILOT_PRODUCT"):
        assert forbidden not in artifact.action_ids


def test_exact_retry_and_restart_do_not_repeat_provider_effect(tmp_path: Path) -> None:
    service, provider, sources, _, order, authority, expected = _run_orchestration(tmp_path)
    kwargs = dict(
        execution_id=expected.execution_id,
        work_order=order,
        authority=authority,
        leadership_artifacts=sources[0],
        architecture=sources[1],
        engineering_artifacts=sources[2],
        qa_artifact=sources[3],
        security_artifact=sources[4],
        devops_artifact=sources[5],
        documentation_artifact=sources[6],
    )
    again = service.run(**kwargs)
    restarted, restarted_provider = _service(tmp_path)
    reopened = restarted.run(**kwargs)
    assert again == reopened == expected
    assert provider.execution_count == 1 and restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "change",
    [
        {"leadership_artifact_digests": ("0" * 64, "1" * 64)},
        {"architecture_artifact_digest": "2" * 64},
        {"engineering_artifact_digests": ("3" * 64, "4" * 64, "5" * 64, "6" * 64)},
        {"qa_artifact_digest": "7" * 64},
        {"security_artifact_digest": "8" * 64},
        {"devops_artifact_digest": "9" * 64},
        {"documentation_artifact_digest": "a" * 64},
    ],
)
def test_source_substitution_fails_before_provider_activity(tmp_path: Path, change) -> None:
    sources = _sources(tmp_path)
    bindings = _bindings(*sources)
    order = _work_order(*sources, **change)
    authority = _authority(order, bindings)
    service, provider = _service(tmp_path)
    with pytest.raises(WorkforceOrchestrationPolicyError):
        service.run(
            execution_id="execution-invalid-source",
            work_order=order,
            authority=authority,
            leadership_artifacts=sources[0],
            architecture=sources[1],
            engineering_artifacts=sources[2],
            qa_artifact=sources[3],
            security_artifact=sources[4],
            devops_artifact=sources[5],
            documentation_artifact=sources[6],
        )
    assert provider.execution_count == 0


def test_authority_source_or_assignment_drift_fails_closed(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    bindings = _bindings(*sources)
    order = _work_order(*sources)
    valid = _authority(order, bindings)
    service, provider = _service(tmp_path)
    kwargs = dict(
        execution_id="execution-invalid-authority", work_order=order,
        leadership_artifacts=sources[0], architecture=sources[1],
        engineering_artifacts=sources[2], qa_artifact=sources[3],
        security_artifact=sources[4], devops_artifact=sources[5],
        documentation_artifact=sources[6],
    )
    for authority in (
        replace(valid, source_set_digest="b" * 64),
        replace(valid, assignment_id="assignment-wrong"),
        replace(valid, work_order_digest="c" * 64),
    ):
        with pytest.raises(WorkforceOrchestrationPolicyError):
            service.run(authority=authority, **kwargs)
    assert provider.execution_count == 0


def test_immutable_execution_rejects_changed_work_order(tmp_path: Path) -> None:
    service, _, sources, bindings, order, _, artifact = _run_orchestration(tmp_path)
    changed = replace(order, objectives=(*order.objectives[:-1], "Different escalation objective"))
    authority = _authority(changed, bindings)
    with pytest.raises(WorkforceOrchestrationConflict):
        service.run(
            execution_id=artifact.execution_id, work_order=changed, authority=authority,
            leadership_artifacts=sources[0], architecture=sources[1],
            engineering_artifacts=sources[2], qa_artifact=sources[3],
            security_artifact=sources[4], devops_artifact=sources[5],
            documentation_artifact=sources[6],
        )


def test_persistence_is_mode_0600_closed_and_tamper_evident(tmp_path: Path) -> None:
    service, _, _, _, _, _, artifact = _run_orchestration(tmp_path)
    directory = tmp_path / "orchestration-state" / artifact.tenant_id / artifact.execution_id
    path = directory / "multi-agent-orchestration-v1.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = json.loads(path.read_text())
    envelope["record"]["status"] = "EXECUTED"
    path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    os.chmod(path, 0o600)
    with pytest.raises(WorkforceOrchestrationCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)


def test_persistence_rejects_unknown_entries_and_unsafe_permissions(tmp_path: Path) -> None:
    service, _, _, _, _, _, artifact = _run_orchestration(tmp_path)
    directory = tmp_path / "orchestration-state" / artifact.tenant_id / artifact.execution_id
    path = directory / "multi-agent-orchestration-v1.json"
    (directory / "unexpected.txt").write_text("unsafe")
    with pytest.raises(WorkforceOrchestrationCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)
    (directory / "unexpected.txt").unlink()
    os.chmod(path, 0o644)
    with pytest.raises(WorkforceOrchestrationCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)


def test_path_escape_is_rejected(tmp_path: Path) -> None:
    store = FileOrchestrationArtifactStore(tmp_path / "state")
    with pytest.raises(WorkforceOrchestrationCorrupt):
        store.load("../tenant", "execution")


class _CrossSourceProvider(DeterministicOrchestrationProvider):
    def plan(self, work_order, authority, sources):
        draft = super().plan(work_order, authority, sources)
        context = replace(
            draft.context_packages[0],
            allowed_source_digests=(draft.context_packages[0].allowed_source_digests[0], sources[-1].artifact_digest),
        )
        return OrchestrationDraft(
            draft.dependency_nodes,
            draft.parallel_waves,
            (context, *draft.context_packages[1:]),
            draft.handoffs,
            draft.conflicts,
            draft.escalations,
            draft.status_report,
        )


def test_provider_cannot_expand_context_source_boundary(tmp_path: Path) -> None:
    sources = _sources(tmp_path)
    bindings = _bindings(*sources)
    order = _work_order(*sources)
    authority = _authority(order, bindings)
    service, provider = _service(tmp_path, _CrossSourceProvider())
    with pytest.raises(WorkforceOrchestrationPolicyError):
        service.run(
            execution_id="execution-cross-source", work_order=order, authority=authority,
            leadership_artifacts=sources[0], architecture=sources[1],
            engineering_artifacts=sources[2], qa_artifact=sources[3],
            security_artifact=sources[4], devops_artifact=sources[5],
            documentation_artifact=sources[6],
        )
    assert provider.execution_count == 1
