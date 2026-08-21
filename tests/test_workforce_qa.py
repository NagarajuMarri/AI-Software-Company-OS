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
from runtime.workforce_engineering import FileEngineeringArtifactStore
from runtime.workforce_qa import (
    ARTIFACT_STATUS,
    DEFECT_STATUS,
    EXECUTION_STATE,
    PILOT_STATUS,
    QA_ACTIONS,
    QA_CAPABILITIES,
    QA_ROLE,
    WORK_STATUS,
    FileQAArtifactStore,
    QAAutomatedTestSpec,
    QAEngineerProvider,
    QAWorkArtifact,
    QAWorkOrder,
    QAWorkforceCorrupt,
    QAWorkforcePolicyError,
    QAWorkforceService,
    qa_objective,
)
from tests.test_workforce_engineering import _run_engineering_family
from tests.test_workforce_leadership import NOW


def _qa_twin(**changes) -> DigitalTwinDefinition:
    values = {
        "twin_id": "twin-qa-engineer-1",
        "display_name": "Bounded QA Engineer",
        "business_role": QA_ROLE,
        "provider_id": "deterministic-qa-engineer-v1",
        "capability_ids": QA_CAPABILITIES,
        "approved_tool_ids": (),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _qa_work_order(architecture, engineering_artifacts, **changes) -> QAWorkOrder:
    values = {
        "work_order_id": "work-order-qa-engineer-1",
        "tenant_id": architecture.tenant_id,
        "opportunity_id": architecture.opportunity_id,
        "assignment_id": "assignment-qa-engineer-1",
        "business_role": QA_ROLE,
        "title": "Generic source-bound QA assignment",
        "objective": (
            "Prepare typed test plans, automated-test specifications, integration-test "
            "specifications, and draft defect reports"
        ),
        "architecture_artifact_digest": architecture.digest,
        "engineering_artifact_digests": tuple(
            item.digest for item in engineering_artifacts
        ),
        "acceptance_checks": (
            "Every Engineering role and exact source digest has QA coverage",
            "Automation, integration, failure, and defect behavior are explicit",
            "No test execution or product-delivery authority is exercised",
        ),
        "quality_risks": (
            "Cross-role contract drift could escape isolated component checks",
            "Failure paths could expose unvalidated or cross-tenant state",
        ),
        "constraints": (
            "No product workspace, repository, command, browser, or network access",
            "No quality approval, Security, DevOps, merge, deployment, release, or pilot selection",
        ),
        "issued_at": NOW + timedelta(minutes=10),
    }
    values.update(changes)
    return QAWorkOrder(**values)


def _qa_authority(
    work_order: QAWorkOrder,
    architecture,
    engineering_artifacts,
    *,
    twin_id: str = "twin-qa-engineer-1",
    **changes,
) -> DelegatedAuthority:
    values = {
        "authority_id": "authority-qa-engineer-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": work_order.tenant_id,
        "assignment_id": work_order.assignment_id,
        "twin_id": twin_id,
        "business_role": QA_ROLE,
        "objective_digest": hashlib.sha256(
            qa_objective(work_order, architecture, engineering_artifacts).encode()
        ).hexdigest(),
        "allowed_action_ids": QA_ACTIONS,
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=3),
        "max_tool_calls": 0,
        "max_output_bytes": 96_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _qa_service(
    tmp_path: Path,
    *,
    provider: QAEngineerProvider | None = None,
) -> tuple[QAWorkforceService, QAEngineerProvider]:
    selected = provider or QAEngineerProvider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected,)),
        DigitalTwinToolRegistry(()),
        FileDigitalTwinExecutionStore(tmp_path / "qa-digital-twin-state"),
        clock=lambda: NOW + timedelta(minutes=13),
    )
    service = QAWorkforceService(
        runtime,
        selected,
        FileArchitectureArtifactStore(tmp_path / "architecture-state"),
        FileEngineeringArtifactStore(tmp_path / "engineering-state"),
        FileQAArtifactStore(tmp_path / "qa-state"),
        clock=lambda: NOW + timedelta(minutes=12),
    )
    return service, selected


