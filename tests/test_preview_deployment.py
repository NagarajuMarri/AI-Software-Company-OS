from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from runtime.github_delivery import FileGitHubDeliveryArtifactStore
from runtime.preview_deployment import (
    ARTIFACT_STATUS,
    DEPLOYMENT_STATE,
    ENVIRONMENT_STATE,
    MIGRATION_STATE,
    MONITORING_STATE,
    PILOT_STATUS,
    PREVIEW_DEPLOYMENT_ACTIONS,
    PREVIEW_DEPLOYMENT_CAPABILITIES,
    PREVIEW_DEPLOYMENT_TOOL_IDS,
    PRODUCTION_STATE,
    PULL_REQUEST_STATE,
    ROLLBACK_STATE,
    SOURCE_STATE,
    ControlledPreviewDeploymentProvider,
    DeterministicPreviewPlatformGateway,
    FilePreviewDeploymentArtifactStore,
    PreviewDeploymentAuthority,
    PreviewDeploymentConflict,
    PreviewDeploymentCorrupt,
    PreviewDeploymentObservation,
    PreviewDeploymentPolicyError,
    PreviewDeploymentReconciliationRequired,
    PreviewDeploymentService,
    PreviewDeploymentWorkOrder,
    canonical_digest,
)
from runtime.workforce_devops import FileDevOpsArtifactStore, PREVIEW_ENVIRONMENT_CLASS
from tests.test_github_delivery import _run_delivery
from tests.test_workforce_leadership import NOW


PREVIEW_URL = "https://fixture-1.preview.invalid"
HEALTH_URLS = (
    f"{PREVIEW_URL}/health",
    f"{PREVIEW_URL}/ready",
)


def _plan_digest(value) -> str:  # noqa: ANN001
    return canonical_digest(asdict(value))


def _work_order(delivery, devops, **changes) -> PreviewDeploymentWorkOrder:  # noqa: ANN001
    values = {
        "work_order_id": "work-order-preview-deployment-1",
        "tenant_id": delivery.tenant_id,
        "opportunity_id": delivery.opportunity_id,
        "assignment_id": "assignment-preview-deployment-1",
        "github_delivery_artifact_digest": delivery.digest,
        "devops_artifact_digest": devops.digest,
        "repository_id": delivery.repository_id,
        "repository_full_name": delivery.repository_full_name,
        "feature_branch": delivery.feature_branch,
        "approved_commit": delivery.commit_sha,
        "approved_tree": delivery.commit_tree,
        "draft_pull_request_number": delivery.pull_request.number,
        "draft_pull_request_digest": delivery.pull_request.digest,
        "preview_environment_id": "preview-environment-fixture-1",
        "preview_url": PREVIEW_URL,
        "preview_plan_digest": _plan_digest(devops.preview_environment),
        "migration_plan_digest": _plan_digest(devops.migration_plan),
        "deployment_plan_digest": _plan_digest(devops.deployment_plan),
        "monitoring_plan_digest": _plan_digest(devops.monitoring_plan),
        "rollback_plan_digest": _plan_digest(devops.rollback_plan),
        "configuration_digest": hashlib.sha256(b"generic-preview-config-v1").hexdigest(),
        "secret_reference_ids": (
            "preview-database-reference",
            "preview-session-reference",
        ),
        "health_check_urls": HEALTH_URLS,
        "objectives": (
            "Verify the exact persisted Day 33 delivery and Day 28 operational plans",
            "Deploy only the explicitly approved commit to one isolated preview",
            "Apply preview-only migration preparation and verify declared health checks",
            "Enable preview monitoring and retain rollback readiness",
        ),
        "acceptance_checks": (
            "The Day 33 delivery artifact is exact persisted state",
            "The matching Day 28 DevOps plans are exact persisted state",
            "The feature branch, draft PR, commit, and tree remain unchanged",
            "The deployment target is isolated and non-production",
            "Only opaque secret references cross the platform boundary",
            "Exactly one preview deployment and migration occur",
            "Every declared health endpoint returns HTTP 200",
            "Preview monitoring is enabled and rollback remains unexecuted",
            "No merge, production deployment, release, billing, or pilot selection occurs",
        ),
        "constraints": (
            "One generic fixture only and no official pilot selection",
            "One create-only isolated preview environment",
            "No raw credential or secret value",
            "No general infrastructure command or unapproved network access",
            "No pull-request approval or merge",
            "No production deployment or promotion",
            "No release, billing, budget, or risk acceptance",
            "No Day 35 runtime-acceptance journey",
        ),
        "issued_at": NOW + timedelta(minutes=96),
        "expires_at": NOW + timedelta(hours=8),
        "preview_ttl_minutes": 120,
    }
    values.update(changes)
    return PreviewDeploymentWorkOrder(**values)


