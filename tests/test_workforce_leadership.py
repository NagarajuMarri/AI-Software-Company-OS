from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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
)
from runtime.workforce_leadership import (
    ARTIFACT_STATUS,
    CEO_ACTION_IDS,
    CEO_CAPABILITY_IDS,
    FileLeadershipArtifactStore,
    LeadershipAgentProvider,
    LeadershipArtifactKind,
    LeadershipWorkforceCorrupt,
    LeadershipWorkforcePolicyError,
    LeadershipWorkforceService,
    OpportunityIntake,
    PILOT_STATUS,
    PRODUCT_MANAGER_ACTION_IDS,
    PRODUCT_MANAGER_CAPABILITY_IDS,
    WORK_STATUS,
    ceo_objective,
    product_manager_objective,
)


NOW = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)


def _intake(**changes) -> OpportunityIntake:
    values = {
        "opportunity_id": "opportunity-verification-1",
        "tenant_id": "tenant-verification",
        "title": "Generic workflow coordination",
        "problem_statement": (
            "Small teams need a clearer way to coordinate recurring community activities."
        ),
        "target_users": ("Volunteer coordinators", "Community participants"),
        "desired_outcomes": (
            "Make activity responsibilities visible",
            "Reduce missed coordination steps",
        ),
        "constraints": (
            "Use only generic verification data",
            "No official pilot product is selected",
        ),
        "recorded_at": NOW,
    }
    values.update(changes)
    return OpportunityIntake(**values)


def _twin(role: AgentRole, **changes) -> DigitalTwinDefinition:
    capabilities = (
        CEO_CAPABILITY_IDS
        if role is AgentRole.CEO
        else PRODUCT_MANAGER_CAPABILITY_IDS
    )
    values = {
        "twin_id": "twin-ceo-1" if role is AgentRole.CEO else "twin-product-manager-1",
        "display_name": "Bounded CEO" if role is AgentRole.CEO else "Bounded Product Manager",
        "business_role": role,
        "provider_id": "deterministic-leadership-v1",
        "capability_ids": capabilities,
        "approved_tool_ids": (),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _authority(
    role: AgentRole,
    objective: str,
    *,
    assignment_id: str,
    twin_id: str,
    **changes,
) -> DelegatedAuthority:
    actions = CEO_ACTION_IDS if role is AgentRole.CEO else PRODUCT_MANAGER_ACTION_IDS
    values = {
        "authority_id": f"authority-{assignment_id}",
        "issuer_id": "founder-module-approval",
        "tenant_id": "tenant-verification",
        "assignment_id": assignment_id,
        "twin_id": twin_id,
        "business_role": role,
        "objective_digest": hashlib.sha256(objective.encode()).hexdigest(),
        "allowed_action_ids": actions,
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=2),
        "max_tool_calls": 0,
        "max_output_bytes": 32_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _service(
    tmp_path: Path,
    *,
    provider: LeadershipAgentProvider | None = None,
) -> tuple[LeadershipWorkforceService, LeadershipAgentProvider]:
    selected = provider or LeadershipAgentProvider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected,)),
        DigitalTwinToolRegistry(()),
        FileDigitalTwinExecutionStore(tmp_path / "digital-twin-state"),
        clock=lambda: NOW + timedelta(minutes=2),
    )
    service = LeadershipWorkforceService(
        runtime,
        selected,
        FileLeadershipArtifactStore(tmp_path / "leadership-state"),
        clock=lambda: NOW + timedelta(minutes=1),
    )
    return service, selected


def _run_ceo(tmp_path: Path):
    intake = _intake()
    twin = _twin(AgentRole.CEO)
    authority = _authority(
        AgentRole.CEO,
        ceo_objective(intake),
        assignment_id="assignment-ceo-1",
        twin_id=twin.twin_id,
    )
    service, provider = _service(tmp_path)
    artifact = service.run_ceo(
        execution_id="execution-ceo-1",
        twin=twin,
        authority=authority,
        intake=intake,
    )
    return service, provider, intake, twin, authority, artifact


def _run_both(tmp_path: Path):
    service, provider, intake, ceo_twin, ceo_authority, ceo = _run_ceo(tmp_path)
    pm_twin = _twin(AgentRole.PROJECT_MANAGER)
    pm_authority = _authority(
        AgentRole.PROJECT_MANAGER,
        product_manager_objective(intake, ceo),
        assignment_id="assignment-product-manager-1",
        twin_id=pm_twin.twin_id,
    )
    pm = service.run_product_manager(
        execution_id="execution-product-manager-1",
        twin=pm_twin,
        authority=pm_authority,
        intake=intake,
        ceo_artifact=ceo,
    )
    return (
        service,
        provider,
        intake,
        ceo_twin,
        ceo_authority,
        ceo,
        pm_twin,
        pm_authority,
        pm,
    )


