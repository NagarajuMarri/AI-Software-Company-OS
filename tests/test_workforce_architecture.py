from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from runtime.agents import AgentRole
from runtime.digital_twin import (
    ContextValue,
    DelegatedAuthority,
    DigitalTwinDefinition,
    DigitalTwinProviderRegistry,
    DigitalTwinRuntime,
    DigitalTwinToolRegistry,
    FileDigitalTwinExecutionStore,
    ProviderExecutionResult,
    USE_ASSIGNED_TOOL,
)
from runtime.workforce_architecture import (
    ADR_STATUS,
    ARCHITECT_ACTION_IDS,
    ARCHITECT_CAPABILITY_IDS,
    ARTIFACT_STATUS,
    ArchitectureDecisionDraft,
    ArchitectureWorkforceCorrupt,
    ArchitectureWorkforcePolicyError,
    ArchitectureWorkforceService,
    FileArchitectureArtifactStore,
    PILOT_STATUS,
    RECOMMENDATION_STATUS,
    SoftwareArchitectProvider,
    WORK_STATUS,
    architecture_objective,
)
from runtime.workforce_leadership import FileLeadershipArtifactStore
from tests.test_workforce_leadership import NOW, _run_both


def _architect_twin(**changes) -> DigitalTwinDefinition:
    values = {
        "twin_id": "twin-software-architect-1",
        "display_name": "Bounded Software Architect",
        "business_role": AgentRole.SOFTWARE_ARCHITECT,
        "provider_id": "deterministic-architect-v1",
        "capability_ids": ARCHITECT_CAPABILITY_IDS,
        "approved_tool_ids": (),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _architect_authority(
    objective: str,
    *,
    twin_id: str = "twin-software-architect-1",
    assignment_id: str = "assignment-software-architect-1",
    **changes,
) -> DelegatedAuthority:
    values = {
        "authority_id": f"authority-{assignment_id}",
        "issuer_id": "founder-module-approval",
        "tenant_id": "tenant-verification",
        "assignment_id": assignment_id,
        "twin_id": twin_id,
        "business_role": AgentRole.SOFTWARE_ARCHITECT,
        "objective_digest": hashlib.sha256(objective.encode()).hexdigest(),
        "allowed_action_ids": ARCHITECT_ACTION_IDS,
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=2),
        "max_tool_calls": 0,
        "max_output_bytes": 64_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _architecture_service(
    tmp_path: Path,
    *,
    provider: SoftwareArchitectProvider | None = None,
) -> tuple[ArchitectureWorkforceService, SoftwareArchitectProvider]:
    selected = provider or SoftwareArchitectProvider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected,)),
        DigitalTwinToolRegistry(()),
        FileDigitalTwinExecutionStore(tmp_path / "architecture-digital-twin-state"),
        clock=lambda: NOW + timedelta(minutes=4),
    )
    service = ArchitectureWorkforceService(
        runtime,
        selected,
        FileLeadershipArtifactStore(tmp_path / "leadership-state"),
        FileArchitectureArtifactStore(tmp_path / "architecture-state"),
        clock=lambda: NOW + timedelta(minutes=3),
    )
    return service, selected


def _run_architect(tmp_path: Path):
    leadership = _run_both(tmp_path)
    intake = leadership[2]
    product_manager = leadership[8]
    twin = _architect_twin()
    authority = _architect_authority(
        architecture_objective(intake, product_manager),
        twin_id=twin.twin_id,
    )
    service, provider = _architecture_service(tmp_path)
    artifact = service.run(
        execution_id="execution-software-architect-1",
        twin=twin,
        authority=authority,
        intake=intake,
        product_manager_artifact=product_manager,
    )
    return service, provider, intake, product_manager, twin, authority, artifact


def test_software_architect_produces_typed_draft_from_exact_pm_plan(
    tmp_path: Path,
) -> None:
    service, provider, intake, product_manager, _, _, artifact = _run_architect(
        tmp_path
    )

    assert provider.execution_count == 1
    assert artifact.business_role is AgentRole.SOFTWARE_ARCHITECT
    assert artifact.opportunity_digest == intake.digest
    assert artifact.product_manager_artifact_digest == product_manager.digest
    assert len(artifact.components) == 5
    assert len(artifact.technology_recommendations) == 4
    assert all(item.status == RECOMMENDATION_STATUS for item in artifact.technology_recommendations)
    assert len(artifact.adr_drafts) == 2
    assert all(
        item.status == ADR_STATUS and item.human_approval_required
        for item in artifact.adr_drafts
    )
    assert len(artifact.technical_risks) == 3
    assert artifact.status_report.state == WORK_STATUS
    assert artifact.status_report.blockers == ("Human architecture approval is pending",)
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pilot_status == PILOT_STATUS
    assert service.get(intake.tenant_id, artifact.execution_id) == artifact


