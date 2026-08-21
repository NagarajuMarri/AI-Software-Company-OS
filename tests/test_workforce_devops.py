from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path

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
from runtime.workforce_security import FileSecurityArtifactStore
from runtime.workforce_devops import (
    ARTIFACT_STATUS,
    DEVOPS_ACTIONS,
    DEVOPS_CAPABILITIES,
    DEVOPS_ROLE,
    EXECUTION_STATE,
    PILOT_STATUS,
    PREVIEW_ENVIRONMENT_CLASS,
    WORK_STATUS,
    DevOpsEngineerProvider,
    DevOpsWorkArtifact,
    DevOpsWorkOrder,
    DevOpsWorkforceCorrupt,
    DevOpsWorkforcePolicyError,
    DevOpsWorkforceService,
    FileDevOpsArtifactStore,
    devops_objective,
)
from tests.test_workforce_leadership import NOW
from tests.test_workforce_security import _run_security


def _devops_twin(**changes) -> DigitalTwinDefinition:
    values = {
        "twin_id": "twin-devops-engineer-1",
        "display_name": "Bounded DevOps Engineer",
        "business_role": DEVOPS_ROLE,
        "provider_id": "deterministic-devops-engineer-v1",
        "capability_ids": DEVOPS_CAPABILITIES,
        "approved_tool_ids": (),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _devops_work_order(architecture, sources, qa_artifact, security_artifact, **changes) -> DevOpsWorkOrder:
    values = {
        "work_order_id": "work-order-devops-engineer-1",
        "tenant_id": architecture.tenant_id,
        "opportunity_id": architecture.opportunity_id,
        "assignment_id": "assignment-devops-engineer-1",
        "business_role": DEVOPS_ROLE,
        "title": "Generic exact-source DevOps preparation assignment",
        "objective": (
            "Prepare CI, isolated preview, migration, deployment, monitoring, and rollback plans"
        ),
        "architecture_artifact_digest": architecture.digest,
        "engineering_artifact_digests": tuple(item.digest for item in sources),
        "qa_artifact_digest": qa_artifact.digest,
        "security_artifact_digest": security_artifact.digest,
        "acceptance_checks": (
            "Every plan binds the exact Architecture, Engineering, QA, and Security sources",
            "CI and preview gates cover customer paths, persistence, tenant isolation, and security",
            "Migration, deployment, monitoring, and rollback preparation remains reversible and reviewable",
            "Every operational action remains NOT_EXECUTED until an authorized isolated workspace exists",
        ),
        "operational_risks": (
            "A stale source, configuration, schema, or environment identity could invalidate evidence",
            "Infrastructure credentials and production boundaries must remain outside this planning assignment",
        ),
        "constraints": (
            "No filesystem, workspace, repository, command, network, infrastructure, credential, or live provider access",
            "No CI execution, provisioning, migration, deployment, monitoring, rollback, promotion, release, or pilot selection",
        ),
        "issued_at": NOW + timedelta(minutes=30),
    }
    values.update(changes)
    return DevOpsWorkOrder(**values)


def _devops_authority(
    work_order: DevOpsWorkOrder,
    architecture,
    sources,
    qa_artifact,
    security_artifact,
    *,
    twin_id: str = "twin-devops-engineer-1",
    **changes,
) -> DelegatedAuthority:
    values = {
        "authority_id": "authority-devops-engineer-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": work_order.tenant_id,
        "assignment_id": work_order.assignment_id,
        "twin_id": twin_id,
        "business_role": DEVOPS_ROLE,
        "objective_digest": hashlib.sha256(
            devops_objective(work_order, architecture, sources, qa_artifact, security_artifact).encode()
        ).hexdigest(),
        "allowed_action_ids": DEVOPS_ACTIONS,
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=4),
        "max_tool_calls": 0,
        "max_output_bytes": 128_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _devops_service(tmp_path: Path, *, provider: DevOpsEngineerProvider | None = None):
    selected = provider or DevOpsEngineerProvider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected,)),
        DigitalTwinToolRegistry(()),
        FileDigitalTwinExecutionStore(tmp_path / "devops-digital-twin-state"),
        clock=lambda: NOW + timedelta(minutes=33),
    )
    service = DevOpsWorkforceService(
        runtime,
        selected,
        FileArchitectureArtifactStore(tmp_path / "architecture-state"),
        FileEngineeringArtifactStore(tmp_path / "engineering-state"),
        FileQAArtifactStore(tmp_path / "qa-state"),
        FileSecurityArtifactStore(tmp_path / "security-state"),
        FileDevOpsArtifactStore(tmp_path / "devops-state"),
        clock=lambda: NOW + timedelta(minutes=32),
    )
    return service, selected


