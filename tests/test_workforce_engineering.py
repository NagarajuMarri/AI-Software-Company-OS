from __future__ import annotations

from dataclasses import fields, replace
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
from runtime.workforce_architecture import FileArchitectureArtifactStore
from runtime.workforce_engineering import (
    ARTIFACT_STATUS,
    ENGINEERING_ROLES,
    PILOT_STATUS,
    WORK_STATUS,
    EngineeringAgentProvider,
    EngineeringWorkArtifact,
    EngineeringWorkOrder,
    EngineeringWorkforceCorrupt,
    EngineeringWorkforcePolicyError,
    EngineeringWorkforceService,
    FileEngineeringArtifactStore,
    action_ids_for,
    capability_ids_for,
    discipline_for,
    engineering_objective,
)
from tests.test_workforce_architecture import _run_architect
from tests.test_workforce_leadership import NOW


_TARGET_COMPONENTS = {
    AgentRole.BACKEND_ENGINEER: ("application-service", "domain-core"),
    AgentRole.FRONTEND_ENGINEER: ("interface-boundary",),
    AgentRole.AI_ENGINEER: ("application-service", "evidence-boundary"),
    AgentRole.DATA_ENGINEER: ("domain-core", "persistence-adapter"),
}


def _slug(role: AgentRole) -> str:
    return role.value.casefold().replace("_", "-")


def _engineering_twin(role: AgentRole, **changes) -> DigitalTwinDefinition:
    slug = _slug(role)
    values = {
        "twin_id": f"twin-{slug}-1",
        "display_name": f"Bounded {role.value.replace('_', ' ').title()}",
        "business_role": role,
        "provider_id": "deterministic-engineering-family-v1",
        "capability_ids": capability_ids_for(role),
        "approved_tool_ids": (),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _work_order(role: AgentRole, architecture, **changes) -> EngineeringWorkOrder:
    slug = _slug(role)
    values = {
        "work_order_id": f"work-order-{slug}-1",
        "tenant_id": architecture.tenant_id,
        "opportunity_id": architecture.opportunity_id,
        "assignment_id": f"assignment-{slug}-1",
        "business_role": role,
        "title": f"Generic {role.value.replace('_', ' ').title()} assignment",
        "objective": "Translate the assigned architecture boundary into a typed engineering output",
        "architecture_artifact_digest": architecture.digest,
        "target_component_ids": _TARGET_COMPONENTS.get(role, ("interface-boundary",)),
        "acceptance_checks": (
            "The output is role-specific and source-bound",
            "Failure behavior and later verification are explicit",
        ),
        "constraints": (
            "No product repository or command access",
            "No merge, deployment, release, or pilot selection",
        ),
        "issued_at": NOW + timedelta(minutes=5),
    }
    values.update(changes)
    return EngineeringWorkOrder(**values)


def _engineering_authority(
    work_order: EngineeringWorkOrder,
    architecture,
    *,
    twin_id: str | None = None,
    **changes,
) -> DelegatedAuthority:
    role = work_order.business_role
    values = {
        "authority_id": f"authority-{work_order.assignment_id}",
        "issuer_id": "founder-module-approval",
        "tenant_id": work_order.tenant_id,
        "assignment_id": work_order.assignment_id,
        "twin_id": twin_id or f"twin-{_slug(role)}-1",
        "business_role": role,
        "objective_digest": hashlib.sha256(
            engineering_objective(work_order, architecture).encode()
        ).hexdigest(),
        "allowed_action_ids": action_ids_for(role),
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=2),
        "max_tool_calls": 0,
        "max_output_bytes": 64_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _engineering_service(
    tmp_path: Path,
    *,
    provider: EngineeringAgentProvider | None = None,
) -> tuple[EngineeringWorkforceService, EngineeringAgentProvider]:
    selected = provider or EngineeringAgentProvider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected,)),
        DigitalTwinToolRegistry(()),
        FileDigitalTwinExecutionStore(tmp_path / "engineering-digital-twin-state"),
        clock=lambda: NOW + timedelta(minutes=8),
    )
    service = EngineeringWorkforceService(
        runtime,
        selected,
        FileArchitectureArtifactStore(tmp_path / "architecture-state"),
        FileEngineeringArtifactStore(tmp_path / "engineering-state"),
        clock=lambda: NOW + timedelta(minutes=7),
    )
    return service, selected