def test_architect_role_has_no_tools_or_engineering_approval_authority(
    tmp_path: Path,
) -> None:
    _, _, _, _, twin, authority, artifact = _run_architect(tmp_path)

    assert twin.capability_ids == ARCHITECT_CAPABILITY_IDS
    assert twin.approved_tool_ids == authority.allowed_tool_ids == ()
    assert authority.allowed_action_ids == ARCHITECT_ACTION_IDS
    assert authority.max_tool_calls == 0
    assert authority.live_provider_allowed is False
    for forbidden in (
        "APPROVE_ARCHITECTURE",
        "CREATE_ENGINEERING_TASKS",
        "WRITE_PRODUCT_REPOSITORY",
        "MERGE",
        "DEPLOY",
        "RELEASE",
        "SELECT_PILOT_PRODUCT",
    ):
        assert forbidden not in authority.allowed_action_ids
    assert all(item.status == "PROPOSED" for item in artifact.adr_drafts)


def test_exact_retry_and_restart_do_not_repeat_architect_provider_effect(
    tmp_path: Path,
) -> None:
    service, provider, intake, product_manager, twin, authority, artifact = _run_architect(
        tmp_path
    )
    assert service.run(
        execution_id=artifact.execution_id,
        twin=twin,
        authority=authority,
        intake=intake,
        product_manager_artifact=product_manager,
    ) == artifact
    assert provider.execution_count == 1

    restarted_provider = SoftwareArchitectProvider()
    restarted, _ = _architecture_service(tmp_path, provider=restarted_provider)
    assert restarted.run(
        execution_id=artifact.execution_id,
        twin=twin,
        authority=authority,
        intake=intake,
        product_manager_artifact=product_manager,
    ) == artifact
    assert restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "allowed_action_ids",
    [
        ARCHITECT_ACTION_IDS[:-1],
        ARCHITECT_ACTION_IDS + ("APPROVE_ARCHITECTURE",),
        tuple(reversed(ARCHITECT_ACTION_IDS)),
    ],
)
def test_architect_requires_exact_action_profile_before_provider_effect(
    tmp_path: Path,
    allowed_action_ids: tuple[str, ...],
) -> None:
    leadership = _run_both(tmp_path)
    intake, product_manager = leadership[2], leadership[8]
    twin = _architect_twin()
    authority = _architect_authority(
        architecture_objective(intake, product_manager),
        allowed_action_ids=allowed_action_ids,
    )
    service, provider = _architecture_service(tmp_path)

    with pytest.raises(ArchitectureWorkforcePolicyError, match="boundary does not match"):
        service.run(
            execution_id="execution-invalid-actions",
            twin=twin,
            authority=authority,
            intake=intake,
            product_manager_artifact=product_manager,
        )
    assert provider.execution_count == 0


def test_wrong_capability_tenant_live_and_tool_profiles_fail_closed(
    tmp_path: Path,
) -> None:
    leadership = _run_both(tmp_path)
    intake, product_manager = leadership[2], leadership[8]
    objective = architecture_objective(intake, product_manager)
    twin = _architect_twin()
    base = _architect_authority(objective)
    service, provider = _architecture_service(tmp_path)
    candidates = (
        (_architect_twin(capability_ids=("status-reporting",)), base),
        (twin, replace(base, tenant_id="other-tenant")),
        (twin, replace(base, live_provider_allowed=True)),
        (
            _architect_twin(approved_tool_ids=("repository.write",)),
            replace(
                base,
                allowed_action_ids=ARCHITECT_ACTION_IDS + (USE_ASSIGNED_TOOL,),
                allowed_tool_ids=("repository.write",),
                max_tool_calls=1,
            ),
        ),
    )
    for index, (selected_twin, authority) in enumerate(candidates, start=1):
        with pytest.raises(ArchitectureWorkforcePolicyError):
            service.run(
                execution_id=f"execution-invalid-profile-{index}",
                twin=selected_twin,
                authority=authority,
                intake=intake,
                product_manager_artifact=product_manager,
            )
    assert provider.execution_count == 0