def _run_devops(tmp_path: Path):
    security_run = _run_security(tmp_path)
    _, _, intake, architecture, sources, qa_artifact, _, _, _, security_artifact = security_run
    work_order = _devops_work_order(architecture, sources, qa_artifact, security_artifact)
    twin = _devops_twin()
    authority = _devops_authority(
        work_order, architecture, sources, qa_artifact, security_artifact
    )
    service, provider = _devops_service(tmp_path)
    artifact = service.run(
        execution_id="execution-devops-engineer-1",
        twin=twin,
        authority=authority,
        work_order=work_order,
        architecture=architecture,
        engineering_artifacts=sources,
        qa_artifact=qa_artifact,
        security_artifact=security_artifact,
    )
    return (
        service, provider, intake, architecture, sources, qa_artifact, security_artifact,
        work_order, twin, authority, artifact,
    )


def _devops_sources(tmp_path: Path):
    result = _run_security(tmp_path)
    return result[3], result[4], result[5], result[9]


def test_devops_engineer_produces_six_exact_source_bound_not_executed_plans(tmp_path: Path) -> None:
    service, provider, intake, architecture, sources, qa, security, order, twin, authority, artifact = _run_devops(tmp_path)
    assert provider.execution_count == 1
    assert artifact.business_role is DEVOPS_ROLE
    assert artifact.tenant_id == intake.tenant_id
    assert artifact.work_order_digest == order.digest
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(item.digest for item in sources)
    assert artifact.qa_artifact_digest == qa.digest
    assert artifact.security_artifact_digest == security.digest
    assert artifact.capability_ids == twin.capability_ids == DEVOPS_CAPABILITIES
    assert artifact.action_ids == authority.allowed_action_ids == DEVOPS_ACTIONS
    plans = (
        artifact.ci_pipeline, artifact.preview_environment, artifact.migration_plan,
        artifact.deployment_plan, artifact.monitoring_plan, artifact.rollback_plan,
    )
    assert all(item.execution_state == EXECUTION_STATE for item in plans)
    assert artifact.preview_environment.environment_class == PREVIEW_ENVIRONMENT_CLASS
    assert artifact.deployment_plan.target_environment == PREVIEW_ENVIRONMENT_CLASS
    assert artifact.monitoring_plan.target_environment == PREVIEW_ENVIRONMENT_CLASS
    assert artifact.rollback_plan.target_environment == PREVIEW_ENVIRONMENT_CLASS
    assert artifact.status_report.state == WORK_STATUS
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pilot_status == PILOT_STATUS
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_devops_profile_has_zero_tools_and_no_operational_or_delivery_authority(tmp_path: Path) -> None:
    *_, twin, authority, artifact = _run_devops(tmp_path)[-3:]
    assert twin.approved_tool_ids == authority.allowed_tool_ids == ()
    assert authority.max_tool_calls == 0
    assert authority.live_provider_allowed is False
    for forbidden in (
        USE_ASSIGNED_TOOL, "READ_PRODUCT_WORKSPACE", "CONFIGURE_CI", "PROVISION_INFRASTRUCTURE",
        "RUN_MIGRATION", "DEPLOY", "MONITOR", "ROLLBACK", "PROMOTE", "RELEASE",
        "WRITE_PRODUCT_REPOSITORY", "RUN_COMMAND", "COMMIT", "MERGE", "SELECT_PILOT_PRODUCT",
    ):
        assert forbidden not in artifact.action_ids


