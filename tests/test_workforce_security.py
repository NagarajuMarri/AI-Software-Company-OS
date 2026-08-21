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
from runtime.workforce_qa import FileQAArtifactStore
from runtime.workforce_security import (
    ARTIFACT_STATUS,
    EXECUTION_STATE,
    FINDING_STATUS,
    PILOT_STATUS,
    SECURITY_ACTIONS,
    SECURITY_CAPABILITIES,
    SECURITY_ROLE,
    WORK_STATUS,
    FileSecurityArtifactStore,
    SecurityEngineerProvider,
    SecurityWorkArtifact,
    SecurityWorkOrder,
    SecurityWorkforceCorrupt,
    SecurityWorkforcePolicyError,
    SecurityWorkforceService,
    ThreatCategory,
    security_objective,
)
from tests.test_workforce_leadership import NOW
from tests.test_workforce_qa import _run_qa


def _security_twin(**changes) -> DigitalTwinDefinition:
    values = {
        "twin_id": "twin-security-engineer-1",
        "display_name": "Bounded Security Engineer",
        "business_role": SECURITY_ROLE,
        "provider_id": "deterministic-security-engineer-v1",
        "capability_ids": SECURITY_CAPABILITIES,
        "approved_tool_ids": (),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _security_work_order(architecture, sources, qa_artifact, **changes) -> SecurityWorkOrder:
    values = {
        "work_order_id": "work-order-security-engineer-1",
        "tenant_id": architecture.tenant_id,
        "opportunity_id": architecture.opportunity_id,
        "assignment_id": "assignment-security-engineer-1",
        "business_role": SECURITY_ROLE,
        "title": "Generic source-bound Security assignment",
        "objective": (
            "Prepare a STRIDE threat model, dependency-check specifications, "
            "secret-check specifications, and draft security findings"
        ),
        "architecture_artifact_digest": architecture.digest,
        "engineering_artifact_digests": tuple(item.digest for item in sources),
        "qa_artifact_digest": qa_artifact.digest,
        "acceptance_checks": (
            "All STRIDE categories and exact upstream sources are covered",
            "Every Engineering role has dependency and secret check specifications",
            "Findings bind the exact QA artifact and remain draft until authorized validation",
            "No scan, remediation, approval, or product-delivery authority is exercised",
        ),
        "security_risks": (
            "Authority and tenant boundaries could be trusted from client-controlled state",
            "Dependencies, model provenance, and secrets remain unverified without a workspace",
        ),
        "constraints": (
            "No filesystem, product workspace, repository, command, network, or credential access",
            "No scanning, remediation, security approval, DevOps, merge, deployment, release, or pilot selection",
        ),
        "issued_at": NOW + timedelta(minutes=20),
    }
    values.update(changes)
    return SecurityWorkOrder(**values)


def _security_authority(
    work_order: SecurityWorkOrder,
    architecture,
    sources,
    qa_artifact,
    *,
    twin_id: str = "twin-security-engineer-1",
    **changes,
) -> DelegatedAuthority:
    values = {
        "authority_id": "authority-security-engineer-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": work_order.tenant_id,
        "assignment_id": work_order.assignment_id,
        "twin_id": twin_id,
        "business_role": SECURITY_ROLE,
        "objective_digest": hashlib.sha256(
            security_objective(work_order, architecture, sources, qa_artifact).encode()
        ).hexdigest(),
        "allowed_action_ids": SECURITY_ACTIONS,
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=3),
        "max_tool_calls": 0,
        "max_output_bytes": 128_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _security_service(
    tmp_path: Path,
    *,
    provider: SecurityEngineerProvider | None = None,
) -> tuple[SecurityWorkforceService, SecurityEngineerProvider]:
    selected = provider or SecurityEngineerProvider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected,)),
        DigitalTwinToolRegistry(()),
        FileDigitalTwinExecutionStore(tmp_path / "security-digital-twin-state"),
        clock=lambda: NOW + timedelta(minutes=23),
    )
    service = SecurityWorkforceService(
        runtime,
        selected,
        FileArchitectureArtifactStore(tmp_path / "architecture-state"),
        FileEngineeringArtifactStore(tmp_path / "engineering-state"),
        FileQAArtifactStore(tmp_path / "qa-state"),
        FileSecurityArtifactStore(tmp_path / "security-state"),
        clock=lambda: NOW + timedelta(minutes=22),
    )
    return service, selected