def _authority(order: PreviewDeploymentWorkOrder, **changes) -> PreviewDeploymentAuthority:
    values = {
        "authority_id": "authority-preview-deployment-1",
        "issuer_id": "founder-preview-deployment-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "work_order_digest": order.digest,
        "github_delivery_artifact_digest": order.github_delivery_artifact_digest,
        "devops_artifact_digest": order.devops_artifact_digest,
        "repository_id": order.repository_id,
        "approved_commit": order.approved_commit,
        "preview_environment_id": order.preview_environment_id,
        "allowed_action_ids": PREVIEW_DEPLOYMENT_ACTIONS,
        "allowed_tool_ids": PREVIEW_DEPLOYMENT_TOOL_IDS,
        "issued_at": NOW + timedelta(minutes=97),
        "expires_at": NOW + timedelta(hours=8),
        "max_platform_calls": 6,
        "max_health_checks": 4,
        "max_secret_references": 4,
    }
    values.update(changes)
    return PreviewDeploymentAuthority(**values)


def _service(tmp_path: Path, provider) -> PreviewDeploymentService:  # noqa: ANN001
    return PreviewDeploymentService(
        provider,
        FileGitHubDeliveryArtifactStore(tmp_path / "github-delivery-state"),
        FileDevOpsArtifactStore(tmp_path / "devops-state"),
        FilePreviewDeploymentArtifactStore(tmp_path / "preview-deployment-state"),
        clock=lambda: NOW + timedelta(minutes=105),
    )


def _fixture(tmp_path: Path, gateway=None):  # noqa: ANN001
    *_, delivery = _run_delivery(tmp_path)
    devops = FileDevOpsArtifactStore(tmp_path / "devops-state").load(
        delivery.tenant_id, "execution-devops-engineer-1"
    )
    order = _work_order(delivery, devops)
    authority = _authority(order)
    selected_gateway = gateway or DeterministicPreviewPlatformGateway(
        clock=lambda: NOW + timedelta(minutes=104)
    )
    provider = ControlledPreviewDeploymentProvider(selected_gateway)
    service = _service(tmp_path, provider)
    return service, provider, selected_gateway, delivery, devops, order, authority


def _run_preview(tmp_path: Path, gateway=None):  # noqa: ANN001
    values = _fixture(tmp_path, gateway)
    service, provider, selected_gateway, delivery, devops, order, authority = values
    artifact = service.run(
        execution_id="execution-preview-deployment-1",
        work_order=order,
        authority=authority,
        github_delivery_artifact=delivery,
        devops_artifact=devops,
    )
    return (*values, artifact)


def test_preview_deploys_exact_approved_commit_once_and_reports_healthy(tmp_path: Path) -> None:
    service, provider, gateway, delivery, devops, order, _, artifact = _run_preview(tmp_path)
    assert provider.execution_count == 1
    assert (gateway.find_count, gateway.deploy_count, gateway.inspect_count) == (1, 1, 1)
    assert artifact.github_delivery_artifact_digest == delivery.digest
    assert artifact.devops_artifact_digest == devops.digest
    assert artifact.approved_commit == artifact.deployed_commit == delivery.commit_sha
    assert artifact.approved_tree == artifact.deployed_tree == delivery.commit_tree
    assert artifact.preview_environment_id == order.preview_environment_id
    assert artifact.preview_url == PREVIEW_URL
    assert tuple(item.url for item in artifact.health_receipts) == HEALTH_URLS
    assert all(item.status_code == 200 for item in artifact.health_receipts)
    assert artifact.capability_ids == PREVIEW_DEPLOYMENT_CAPABILITIES
    assert artifact.action_ids == PREVIEW_DEPLOYMENT_ACTIONS
    assert artifact.tool_ids == PREVIEW_DEPLOYMENT_TOOL_IDS
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_preview_source_chain_and_terminal_states_are_exact(tmp_path: Path) -> None:
    *_, artifact = _run_preview(tmp_path)
    assert artifact.source_state == SOURCE_STATE
    assert artifact.pull_request_state == PULL_REQUEST_STATE
    assert artifact.environment_state == ENVIRONMENT_STATE
    assert artifact.deployment_state == DEPLOYMENT_STATE
    assert artifact.migration_state == MIGRATION_STATE
    assert artifact.monitoring_state == MONITORING_STATE
    assert artifact.rollback_state == ROLLBACK_STATE
    assert artifact.production_state == PRODUCTION_STATE
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS
    assert (artifact.deployment_count, artifact.migration_count) == (1, 1)
    assert artifact.monitoring_configuration_count == 1
    assert artifact.rollback_count == artifact.production_deployment_count == 0
    assert artifact.merge_count == artifact.release_count == artifact.billing_count == 0