def test_architect_requires_exact_persisted_product_manager_handoff(
    tmp_path: Path,
) -> None:
    leadership = _run_both(tmp_path)
    intake, product_manager = leadership[2], leadership[8]
    twin = _architect_twin()
    changed = replace(product_manager, summary="Changed after persistence")
    authority = _architect_authority(architecture_objective(intake, changed))
    service, provider = _architecture_service(tmp_path)

    with pytest.raises(ArchitectureWorkforcePolicyError, match="persisted"):
        service.run(
            execution_id="execution-changed-source",
            twin=twin,
            authority=authority,
            intake=intake,
            product_manager_artifact=changed,
        )
    other_intake = replace(intake, opportunity_id="another-opportunity")
    with pytest.raises(ArchitectureWorkforcePolicyError, match="exact Product Manager"):
        service.run(
            execution_id="execution-cross-opportunity",
            twin=twin,
            authority=authority,
            intake=other_intake,
            product_manager_artifact=product_manager,
        )
    assert provider.execution_count == 0


def test_unknown_provider_output_is_rejected_and_not_persisted(tmp_path: Path) -> None:
    leadership = _run_both(tmp_path)
    intake, product_manager = leadership[2], leadership[8]
    twin = _architect_twin()
    authority = _architect_authority(architecture_objective(intake, product_manager))
    provider = SoftwareArchitectProvider()
    original = provider.render

    def invalid(request):
        result = original(request)
        return ProviderExecutionResult(
            result.execution_id,
            result.provider_id,
            result.request_digest,
            result.status,
            result.summary,
            result.output + (ContextValue("unknown_output", "not allowed"),),
        )

    provider.render = invalid
    service, _ = _architecture_service(tmp_path, provider=provider)
    with pytest.raises(ArchitectureWorkforcePolicyError, match="not closed"):
        service.run(
            execution_id="execution-invalid-output",
            twin=twin,
            authority=authority,
            intake=intake,
            product_manager_artifact=product_manager,
        )
    with pytest.raises(Exception):
        service.get(intake.tenant_id, "execution-invalid-output")


def test_architecture_models_cannot_accept_adr_or_select_pilot(tmp_path: Path) -> None:
    _, _, _, _, _, _, artifact = _run_architect(tmp_path)
    with pytest.raises(ValueError, match="remain proposed"):
        replace(artifact.adr_drafts[0], status="ACCEPTED")
    with pytest.raises(ValueError, match="cannot select"):
        replace(artifact, pilot_status="SELECTED")
    with pytest.raises(ValueError, match="Software Architect role"):
        replace(artifact, business_role=AgentRole.BACKEND_ENGINEER)


def test_store_uses_mode_0600_and_rejects_tamper_permission_symlink_and_unknown_entry(
    tmp_path: Path,
) -> None:
    service, _, intake, _, _, _, artifact = _run_architect(tmp_path)
    path = (
        tmp_path
        / "architecture-state"
        / intake.tenant_id
        / artifact.execution_id
        / "architecture-proposal-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    os.chmod(path, 0o644)
    with pytest.raises(ArchitectureWorkforceCorrupt, match="unsafe"):
        service.get(intake.tenant_id, artifact.execution_id)

    os.chmod(path, 0o600)
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace(ARTIFACT_STATUS, "APPROVED"), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(ArchitectureWorkforceCorrupt):
        service.get(intake.tenant_id, artifact.execution_id)

    path.unlink()
    path.symlink_to(tmp_path / "outside.json")
    with pytest.raises(ArchitectureWorkforceCorrupt, match="unsafe"):
        service.get(intake.tenant_id, artifact.execution_id)

    path.unlink()
    path.write_text(json.dumps({}), encoding="utf-8")
    os.chmod(path, 0o600)
    (path.parent / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ArchitectureWorkforceCorrupt, match="not closed"):
        service.get(intake.tenant_id, artifact.execution_id)


def test_proposal_contains_no_engineering_task_or_repository_payload(tmp_path: Path) -> None:
    _, _, _, _, _, _, artifact = _run_architect(tmp_path)
    serialized = repr(artifact).casefold()
    assert "official pilot" not in serialized
    assert "repository path" not in serialized
    assert "source code" not in serialized
    assert "engineering task id" not in serialized
    assert artifact.status == "DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW"