def _run_qa(tmp_path: Path):
    engineering = _run_engineering_family(tmp_path)
    _, _, intake, architecture, executions = engineering
    engineering_artifacts = tuple(item[3] for item in executions)
    work_order = _qa_work_order(architecture, engineering_artifacts)
    twin = _qa_twin()
    authority = _qa_authority(work_order, architecture, engineering_artifacts)
    service, provider = _qa_service(tmp_path)
    artifact = service.run(
        execution_id="execution-qa-engineer-1",
        twin=twin,
        authority=authority,
        work_order=work_order,
        architecture=architecture,
        engineering_artifacts=engineering_artifacts,
    )
    return (
        service,
        provider,
        intake,
        architecture,
        engineering_artifacts,
        work_order,
        twin,
        authority,
        artifact,
    )


def test_qa_engineer_produces_source_bound_test_and_defect_artifacts(
    tmp_path: Path,
) -> None:
    service, provider, intake, architecture, sources, work_order, twin, authority, artifact = (
        _run_qa(tmp_path)
    )

    assert provider.execution_count == 1
    assert artifact.business_role is QA_ROLE
    assert artifact.tenant_id == intake.tenant_id
    assert artifact.work_order_digest == work_order.digest
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(
        item.digest for item in sources
    )
    assert artifact.capability_ids == twin.capability_ids == QA_CAPABILITIES
    assert artifact.action_ids == authority.allowed_action_ids == QA_ACTIONS
    assert len(artifact.test_plan_items) == 4
    assert len(artifact.automated_test_specs) == 4
    assert len(artifact.integration_test_specs) == 2
    assert len(artifact.defect_reports) == 2
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.automated_test_specs)
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.integration_test_specs)
    assert all(item.status == DEFECT_STATUS for item in artifact.defect_reports)
    assert artifact.status_report.state == WORK_STATUS
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pilot_status == PILOT_STATUS
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_qa_profile_has_zero_tools_and_no_later_module_or_delivery_authority(
    tmp_path: Path,
) -> None:
    _, _, _, _, _, _, twin, authority, artifact = _run_qa(tmp_path)

    assert twin.approved_tool_ids == authority.allowed_tool_ids == ()
    assert authority.max_tool_calls == 0
    assert authority.live_provider_allowed is False
    for forbidden in (
        "WRITE_TEST_FILES",
        "RUN_AUTOMATED_TESTS",
        "RUN_INTEGRATION_TESTS",
        "APPROVE_QUALITY",
        "RUN_SECURITY_REVIEW",
        "CONFIGURE_CI",
        "WRITE_DOCUMENTATION",
        "ORCHESTRATE_AGENTS",
        "WRITE_PRODUCT_REPOSITORY",
        "RUN_COMMAND",
        "COMMIT",
        "MERGE",
        "DEPLOY",
        "RELEASE",
        "SELECT_PILOT_PRODUCT",
    ):
        assert forbidden not in artifact.action_ids


def test_exact_retry_and_restart_do_not_repeat_qa_provider_effect(tmp_path: Path) -> None:
    service, provider, _, architecture, sources, work_order, twin, authority, artifact = (
        _run_qa(tmp_path)
    )
    arguments = {
        "execution_id": artifact.execution_id,
        "twin": twin,
        "authority": authority,
        "work_order": work_order,
        "architecture": architecture,
        "engineering_artifacts": sources,
    }
    assert service.run(**arguments) == artifact
    assert provider.execution_count == 1

    restarted_provider = QAEngineerProvider()
    restarted, _ = _qa_service(tmp_path, provider=restarted_provider)
    assert restarted.run(**arguments) == artifact
    assert restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "profile_change",
    ["missing-action", "extra-action", "reordered-actions", "missing-capability"],
)
def test_qa_requires_exact_ordered_profile_before_provider_effect(
    tmp_path: Path,
    profile_change: str,
) -> None:
    _, _, _, architecture, executions = _run_engineering_family(tmp_path)
    sources = tuple(item[3] for item in executions)
    work_order = _qa_work_order(architecture, sources)
    twin = _qa_twin()
    authority = _qa_authority(work_order, architecture, sources)
    if profile_change == "missing-action":
        authority = replace(authority, allowed_action_ids=authority.allowed_action_ids[:-1])
    elif profile_change == "extra-action":
        authority = replace(
            authority, allowed_action_ids=authority.allowed_action_ids + ("RUN_SECURITY_REVIEW",)
        )
    elif profile_change == "reordered-actions":
        authority = replace(
            authority, allowed_action_ids=tuple(reversed(authority.allowed_action_ids))
        )
    else:
        twin = _qa_twin(capability_ids=QA_CAPABILITIES[:-1])
    service, provider = _qa_service(tmp_path)

    with pytest.raises(QAWorkforcePolicyError, match="boundary does not match"):
        service.run(
            execution_id=f"execution-invalid-{profile_change}",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=sources,
        )
    assert provider.execution_count == 0