def _run_security(tmp_path: Path):
    qa_run = _run_qa(tmp_path)
    _, _, intake, architecture, sources, _, _, _, qa_artifact = qa_run
    work_order = _security_work_order(architecture, sources, qa_artifact)
    twin = _security_twin()
    authority = _security_authority(
        work_order, architecture, sources, qa_artifact
    )
    service, provider = _security_service(tmp_path)
    artifact = service.run(
        execution_id="execution-security-engineer-1",
        twin=twin,
        authority=authority,
        work_order=work_order,
        architecture=architecture,
        engineering_artifacts=sources,
        qa_artifact=qa_artifact,
    )
    return (
        service,
        provider,
        intake,
        architecture,
        sources,
        qa_artifact,
        work_order,
        twin,
        authority,
        artifact,
    )


def _security_sources(tmp_path: Path):
    qa_run = _run_qa(tmp_path)
    return qa_run[3], qa_run[4], qa_run[8]


def test_security_engineer_produces_exact_source_bound_security_artifact(
    tmp_path: Path,
) -> None:
    service, provider, intake, architecture, sources, qa_artifact, order, twin, authority, artifact = (
        _run_security(tmp_path)
    )
    assert provider.execution_count == 1
    assert artifact.business_role is SECURITY_ROLE
    assert artifact.tenant_id == intake.tenant_id
    assert artifact.work_order_digest == order.digest
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(
        item.digest for item in sources
    )
    assert artifact.qa_artifact_digest == qa_artifact.digest
    assert artifact.capability_ids == twin.capability_ids == SECURITY_CAPABILITIES
    assert artifact.action_ids == authority.allowed_action_ids == SECURITY_ACTIONS
    assert tuple(item.category for item in artifact.threats) == tuple(ThreatCategory)
    assert len(artifact.dependency_checks) == 4
    assert len(artifact.secret_checks) == 4
    assert len(artifact.findings) == 3
    assert all(item.validation_state == EXECUTION_STATE for item in artifact.threats)
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.dependency_checks)
    assert all(item.execution_state == EXECUTION_STATE for item in artifact.secret_checks)
    assert all(item.status == FINDING_STATUS for item in artifact.findings)
    assert artifact.status_report.state == WORK_STATUS
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pilot_status == PILOT_STATUS
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_security_profile_has_zero_tools_and_no_remediation_or_delivery_authority(
    tmp_path: Path,
) -> None:
    *_, twin, authority, artifact = _run_security(tmp_path)
    assert twin.approved_tool_ids == authority.allowed_tool_ids == ()
    assert authority.max_tool_calls == 0
    assert authority.live_provider_allowed is False
    for forbidden in (
        "READ_PRODUCT_WORKSPACE", "RUN_DEPENDENCY_SCAN", "RUN_SECRET_SCAN",
        "REMEDIATE_FINDING", "ACCEPT_SECURITY_RISK", "APPROVE_SECURITY",
        "CONFIGURE_CI", "WRITE_DOCUMENTATION", "ORCHESTRATE_AGENTS",
        "WRITE_PRODUCT_REPOSITORY", "RUN_COMMAND", "COMMIT", "MERGE",
        "DEPLOY", "RELEASE", "SELECT_PILOT_PRODUCT",
    ):
        assert forbidden not in artifact.action_ids


def test_exact_retry_and_restart_do_not_repeat_security_provider_effect(
    tmp_path: Path,
) -> None:
    service, provider, _, architecture, sources, qa_artifact, order, twin, authority, artifact = (
        _run_security(tmp_path)
    )
    arguments = {
        "execution_id": artifact.execution_id,
        "twin": twin,
        "authority": authority,
        "work_order": order,
        "architecture": architecture,
        "engineering_artifacts": sources,
        "qa_artifact": qa_artifact,
    }
    assert service.run(**arguments) == artifact
    assert provider.execution_count == 1
    restarted_provider = SecurityEngineerProvider()
    restarted, _ = _security_service(tmp_path, provider=restarted_provider)
    assert restarted.run(**arguments) == artifact
    assert restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "profile_change",
    ["missing-action", "extra-action", "reordered-actions", "missing-capability"],
)
def test_security_requires_exact_ordered_profile_before_provider_effect(
    tmp_path: Path,
    profile_change: str,
) -> None:
    architecture, sources, qa_artifact = _security_sources(tmp_path)
    order = _security_work_order(architecture, sources, qa_artifact)
    twin = _security_twin()
    authority = _security_authority(order, architecture, sources, qa_artifact)
    if profile_change == "missing-action":
        authority = replace(authority, allowed_action_ids=authority.allowed_action_ids[:-1])
    elif profile_change == "extra-action":
        authority = replace(
            authority, allowed_action_ids=authority.allowed_action_ids + ("REMEDIATE_FINDING",)
        )
    elif profile_change == "reordered-actions":
        authority = replace(
            authority, allowed_action_ids=tuple(reversed(authority.allowed_action_ids))
        )
    else:
        twin = _security_twin(capability_ids=SECURITY_CAPABILITIES[:-1])
    service, provider = _security_service(tmp_path)
    with pytest.raises(SecurityWorkforcePolicyError, match="boundary does not match"):
        service.run(
            execution_id=f"execution-invalid-{profile_change}",
            twin=twin,
            authority=authority,
            work_order=order,
            architecture=architecture,
            engineering_artifacts=sources,
            qa_artifact=qa_artifact,
        )
    assert provider.execution_count == 0