def test_ceo_and_product_manager_execute_exact_bounded_roles(tmp_path: Path) -> None:
    values = _run_both(tmp_path)
    service, provider, intake, _, _, ceo, _, _, pm = values

    assert provider.execution_count == 2
    assert ceo.kind is LeadershipArtifactKind.CEO_OPPORTUNITY_BRIEF
    assert ceo.business_role is AgentRole.CEO
    assert ceo.goals == intake.desired_outcomes
    assert ceo.scope_in == ceo.scope_out == ceo.plan_items == ()
    assert ceo.status_report.state == WORK_STATUS
    assert ceo.status == ARTIFACT_STATUS
    assert ceo.pilot_status == PILOT_STATUS

    assert pm.kind is LeadershipArtifactKind.PRODUCT_MANAGER_PLAN
    assert pm.business_role is AgentRole.PROJECT_MANAGER
    assert pm.upstream_artifact_digest == ceo.digest
    assert pm.goals == intake.desired_outcomes
    assert len(pm.scope_in) == len(intake.desired_outcomes)
    assert len(pm.scope_out) == 3
    assert len(pm.clarification_questions) == 3
    assert len(pm.plan_items) == 3
    assert pm.status_report.blockers == ("Human product-plan review is pending",)
    assert service.get(intake.tenant_id, ceo.execution_id) == ceo
    assert service.get(intake.tenant_id, pm.execution_id) == pm


def test_role_profiles_have_no_tools_or_elevated_authority(tmp_path: Path) -> None:
    _, _, _, _, ceo_authority, ceo, _, pm_authority, pm = _run_both(tmp_path)
    for authority, artifact in ((ceo_authority, ceo), (pm_authority, pm)):
        assert authority.allowed_tool_ids == ()
        assert authority.max_tool_calls == 0
        assert authority.live_provider_allowed is False
        assert artifact.status == "DRAFT_AWAITING_HUMAN_REVIEW"
        assert any("human" in item.casefold() for item in artifact.status_report.blockers)
        assert "APPROVE" not in authority.allowed_action_ids
        assert "SELECT_PILOT_PRODUCT" not in authority.allowed_action_ids
        assert "WRITE_PRODUCT_REPOSITORY" not in authority.allowed_action_ids


def test_exact_retry_and_restart_do_not_repeat_provider_effect(tmp_path: Path) -> None:
    values = _run_both(tmp_path)
    service, provider, intake, ceo_twin, ceo_authority, ceo, pm_twin, pm_authority, pm = values
    assert service.run_ceo(
        execution_id=ceo.execution_id,
        twin=ceo_twin,
        authority=ceo_authority,
        intake=intake,
    ) == ceo
    assert service.run_product_manager(
        execution_id=pm.execution_id,
        twin=pm_twin,
        authority=pm_authority,
        intake=intake,
        ceo_artifact=ceo,
    ) == pm
    assert provider.execution_count == 2

    restarted_provider = LeadershipAgentProvider()
    restarted, _ = _service(tmp_path, provider=restarted_provider)
    assert restarted.run_ceo(
        execution_id=ceo.execution_id,
        twin=ceo_twin,
        authority=ceo_authority,
        intake=intake,
    ) == ceo
    assert restarted.run_product_manager(
        execution_id=pm.execution_id,
        twin=pm_twin,
        authority=pm_authority,
        intake=intake,
        ceo_artifact=ceo,
    ) == pm
    assert restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "allowed_action_ids",
    [
        CEO_ACTION_IDS[:-1],
        CEO_ACTION_IDS + ("APPROVE_OPPORTUNITY",),
        tuple(reversed(CEO_ACTION_IDS)),
    ],
)
def test_ceo_requires_exact_action_profile_before_provider_effect(
    tmp_path: Path,
    allowed_action_ids: tuple[str, ...],
) -> None:
    intake = _intake()
    twin = _twin(AgentRole.CEO)
    authority = _authority(
        AgentRole.CEO,
        ceo_objective(intake),
        assignment_id="assignment-ceo-1",
        twin_id=twin.twin_id,
        allowed_action_ids=allowed_action_ids,
    )
    service, provider = _service(tmp_path)
    with pytest.raises(LeadershipWorkforcePolicyError, match="exact role profile"):
        service.run_ceo(
            execution_id="execution-ceo-1",
            twin=twin,
            authority=authority,
            intake=intake,
        )
    assert provider.execution_count == 0


def test_wrong_role_capability_tenant_and_tool_profiles_fail_closed(tmp_path: Path) -> None:
    intake = _intake()
    twin = _twin(AgentRole.CEO)
    objective = ceo_objective(intake)
    base = _authority(
        AgentRole.CEO,
        objective,
        assignment_id="assignment-ceo-1",
        twin_id=twin.twin_id,
    )
    service, provider = _service(tmp_path)
    candidates = (
        (_twin(AgentRole.CEO, capability_ids=("status-reporting",)), base),
        (twin, replace(base, tenant_id="other-tenant")),
        (twin, replace(base, live_provider_allowed=True)),
    )
    for index, (selected_twin, authority) in enumerate(candidates, start=1):
        with pytest.raises(LeadershipWorkforcePolicyError):
            service.run_ceo(
                execution_id=f"execution-invalid-{index}",
                twin=selected_twin,
                authority=authority,
                intake=intake,
            )
    assert provider.execution_count == 0