@pytest.mark.parametrize(
    "boundary",
    ["wrong-role", "wrong-tenant", "wrong-assignment", "live-provider", "tool"],
)
def test_wrong_qa_role_tenant_assignment_live_and_tool_profiles_fail_closed(
    tmp_path: Path,
    boundary: str,
) -> None:
    _, _, _, architecture, executions = _run_engineering_family(tmp_path)
    sources = tuple(item[3] for item in executions)
    work_order = _qa_work_order(architecture, sources)
    twin = _qa_twin()
    authority = _qa_authority(work_order, architecture, sources)
    if boundary == "wrong-role":
        twin = _qa_twin(business_role=AgentRole.SECURITY_ENGINEER)
    elif boundary == "wrong-tenant":
        authority = replace(authority, tenant_id="tenant-other")
    elif boundary == "wrong-assignment":
        authority = replace(authority, assignment_id="assignment-other")
    elif boundary == "live-provider":
        authority = replace(authority, live_provider_allowed=True)
    else:
        authority = replace(
            authority,
            allowed_action_ids=authority.allowed_action_ids + (USE_ASSIGNED_TOOL,),
            allowed_tool_ids=("test-runner",),
            max_tool_calls=1,
        )
    service, provider = _qa_service(tmp_path)
    with pytest.raises(QAWorkforcePolicyError):
        service.run(
            execution_id=f"execution-invalid-{boundary}",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=sources,
        )
    assert provider.execution_count == 0


@pytest.mark.parametrize("source_change", ["reordered", "changed", "wrong-work-order"])
def test_qa_requires_exact_persisted_engineering_source_set(
    tmp_path: Path,
    source_change: str,
) -> None:
    _, _, _, architecture, executions = _run_engineering_family(tmp_path)
    sources = tuple(item[3] for item in executions)
    work_order = _qa_work_order(architecture, sources)
    if source_change == "reordered":
        sources = (sources[1], sources[0], *sources[2:])
    elif source_change == "changed":
        sources = (replace(sources[0], title="Changed Engineering source"), *sources[1:])
        work_order = _qa_work_order(architecture, sources)
    else:
        work_order = replace(
            work_order,
            engineering_artifact_digests=tuple(reversed(work_order.engineering_artifact_digests)),
        )
    twin = _qa_twin()
    authority = _qa_authority(work_order, architecture, sources)
    service, provider = _qa_service(tmp_path)
    with pytest.raises(QAWorkforcePolicyError, match="exact bounded|persisted state"):
        service.run(
            execution_id=f"execution-invalid-source-{source_change}",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=sources,
        )
    assert provider.execution_count == 0


def test_unknown_qa_provider_output_is_rejected(tmp_path: Path) -> None:
    _, _, _, architecture, executions = _run_engineering_family(tmp_path)
    sources = tuple(item[3] for item in executions)
    work_order = _qa_work_order(architecture, sources)
    twin = _qa_twin()
    authority = _qa_authority(work_order, architecture, sources)
    provider = QAEngineerProvider()
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
    service, _ = _qa_service(tmp_path, provider=provider)
    with pytest.raises(QAWorkforcePolicyError, match="not closed"):
        service.run(
            execution_id="execution-invalid-output",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=sources,
        )