def _run_engineering_family(tmp_path: Path):
    architect_run = _run_architect(tmp_path)
    intake, architecture = architect_run[2], architect_run[6]
    service, provider = _engineering_service(tmp_path)
    executions = []
    for role in ENGINEERING_ROLES:
        work_order = _work_order(role, architecture)
        twin = _engineering_twin(role)
        authority = _engineering_authority(
            work_order, architecture, twin_id=twin.twin_id
        )
        artifact = service.run(
            execution_id=f"execution-{_slug(role)}-1",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
        )
        executions.append((work_order, twin, authority, artifact))
    return service, provider, intake, architecture, tuple(executions)


def test_four_engineering_roles_execute_through_one_governed_runtime(
    tmp_path: Path,
) -> None:
    service, provider, intake, architecture, executions = _run_engineering_family(
        tmp_path
    )

    assert provider.execution_count == 4
    assert tuple(item[3].business_role for item in executions) == ENGINEERING_ROLES
    assert {item[3].provider_id for item in executions} == {provider.provider_id}
    for work_order, twin, authority, artifact in executions:
        assert artifact.tenant_id == intake.tenant_id
        assert artifact.work_order_digest == work_order.digest
        assert artifact.architecture_artifact_digest == architecture.digest
        assert artifact.capability_ids == twin.capability_ids == capability_ids_for(
            artifact.business_role
        )
        assert artifact.action_ids == authority.allowed_action_ids == action_ids_for(
            artifact.business_role
        )
        assert len(artifact.implementation_items) == 2
        assert len(artifact.interface_contracts) == 1
        assert all(
            item.discipline is discipline_for(artifact.business_role)
            for item in artifact.implementation_items
        )
        assert artifact.status_report.state == WORK_STATUS
        assert artifact.status == ARTIFACT_STATUS
        assert artifact.pilot_status == PILOT_STATUS
        assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_engineering_family_has_exact_role_profiles_and_zero_tools(
    tmp_path: Path,
) -> None:
    _, _, _, _, executions = _run_engineering_family(tmp_path)

    for _, twin, authority, artifact in executions:
        assert twin.approved_tool_ids == authority.allowed_tool_ids == ()
        assert authority.max_tool_calls == 0
        assert authority.live_provider_allowed is False
        for forbidden in (
            "APPROVE_ARCHITECTURE",
            "RUN_QA",
            "RUN_SECURITY_REVIEW",
            "WRITE_PRODUCT_REPOSITORY",
            "RUN_COMMAND",
            "COMMIT",
            "MERGE",
            "DEPLOY",
            "RELEASE",
            "ORCHESTRATE_AGENTS",
            "SELECT_PILOT_PRODUCT",
        ):
            assert forbidden not in artifact.action_ids


def test_exact_retry_and_restart_do_not_repeat_engineering_provider_effect(
    tmp_path: Path,
) -> None:
    service, provider, _, architecture, executions = _run_engineering_family(tmp_path)
    work_order, twin, authority, artifact = executions[0]
    assert service.run(
        execution_id=artifact.execution_id,
        twin=twin,
        authority=authority,
        work_order=work_order,
        architecture=architecture,
    ) == artifact
    assert provider.execution_count == 4

    restarted_provider = EngineeringAgentProvider()
    restarted, _ = _engineering_service(tmp_path, provider=restarted_provider)
    assert restarted.run(
        execution_id=artifact.execution_id,
        twin=twin,
        authority=authority,
        work_order=work_order,
        architecture=architecture,
    ) == artifact
    assert restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "profile_change",
    ["missing-action", "extra-action", "reordered-actions", "missing-capability"],
)
def test_engineering_requires_exact_ordered_role_profile_before_provider_effect(
    tmp_path: Path,
    profile_change: str,
) -> None:
    architect_run = _run_architect(tmp_path)
    architecture = architect_run[6]
    role = AgentRole.BACKEND_ENGINEER
    work_order = _work_order(role, architecture)
    twin = _engineering_twin(role)
    authority = _engineering_authority(work_order, architecture)
    if profile_change == "missing-action":
        authority = replace(authority, allowed_action_ids=authority.allowed_action_ids[:-1])
    elif profile_change == "extra-action":
        authority = replace(
            authority,
            allowed_action_ids=authority.allowed_action_ids + ("RUN_QA",),
        )
    elif profile_change == "reordered-actions":
        authority = replace(
            authority, allowed_action_ids=tuple(reversed(authority.allowed_action_ids))
        )
    else:
        twin = _engineering_twin(role, capability_ids=capability_ids_for(role)[:-1])
    service, provider = _engineering_service(tmp_path)

    with pytest.raises(EngineeringWorkforcePolicyError, match="boundary does not match"):
        service.run(
            execution_id=f"execution-invalid-{profile_change}",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
        )
    assert provider.execution_count == 0