def test_product_manager_requires_exact_persisted_ceo_handoff(tmp_path: Path) -> None:
    service, _, intake, _, _, ceo = _run_ceo(tmp_path)
    pm_twin = _twin(AgentRole.PROJECT_MANAGER)
    changed = replace(ceo, summary="Changed after persistence")
    authority = _authority(
        AgentRole.PROJECT_MANAGER,
        product_manager_objective(intake, changed),
        assignment_id="assignment-product-manager-1",
        twin_id=pm_twin.twin_id,
    )
    with pytest.raises(LeadershipWorkforcePolicyError, match="exact persisted"):
        service.run_product_manager(
            execution_id="execution-product-manager-1",
            twin=pm_twin,
            authority=authority,
            intake=intake,
            ceo_artifact=changed,
        )

    other_intake = _intake(opportunity_id="another-opportunity")
    with pytest.raises(LeadershipWorkforcePolicyError, match="handoff"):
        service.run_product_manager(
            execution_id="execution-product-manager-2",
            twin=pm_twin,
            authority=authority,
            intake=other_intake,
            ceo_artifact=ceo,
        )


def test_invalid_provider_output_becomes_terminal_and_is_not_persisted(tmp_path: Path) -> None:
    intake = _intake()
    twin = _twin(AgentRole.CEO)
    authority = _authority(
        AgentRole.CEO,
        ceo_objective(intake),
        assignment_id="assignment-ceo-1",
        twin_id=twin.twin_id,
    )
    provider = LeadershipAgentProvider()
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
    service, _ = _service(tmp_path, provider=provider)
    with pytest.raises(LeadershipWorkforcePolicyError, match="not closed"):
        service.run_ceo(
            execution_id="execution-ceo-invalid",
            twin=twin,
            authority=authority,
            intake=intake,
        )
    with pytest.raises(Exception):
        service.get(intake.tenant_id, "execution-ceo-invalid")


def test_intake_and_artifact_models_cannot_select_a_pilot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot select"):
        _intake(pilot_status="SELECTED")
    _, _, _, _, _, _, _, _, pm = _run_both(tmp_path)
    with pytest.raises(ValueError, match="cannot select"):
        replace(pm, pilot_status="SELECTED")


def test_maximum_bounded_intake_stays_within_provider_context_and_output_limits(
    tmp_path: Path,
) -> None:
    intake = _intake(
        target_users=tuple(f"User {index} " + "u" * 190 for index in range(1, 9)),
        desired_outcomes=tuple(
            f"Outcome {index} " + "o" * 188 for index in range(1, 9)
        ),
        constraints=tuple(
            f"Constraint {index} " + "c" * 225 for index in range(1, 9)
        ),
    )
    ceo_twin = _twin(AgentRole.CEO)
    ceo_authority = _authority(
        AgentRole.CEO,
        ceo_objective(intake),
        assignment_id="assignment-ceo-maximum",
        twin_id=ceo_twin.twin_id,
    )
    service, provider = _service(tmp_path)
    ceo = service.run_ceo(
        execution_id="execution-ceo-maximum",
        twin=ceo_twin,
        authority=ceo_authority,
        intake=intake,
    )
    pm_twin = _twin(AgentRole.PROJECT_MANAGER)
    pm_authority = _authority(
        AgentRole.PROJECT_MANAGER,
        product_manager_objective(intake, ceo),
        assignment_id="assignment-pm-maximum",
        twin_id=pm_twin.twin_id,
    )
    pm = service.run_product_manager(
        execution_id="execution-pm-maximum",
        twin=pm_twin,
        authority=pm_authority,
        intake=intake,
        ceo_artifact=ceo,
    )
    assert provider.execution_count == 2
    assert len(pm.goals) == len(pm.scope_in) == 8


def test_store_uses_mode_0600_and_rejects_tamper_symlink_and_unknown_entry(
    tmp_path: Path,
) -> None:
    service, _, intake, _, _, ceo = _run_ceo(tmp_path)
    path = (
        tmp_path
        / "leadership-state"
        / intake.tenant_id
        / ceo.execution_id
        / "leadership-artifact-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace(ARTIFACT_STATUS, "APPROVED"), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(LeadershipWorkforceCorrupt):
        service.get(intake.tenant_id, ceo.execution_id)

    path.unlink()
    path.symlink_to(tmp_path / "outside.json")
    with pytest.raises(LeadershipWorkforceCorrupt):
        service.get(intake.tenant_id, ceo.execution_id)

    path.unlink()
    path.write_text(json.dumps({}), encoding="utf-8")
    os.chmod(path, 0o600)
    (path.parent / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(LeadershipWorkforceCorrupt, match="not closed"):
        service.get(intake.tenant_id, ceo.execution_id)