@pytest.mark.parametrize("corruption", ["cross-source", "claimed-execution"])
def test_nested_qa_provider_output_must_match_closed_schema(
    tmp_path: Path,
    corruption: str,
) -> None:
    _, _, _, architecture, executions = _run_engineering_family(tmp_path)
    sources = tuple(item[3] for item in executions)
    work_order = _qa_work_order(architecture, sources)
    twin = _qa_twin()
    authority = _qa_authority(work_order, architecture, sources)
    provider = QAEngineerProvider()
    original = provider.render

    def invalid(request):
        result = original(request)
        output = list(result.output)
        for index, item in enumerate(output):
            if item.key != "automated_test_backend_json":
                continue
            value = json.loads(item.value)
            if corruption == "cross-source":
                value[0]["target_component_id"] = "interface-boundary"
            else:
                value[0]["execution_state"] = "PASSED"
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
    service, _ = _qa_service(tmp_path, provider=provider)
    with pytest.raises(QAWorkforcePolicyError, match="typed validation"):
        service.run(
            execution_id=f"execution-invalid-{corruption}",
            twin=twin,
            authority=authority,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=sources,
        )


def test_qa_models_cannot_claim_execution_approve_or_select_pilot(tmp_path: Path) -> None:
    _, _, _, _, _, work_order, _, _, artifact = _run_qa(tmp_path)
    with pytest.raises(ValueError, match="cannot claim execution"):
        replace(artifact.automated_test_specs[0], execution_state="PASSED")
    with pytest.raises(ValueError, match="authorized workspace"):
        replace(artifact, status="QA_APPROVED")
    with pytest.raises(ValueError, match="cannot select"):
        replace(artifact, pilot_status="SELECTED")
    with pytest.raises(ValueError, match="QA Engineer"):
        replace(work_order, business_role=AgentRole.SECURITY_ENGINEER)


def test_qa_artifact_requires_exact_source_coverage_and_pair_bound_interfaces(
    tmp_path: Path,
) -> None:
    *_, artifact = _run_qa(tmp_path)
    first_plan = artifact.test_plan_items[0]
    duplicate_plan = replace(
        artifact.test_plan_items[1],
        item_id="qa-plan-duplicate-source",
        source_engineering_artifact_digest=first_plan.source_engineering_artifact_digest,
        target_component_ids=first_plan.target_component_ids,
    )
    with pytest.raises(ValueError, match="source coverage"):
        replace(
            artifact,
            test_plan_items=(
                first_plan,
                duplicate_plan,
                *artifact.test_plan_items[2:],
            ),
        )

    first_integration = artifact.integration_test_specs[0]
    unrelated_interface = artifact.sources[2].interface_contract_ids[0]
    with pytest.raises(ValueError, match="crossed its source boundary"):
        replace(
            artifact,
            integration_test_specs=(
                replace(
                    first_integration,
                    interface_contract_ids=(
                        first_integration.interface_contract_ids[0],
                        unrelated_interface,
                    ),
                ),
                artifact.integration_test_specs[1],
            ),
        )


def test_qa_store_rejects_tamper_permission_symlink_and_unknown_entry(
    tmp_path: Path,
) -> None:
    service, *_, artifact = _run_qa(tmp_path)
    path = tmp_path / "qa-state" / artifact.tenant_id / artifact.execution_id / "qa-work-v1.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    os.chmod(path, 0o644)
    with pytest.raises(QAWorkforceCorrupt, match="unsafe"):
        service.get(artifact.tenant_id, artifact.execution_id)

    os.chmod(path, 0o600)
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace(ARTIFACT_STATUS, "QA_APPROVED"), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(QAWorkforceCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)

    path.unlink()
    path.symlink_to(tmp_path / "outside.json")
    with pytest.raises(QAWorkforceCorrupt, match="unsafe"):
        service.get(artifact.tenant_id, artifact.execution_id)

    path.unlink()
    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o600)
    (path.parent / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(QAWorkforceCorrupt, match="not closed"):
        service.get(artifact.tenant_id, artifact.execution_id)


def test_qa_artifact_schema_has_no_workspace_command_or_delivery_effect_fields(
    tmp_path: Path,
) -> None:
    *_, artifact = _run_qa(tmp_path)
    names = {item.name for item in fields(QAWorkArtifact)}
    assert not names.intersection(
        {
            "repository",
            "repository_path",
            "workspace_path",
            "test_files",
            "file_changes",
            "patch",
            "command",
            "test_results",
            "quality_approval",
            "commit_sha",
            "deployment_url",
            "release_id",
        }
    )
    assert all(
        item.execution_state == "NOT_EXECUTED"
        for item in artifact.automated_test_specs + artifact.integration_test_specs
    )
    assert all(item.status == DEFECT_STATUS for item in artifact.defect_reports)