def test_exact_retry_and_restart_do_not_repeat_devops_provider_effect(tmp_path: Path) -> None:
    service, provider, _, architecture, sources, qa, security, order, twin, authority, expected = _run_devops(tmp_path)
    again = service.run(
        execution_id=expected.execution_id, twin=twin, authority=authority, work_order=order,
        architecture=architecture, engineering_artifacts=sources, qa_artifact=qa,
        security_artifact=security,
    )
    restarted, restarted_provider = _devops_service(tmp_path)
    reopened = restarted.run(
        execution_id=expected.execution_id, twin=twin, authority=authority, work_order=order,
        architecture=architecture, engineering_artifacts=sources, qa_artifact=qa,
        security_artifact=security,
    )
    assert again == reopened == expected
    assert provider.execution_count == 1
    assert restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "twin_change,authority_change",
    [
        ({"capability_ids": DEVOPS_CAPABILITIES[:-1]}, {}),
        ({"capability_ids": tuple(reversed(DEVOPS_CAPABILITIES))}, {}),
        ({"approved_tool_ids": ("shell",)}, {}),
        ({}, {"allowed_action_ids": DEVOPS_ACTIONS[:-1]}),
        ({}, {"allowed_action_ids": tuple(reversed(DEVOPS_ACTIONS))}),
        ({}, {"allowed_action_ids": DEVOPS_ACTIONS + (USE_ASSIGNED_TOOL,), "allowed_tool_ids": ("shell",), "max_tool_calls": 1}),
        ({}, {"live_provider_allowed": True}),
    ],
)
def test_devops_profile_drift_fails_before_provider_effect(tmp_path: Path, twin_change, authority_change) -> None:
    architecture, sources, qa, security = _devops_sources(tmp_path)
    order = _devops_work_order(architecture, sources, qa, security)
    twin = _devops_twin(**twin_change)
    authority = _devops_authority(order, architecture, sources, qa, security, **authority_change)
    service, provider = _devops_service(tmp_path)
    with pytest.raises(DevOpsWorkforcePolicyError):
        service.run(
            execution_id="execution-devops-drift", twin=twin, authority=authority,
            work_order=order, architecture=architecture, engineering_artifacts=sources,
            qa_artifact=qa, security_artifact=security,
        )
    assert provider.execution_count == 0


def test_devops_rejects_changed_or_reordered_exact_sources_before_provider_effect(tmp_path: Path) -> None:
    architecture, sources, qa, security = _devops_sources(tmp_path)
    order = _devops_work_order(architecture, sources, qa, security)
    twin = _devops_twin()
    authority = _devops_authority(order, architecture, sources, qa, security)
    service, provider = _devops_service(tmp_path)
    for changed_sources, changed_security in (
        (tuple(reversed(sources)), security),
        (sources, replace(security, summary=security.summary + " altered")),
    ):
        with pytest.raises(DevOpsWorkforcePolicyError):
            service.run(
                execution_id="execution-devops-source-drift", twin=twin, authority=authority,
                work_order=order, architecture=architecture, engineering_artifacts=changed_sources,
                qa_artifact=qa, security_artifact=changed_security,
            )
    assert provider.execution_count == 0


class _ExtraOutputProvider(DevOpsEngineerProvider):
    def render(self, request):
        result = super().render(request)
        return ProviderExecutionResult(
            execution_id=result.execution_id, provider_id=result.provider_id,
            request_digest=result.request_digest, status=result.status, summary=result.summary,
            output=result.output + (ContextValue("unexpected_deploy_url", "https://example.invalid"),),
        )