def test_wrong_role_tenant_assignment_live_and_tool_profiles_fail_closed(
    tmp_path: Path,
) -> None:
    architecture = _run_architect(tmp_path)[6]
    work_order = _work_order(AgentRole.BACKEND_ENGINEER, architecture)
    twin = _engineering_twin(work_order.business_role)
    base = _engineering_authority(work_order, architecture)
    service, provider = _engineering_service(tmp_path)
    candidates = (
        (
            _engineering_twin(AgentRole.FRONTEND_ENGINEER),
            replace(base, business_role=AgentRole.FRONTEND_ENGINEER),
        ),
        (twin, replace(base, tenant_id="other-tenant")),
        (twin, replace(base, assignment_id="other-assignment")),
        (twin, replace(base, live_provider_allowed=True)),
        (
            _engineering_twin(
                work_order.business_role, approved_tool_ids=("repository.write",)
            ),
            replace(
                base,
                allowed_action_ids=base.allowed_action_ids + (USE_ASSIGNED_TOOL,),
                allowed_tool_ids=("repository.write",),
                max_tool_calls=1,
            ),
        ),
    )
    for index, (selected_twin, authority) in enumerate(candidates, start=1):
        with pytest.raises(EngineeringWorkforcePolicyError):
            service.run(
                execution_id=f"execution-invalid-boundary-{index}",
                twin=selected_twin,
                authority=authority,
                work_order=work_order,
                architecture=architecture,
            )
    assert provider.execution_count == 0


def test_engineering_requires_exact_persisted_architecture_handoff(
    tmp_path: Path,
) -> None:
    architecture = _run_architect(tmp_path)[6]
    work_order = _work_order(AgentRole.DATA_ENGINEER, architecture)
    twin = _engineering_twin(work_order.business_role)
    authority = _engineering_authority(work_order, architecture)
    service, provider = _engineering_service(tmp_path)

    changed = replace(architecture, summary="Changed after persistence")
    with pytest.raises(EngineeringWorkforcePolicyError, match="exact bounded"):
        service.run(
            execution_id="execution-changed-architecture",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=changed,
        )
    wrong_target = _work_order(
        AgentRole.DATA_ENGINEER,
        architecture,
        target_component_ids=("missing-component",),
    )
    wrong_authority = _engineering_authority(wrong_target, architecture)
    with pytest.raises(EngineeringWorkforcePolicyError, match="exact bounded"):
        service.run(
            execution_id="execution-missing-component",
            twin=twin,
            authority=wrong_authority,
            work_order=wrong_target,
            architecture=architecture,
        )
    assert provider.execution_count == 0


def test_unknown_provider_output_is_rejected(tmp_path: Path) -> None:
    architecture = _run_architect(tmp_path)[6]
    work_order = _work_order(AgentRole.AI_ENGINEER, architecture)
    twin = _engineering_twin(work_order.business_role)
    authority = _engineering_authority(work_order, architecture)
    provider = EngineeringAgentProvider()
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
    service, _ = _engineering_service(tmp_path, provider=provider)
    with pytest.raises(EngineeringWorkforcePolicyError, match="not closed"):
        service.run(
            execution_id="execution-invalid-output",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
        )