@pytest.mark.parametrize(
    "boundary",
    ["wrong-role", "wrong-tenant", "wrong-assignment", "live-provider", "tool"],
)
def test_wrong_security_role_tenant_assignment_live_and_tool_profiles_fail_closed(
    tmp_path: Path,
    boundary: str,
) -> None:
    architecture, sources, qa_artifact = _security_sources(tmp_path)
    order = _security_work_order(architecture, sources, qa_artifact)
    twin = _security_twin()
    authority = _security_authority(order, architecture, sources, qa_artifact)
    if boundary == "wrong-role":
        twin = _security_twin(business_role=AgentRole.DEVOPS_ENGINEER)
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
            allowed_tool_ids=("security-scanner",),
            max_tool_calls=1,
        )
    service, provider = _security_service(tmp_path)
    with pytest.raises(SecurityWorkforcePolicyError):
        service.run(
            execution_id=f"execution-invalid-{boundary}",
            twin=twin,
            authority=authority,
            work_order=order,
            architecture=architecture,
            engineering_artifacts=sources,
            qa_artifact=qa_artifact,
        )
    assert provider.execution_count == 0


@pytest.mark.parametrize(
    "source_change",
    ["reordered-engineering", "changed-engineering", "changed-qa", "wrong-work-order-qa"],
)
def test_security_requires_exact_persisted_architecture_engineering_and_qa_sources(
    tmp_path: Path,
    source_change: str,
) -> None:
    architecture, sources, qa_artifact = _security_sources(tmp_path)
    order = _security_work_order(architecture, sources, qa_artifact)
    if source_change == "reordered-engineering":
        sources = (sources[1], sources[0], *sources[2:])
    elif source_change == "changed-engineering":
        sources = (replace(sources[0], title="Changed source"), *sources[1:])
        order = _security_work_order(architecture, sources, qa_artifact)
    elif source_change == "changed-qa":
        qa_artifact = replace(qa_artifact, title="Changed QA source")
        order = _security_work_order(architecture, sources, qa_artifact)
    else:
        order = replace(order, qa_artifact_digest="f" * 64)
    twin = _security_twin()
    authority = _security_authority(order, architecture, sources, qa_artifact)
    service, provider = _security_service(tmp_path)
    with pytest.raises(SecurityWorkforcePolicyError, match="exact|persisted"):
        service.run(
            execution_id=f"execution-source-{source_change}",
            twin=twin,
            authority=authority,
            work_order=order,
            architecture=architecture,
            engineering_artifacts=sources,
            qa_artifact=qa_artifact,
        )
    assert provider.execution_count == 0


def test_unknown_security_provider_output_is_rejected(tmp_path: Path) -> None:
    architecture, sources, qa_artifact = _security_sources(tmp_path)
    order = _security_work_order(architecture, sources, qa_artifact)
    twin = _security_twin()
    authority = _security_authority(order, architecture, sources, qa_artifact)
    provider = SecurityEngineerProvider()
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
    service, _ = _security_service(tmp_path, provider=provider)
    with pytest.raises(SecurityWorkforcePolicyError, match="not closed"):
        service.run(
            execution_id="execution-invalid-output",
            twin=twin,
            authority=authority,
            work_order=order,
            architecture=architecture,
            engineering_artifacts=sources,
            qa_artifact=qa_artifact,
        )