def test_devops_rejects_unknown_provider_output_field(tmp_path: Path) -> None:
    architecture, sources, qa, security = _devops_sources(tmp_path)
    order = _devops_work_order(architecture, sources, qa, security)
    twin = _devops_twin()
    authority = _devops_authority(order, architecture, sources, qa, security)
    service, provider = _devops_service(tmp_path, provider=_ExtraOutputProvider())
    with pytest.raises(DevOpsWorkforcePolicyError, match="not closed"):
        service.run(
            execution_id="execution-devops-extra", twin=twin, authority=authority,
            work_order=order, architecture=architecture, engineering_artifacts=sources,
            qa_artifact=qa, security_artifact=security,
        )
    assert provider.execution_count == 1


def test_devops_models_reject_execution_production_and_pilot_claims(tmp_path: Path) -> None:
    *_, artifact = _run_devops(tmp_path)
    with pytest.raises(ValueError, match="cannot claim execution"):
        replace(artifact.ci_pipeline, execution_state="SUCCEEDED")
    with pytest.raises(ValueError, match="production"):
        replace(artifact.deployment_plan, target_environment="PRODUCTION")
    with pytest.raises(ValueError, match="pilot"):
        replace(artifact, pilot_status="SELECTED")


def test_devops_plans_bind_all_sources_and_data_migration_boundary(tmp_path: Path) -> None:
    *_, sources, qa, security, _, _, _, artifact = _run_devops(tmp_path)[3:]
    digests = tuple(item.digest for item in sources)
    assert artifact.ci_pipeline.source_engineering_artifact_digests == digests
    assert artifact.deployment_plan.source_engineering_artifact_digests == digests
    assert artifact.ci_pipeline.qa_artifact_digest == qa.digest
    assert artifact.ci_pipeline.security_artifact_digest == security.digest
    assert artifact.migration_plan.data_engineering_artifact_digest == sources[-1].digest
    assert set(artifact.migration_plan.target_component_ids) <= set(sources[-1].target_component_ids)
    assert artifact.rollback_plan.deployment_plan_id == artifact.deployment_plan.plan_id
    assert artifact.rollback_plan.migration_plan_id == artifact.migration_plan.plan_id


def test_devops_store_rejects_tamper_permissions_symlink_and_unknown_entry(tmp_path: Path) -> None:
    *_, artifact = _run_devops(tmp_path)
    store = FileDevOpsArtifactStore(tmp_path / "devops-state")
    path = tmp_path / "devops-state" / artifact.tenant_id / artifact.execution_id / "devops-work-v1.json"
    original = path.read_bytes()
    path.chmod(0o644)
    with pytest.raises(DevOpsWorkforceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    path.chmod(0o600)
    payload = json.loads(original)
    payload["record"]["summary"] += " tampered"
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(DevOpsWorkforceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    path.write_bytes(original)
    path.chmod(0o600)
    (path.parent / "unknown.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(DevOpsWorkforceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    (path.parent / "unknown.txt").unlink()
    target = tmp_path / "unsafe-link"
    target.symlink_to(path)
    path.unlink()
    target.rename(path)
    with pytest.raises(DevOpsWorkforceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_devops_artifact_schema_excludes_operational_secrets_and_delivery_receipts(tmp_path: Path) -> None:
    *_, artifact = _run_devops(tmp_path)
    payload = json.dumps(asdict(artifact), default=str).casefold()
    for forbidden in (
        "credential_value", "secret_value", "access_token", "private_key", "connection_string",
        "workspace_path", "repository_url", "commit_sha", "deployment_url", "release_id",
        "infrastructure_resource_id", "production_endpoint",
    ):
        assert forbidden not in payload
    assert EXECUTION_STATE.casefold() in payload
    assert ARTIFACT_STATUS.casefold() in payload
    assert os.stat(
        tmp_path / "devops-state" / artifact.tenant_id / artifact.execution_id / "devops-work-v1.json"
    ).st_mode & 0o777 == 0o600