def test_exact_retry_and_restart_do_not_repeat_platform_effect(tmp_path: Path) -> None:
    service, provider, gateway, delivery, devops, order, authority, expected = _run_preview(tmp_path)
    kwargs = dict(
        execution_id=expected.execution_id,
        work_order=order,
        authority=authority,
        github_delivery_artifact=delivery,
        devops_artifact=devops,
    )
    assert service.run(**kwargs) == expected
    restarted_gateway = DeterministicPreviewPlatformGateway()
    restarted_provider = ControlledPreviewDeploymentProvider(restarted_gateway)
    restarted = _service(tmp_path, restarted_provider)
    assert restarted.run(**kwargs) == expected
    assert provider.execution_count == 1 and restarted_provider.execution_count == 0
    assert gateway.deploy_count == 1 and restarted_gateway.deploy_count == 0


def test_changed_retry_conflicts_without_another_platform_effect(tmp_path: Path) -> None:
    service, provider, gateway, delivery, devops, order, _, artifact = _run_preview(tmp_path)
    changed = replace(order, preview_ttl_minutes=180)
    with pytest.raises(PreviewDeploymentConflict):
        service.run(
            execution_id=artifact.execution_id,
            work_order=changed,
            authority=_authority(changed),
            github_delivery_artifact=delivery,
            devops_artifact=devops,
        )
    assert provider.execution_count == gateway.deploy_count == 1


@pytest.mark.parametrize(
    "change",
    (
        {"assignment_id": "wrong-assignment"},
        {"repository_id": "wrong-repository"},
        {"approved_commit": "f" * 40},
        {"preview_environment_id": "wrong-environment"},
        {"github_delivery_artifact_digest": "0" * 64},
        {"devops_artifact_digest": "1" * 64},
    ),
)
def test_authority_drift_fails_before_platform_effect(tmp_path: Path, change) -> None:
    service, provider, gateway, delivery, devops, order, authority = _fixture(tmp_path)
    with pytest.raises(PreviewDeploymentPolicyError):
        service.run(
            execution_id="execution-invalid-preview-authority",
            work_order=order,
            authority=replace(authority, **change),
            github_delivery_artifact=delivery,
            devops_artifact=devops,
        )
    assert provider.execution_count == gateway.deploy_count == 0


def test_expired_authority_fails_before_platform_effect(tmp_path: Path) -> None:
    service, provider, gateway, delivery, devops, order, _ = _fixture(tmp_path)
    authority = _authority(
        order,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=100),
    )
    with pytest.raises(PreviewDeploymentPolicyError):
        service.run(
            execution_id="execution-expired-preview-authority",
            work_order=order,
            authority=authority,
            github_delivery_artifact=delivery,
            devops_artifact=devops,
        )
    assert provider.execution_count == gateway.deploy_count == 0


def test_unpersisted_or_changed_day33_source_fails_before_platform(tmp_path: Path) -> None:
    service, provider, gateway, delivery, devops, order, authority = _fixture(tmp_path)
    changed = replace(delivery, execution_id="execution-github-delivery-other")
    with pytest.raises(PreviewDeploymentPolicyError):
        service.run(
            execution_id="execution-changed-day33-source",
            work_order=order,
            authority=authority,
            github_delivery_artifact=changed,
            devops_artifact=devops,
        )
    assert provider.execution_count == gateway.deploy_count == 0


def test_changed_devops_plan_binding_fails_before_platform(tmp_path: Path) -> None:
    service, provider, gateway, delivery, devops, order, _ = _fixture(tmp_path)
    changed = replace(order, monitoring_plan_digest="9" * 64)
    with pytest.raises(PreviewDeploymentPolicyError):
        service.run(
            execution_id="execution-changed-devops-plan",
            work_order=changed,
            authority=_authority(changed),
            github_delivery_artifact=delivery,
            devops_artifact=devops,
        )
    assert provider.execution_count == gateway.deploy_count == 0


def test_existing_preview_requires_reconciliation_without_second_deploy(tmp_path: Path) -> None:
    service, provider, gateway, delivery, devops, order, authority = _fixture(tmp_path)
    gateway.deploy(
        environment_id=order.preview_environment_id,
        preview_url=order.preview_url,
        repository_full_name=order.repository_full_name,
        feature_branch=order.feature_branch,
        approved_commit=order.approved_commit,
        approved_tree=order.approved_tree,
        configuration_digest=order.configuration_digest,
        secret_reference_ids=order.secret_reference_ids,
        health_check_urls=order.health_check_urls,
    )
    with pytest.raises(PreviewDeploymentReconciliationRequired):
        service.run(
            execution_id="execution-existing-preview",
            work_order=order,
            authority=authority,
            github_delivery_artifact=delivery,
            devops_artifact=devops,
        )
    assert provider.execution_count == 1 and gateway.deploy_count == 1