@pytest.mark.parametrize(
    "corruption",
    ["cross-source", "claimed-scan", "changed-qa-binding", "elevated-finding"],
)
def test_nested_security_provider_output_must_match_closed_typed_schema(
    tmp_path: Path,
    corruption: str,
) -> None:
    architecture, sources, qa_artifact = _security_sources(tmp_path)
    order = _security_work_order(architecture, sources, qa_artifact)
    twin = _security_twin()
    authority = _security_authority(order, architecture, sources, qa_artifact)
    provider = SecurityEngineerProvider()
    original = provider.render

    def invalid(request):
        result = original(request)
        output = list(result.output)
        key = "dependency_backend_json"
        if corruption == "changed-qa-binding" or corruption == "elevated-finding":
            key = "finding_authority_json"
        for index, item in enumerate(output):
            if item.key != key:
                continue
            value = json.loads(item.value)
            if corruption == "cross-source":
                value[0]["target_component_ids"] = ["not-owned-component"]
            elif corruption == "claimed-scan":
                value[0]["execution_state"] = "PASSED"
            elif corruption == "changed-qa-binding":
                value[0]["qa_artifact_digest"] = "a" * 64
            else:
                value[0]["status"] = "SECURITY_APPROVED"
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
    service, _ = _security_service(tmp_path, provider=provider)
    with pytest.raises(SecurityWorkforcePolicyError, match="typed validation"):
        service.run(
            execution_id=f"execution-invalid-{corruption}",
            twin=twin,
            authority=authority,
            work_order=order,
            architecture=architecture,
            engineering_artifacts=sources,
            qa_artifact=qa_artifact,
        )


def test_security_models_cannot_claim_scan_approve_or_select_pilot(tmp_path: Path) -> None:
    *_, order, _, _, artifact = _run_security(tmp_path)
    with pytest.raises(ValueError, match="cannot claim"):
        replace(artifact.dependency_checks[0], execution_state="PASSED")
    with pytest.raises(ValueError, match="authorized workspace"):
        replace(artifact, status="SECURITY_APPROVED")
    with pytest.raises(ValueError, match="cannot select"):
        replace(artifact, pilot_status="SELECTED")
    with pytest.raises(ValueError, match="Security Engineer"):
        replace(order, business_role=AgentRole.QA_ENGINEER)


def test_security_artifact_requires_exact_check_coverage_and_source_bound_threats(
    tmp_path: Path,
) -> None:
    *_, artifact = _run_security(tmp_path)
    duplicate = replace(
        artifact.dependency_checks[1],
        check_id="security-dependency-duplicate",
        source_engineering_artifact_digest=artifact.dependency_checks[0].source_engineering_artifact_digest,
        target_component_ids=artifact.dependency_checks[0].target_component_ids,
    )
    with pytest.raises(ValueError, match="source coverage"):
        replace(
            artifact,
            dependency_checks=(
                artifact.dependency_checks[0],
                duplicate,
                *artifact.dependency_checks[2:],
            ),
        )
    with pytest.raises(ValueError, match="component boundary"):
        replace(
            artifact,
            threats=(
                replace(
                    artifact.threats[0],
                    target_component_ids=("not-owned-component",),
                ),
                *artifact.threats[1:],
            ),
        )


def test_security_store_rejects_tamper_permission_symlink_and_unknown_entry(
    tmp_path: Path,
) -> None:
    service, *_, artifact = _run_security(tmp_path)
    path = (
        tmp_path
        / "security-state"
        / artifact.tenant_id
        / artifact.execution_id
        / "security-work-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    os.chmod(path, 0o644)
    with pytest.raises(SecurityWorkforceCorrupt, match="unsafe"):
        service.get(artifact.tenant_id, artifact.execution_id)
    os.chmod(path, 0o600)
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace(ARTIFACT_STATUS, "SECURITY_APPROVED"), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(SecurityWorkforceCorrupt):
        service.get(artifact.tenant_id, artifact.execution_id)
    path.unlink()
    path.symlink_to(tmp_path / "outside.json")
    with pytest.raises(SecurityWorkforceCorrupt, match="unsafe"):
        service.get(artifact.tenant_id, artifact.execution_id)
    path.unlink()
    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o600)
    (path.parent / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SecurityWorkforceCorrupt, match="not closed"):
        service.get(artifact.tenant_id, artifact.execution_id)


def test_security_artifact_schema_has_no_workspace_scan_remediation_or_delivery_fields(
    tmp_path: Path,
) -> None:
    *_, artifact = _run_security(tmp_path)
    names = {item.name for item in fields(SecurityWorkArtifact)}
    assert not names.intersection(
        {
            "repository", "repository_path", "workspace_path", "file_changes",
            "dependency_results", "secret_values", "scan_command", "remediation_patch",
            "risk_acceptance", "security_approval", "commit_sha", "deployment_url", "release_id",
        }
    )
    assert all(item.validation_state == EXECUTION_STATE for item in artifact.threats)
    assert all(
        item.execution_state == EXECUTION_STATE
        for item in artifact.dependency_checks + artifact.secret_checks
    )
    assert all(item.status == FINDING_STATUS for item in artifact.findings)