@pytest.mark.parametrize("corruption", ["cross-role", "malformed-interface"])
def test_nested_provider_output_must_match_the_closed_role_schema(
    tmp_path: Path,
    corruption: str,
) -> None:
    architecture = _run_architect(tmp_path)[6]
    work_order = _work_order(AgentRole.AI_ENGINEER, architecture)
    twin = _engineering_twin(work_order.business_role)
    authority = _engineering_authority(work_order, architecture)
    provider = EngineeringAgentProvider()
    original = provider.render

    def invalid(request):
        result = original(request)
        output = list(result.output)
        target_key = (
            "implementation_items_json"
            if corruption == "cross-role"
            else "interface_contracts_json"
        )
        for index, item in enumerate(output):
            if item.key != target_key:
                continue
            value = json.loads(item.value)
            if corruption == "cross-role":
                value[0]["discipline"] = "BACKEND"
            else:
                value[0]["inputs"] = "not-a-list"
            output[index] = ContextValue(item.key, json.dumps(value))
            break
        return ProviderExecutionResult(
            result.execution_id,
            result.provider_id,
            result.request_digest,
            result.status,
            result.summary,
            tuple(output),
        )

    provider.render = invalid
    service, _ = _engineering_service(tmp_path, provider=provider)
    with pytest.raises(EngineeringWorkforcePolicyError, match="typed validation"):
        service.run(
            execution_id=f"execution-invalid-{corruption}",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
        )


def test_engineering_models_cannot_cross_roles_approve_or_select_pilot(
    tmp_path: Path,
) -> None:
    _, _, _, _, executions = _run_engineering_family(tmp_path)
    artifact = executions[0][3]
    with pytest.raises(ValueError):
        replace(artifact, business_role=AgentRole.FRONTEND_ENGINEER)
    with pytest.raises(ValueError, match="authorized workspace"):
        replace(artifact, status="APPLIED_TO_PRODUCT_REPOSITORY")
    with pytest.raises(ValueError, match="cannot select"):
        replace(artifact, pilot_status="SELECTED")
    with pytest.raises(ValueError, match="not supported"):
        _work_order(AgentRole.QA_ENGINEER, artifact)


def test_store_uses_mode_0600_and_rejects_tamper_permission_symlink_and_unknown_entry(
    tmp_path: Path,
) -> None:
    service, _, _, _, executions = _run_engineering_family(tmp_path)
    artifact = executions[0][3]
    path = (
        tmp_path
        / "engineering-state"
        / artifact.tenant_id
        / artifact.execution_id
        / "engineering-work-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    os.chmod(path, 0o644)
    with pytest.raises(EngineeringWorkforceCorrupt, match="unsafe"):
        service.get(artifact.tenant_id, artifact.execution_id)

    os.chmod(path, 0o600)
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace(ARTIFACT_STATUS, "APPLIED"), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(EngineeringWorkforceCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)

    path.unlink()
    path.symlink_to(tmp_path / "outside.json")
    with pytest.raises(EngineeringWorkforceCorrupt, match="unsafe"):
        service.get(artifact.tenant_id, artifact.execution_id)

    path.unlink()
    path.write_text(json.dumps({}), encoding="utf-8")
    os.chmod(path, 0o600)
    (path.parent / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(EngineeringWorkforceCorrupt, match="not closed"):
        service.get(artifact.tenant_id, artifact.execution_id)


def test_artifact_schema_has_no_repository_command_or_delivery_effect_fields(
    tmp_path: Path,
) -> None:
    _, _, _, _, executions = _run_engineering_family(tmp_path)
    names = {item.name for item in fields(EngineeringWorkArtifact)}
    assert not names.intersection(
        {
            "repository",
            "repository_path",
            "workspace_path",
            "file_changes",
            "patch",
            "command",
            "commit_sha",
            "deployment_url",
            "release_id",
        }
    )
    assert all(item[3].pilot_status == "NOT_SELECTED" for item in executions)