class _FailingInspectGateway(DeterministicPreviewPlatformGateway):
    def inspect(self, environment_id: str) -> PreviewDeploymentObservation:
        del environment_id
        raise PreviewDeploymentPolicyError("simulated post-deployment inspection failure")


class _FailingFindGateway(DeterministicPreviewPlatformGateway):
    def find(self, environment_id: str) -> PreviewDeploymentObservation | None:
        del environment_id
        raise RuntimeError("sensitive provider lookup detail")


def test_lookup_failure_is_redacted_and_stops_before_deployment(tmp_path: Path) -> None:
    gateway = _FailingFindGateway(clock=lambda: NOW + timedelta(minutes=104))
    service, provider, _, delivery, devops, order, authority = _fixture(tmp_path, gateway)
    with pytest.raises(PreviewDeploymentPolicyError, match="lookup failed before deployment"):
        service.run(
            execution_id="execution-preview-lookup-failure",
            work_order=order,
            authority=authority,
            github_delivery_artifact=delivery,
            devops_artifact=devops,
        )
    assert provider.execution_count == 1 and gateway.deploy_count == 0


def test_post_deployment_failure_requires_human_reconciliation(tmp_path: Path) -> None:
    gateway = _FailingInspectGateway(clock=lambda: NOW + timedelta(minutes=104))
    service, provider, _, delivery, devops, order, authority = _fixture(tmp_path, gateway)
    with pytest.raises(PreviewDeploymentReconciliationRequired):
        service.run(
            execution_id="execution-preview-partial",
            work_order=order,
            authority=authority,
            github_delivery_artifact=delivery,
            devops_artifact=devops,
        )
    assert provider.execution_count == gateway.deploy_count == 1


def test_persistence_is_mode_0600_and_tamper_evident(tmp_path: Path) -> None:
    *_, artifact = _run_preview(tmp_path)
    path = (
        tmp_path
        / "preview-deployment-state"
        / artifact.tenant_id
        / artifact.execution_id
        / "preview-deployment-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = json.loads(path.read_text())
    envelope["record"]["production_deployment_count"] = 1
    path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    os.chmod(path, 0o600)
    store = FilePreviewDeploymentArtifactStore(tmp_path / "preview-deployment-state")
    with pytest.raises(PreviewDeploymentCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_persistence_rejects_unknown_entries_permissions_and_escape(tmp_path: Path) -> None:
    *_, artifact = _run_preview(tmp_path)
    directory = (
        tmp_path / "preview-deployment-state" / artifact.tenant_id / artifact.execution_id
    )
    path = directory / "preview-deployment-v1.json"
    (directory / "unexpected.txt").write_text("unsafe", encoding="utf-8")
    store = FilePreviewDeploymentArtifactStore(tmp_path / "preview-deployment-state")
    with pytest.raises(PreviewDeploymentCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    (directory / "unexpected.txt").unlink()
    os.chmod(path, 0o644)
    with pytest.raises(PreviewDeploymentCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    with pytest.raises(PreviewDeploymentCorrupt):
        store.load("../tenant", "execution")


def test_models_reject_production_or_elevated_preview_authority(tmp_path: Path) -> None:
    *_, order, _ = _fixture(tmp_path)[-2:]
    with pytest.raises(ValueError):
        replace(order, preview_url="https://preview.example.com")
    with pytest.raises(ValueError):
        replace(order, environment_class="PRODUCTION")
    with pytest.raises(ValueError):
        replace(order, feature_branch="main")
    with pytest.raises(ValueError):
        _authority(order, production_deployment_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, merge_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, release_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, billing_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, pilot_selection_allowed=True)


def test_preview_profile_contains_no_production_merge_release_or_day35_action(tmp_path: Path) -> None:
    *_, artifact = _run_preview(tmp_path)
    for forbidden in (
        "DEPLOY_PRODUCTION",
        "PROMOTE_TO_PRODUCTION",
        "APPROVE_PULL_REQUEST",
        "MERGE_PULL_REQUEST",
        "RELEASE",
        "BILL_CUSTOMER",
        "SELECT_PILOT_PRODUCT",
        "RUN_COMPLETE_RUNTIME_ACCEPTANCE",
    ):
        assert forbidden not in artifact.action_ids
    assert artifact.environment_class == PREVIEW_ENVIRONMENT_CLASS
