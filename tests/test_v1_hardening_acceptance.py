from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import stat

import pytest

from runtime.v1_hardening_acceptance import (
    ARTIFACT_STATUS,
    DOCUMENTATION_IDS,
    FOUNDER_UAT_STATUS,
    HARDENING_CONTROL_IDS,
    HARDENING_CONTROL_STATES,
    MONITORING_SIGNAL_IDS,
    PRODUCTION_STATE,
    RELEASE_STATE,
    V1_HARDENING_ACTIONS,
    V1_HARDENING_CAPABILITIES,
    V1_HARDENING_TOOL_IDS,
    ControlledV1HardeningProvider,
    FileV1HardeningAcceptanceArtifactStore,
    OfflineV1HardeningProvider,
    V1HardeningAuthority,
    V1HardeningConflict,
    V1HardeningCorrupt,
    V1HardeningNotFound,
    V1HardeningPolicyError,
    V1HardeningProvider,
    V1HardeningAcceptanceService,
    V1HardeningWorkOrder,
    hardening_policy_digests_for,
)
from tests.test_end_to_end_product_pilot import _run_pilot
from tests.test_workforce_leadership import NOW


def _work_order(pilot, **changes):  # noqa: ANN001
    values = {
        "work_order_id": "work-order-ascos-v1-hardening-1",
        "tenant_id": pilot.tenant_id,
        "assignment_id": "assignment-ascos-v1-hardening-1",
        "pilot_id": pilot.pilot_id,
        "source_pilot_execution_id": pilot.execution_id,
        "source_pilot_artifact_digest": pilot.digest,
        "repository_full_name": pilot.repository_full_name,
        "feature_branch": pilot.feature_branch,
        "approved_commit": pilot.approved_commit,
        "approved_tree": pilot.approved_tree,
        "draft_pull_request_number": pilot.draft_pull_request_number,
        "preview_url": pilot.preview_url,
        "journey_ids": pilot.journey_ids,
        "control_source_digests": hardening_policy_digests_for(pilot.digest),
        "monitoring_signal_ids": MONITORING_SIGNAL_IDS,
        "documentation_ids": DOCUMENTATION_IDS,
        "objectives": (
            "Verify the exact completed Day 36 product pilot",
            "Verify security, backup, recovery, audit, and monitoring controls",
            "Bind the complete V1 documentation package",
            "Prepare real-browser evidence for founder UAT",
        ),
        "acceptance_checks": (
            "Day 36 source artifact is exact and persisted",
            "Security baseline retains zero elevated effects",
            "One canonical backup copy verifies exactly",
            "One explicit recovery drill returns exact state",
            "Seven control receipts form one audit chain",
            "Five operational monitoring signals are healthy",
            "Seven required documentation records are bound",
            "All four end-user journeys remain ready for founder UAT",
            "Founder acceptance, release, and production remain blocked",
        ),
        "constraints": (
            "Use only the exact persisted Day 36 pilot",
            "Do not write or mutate a product repository",
            "Do not update, approve, close, or merge a pull request",
            "Do not mutate a preview environment",
            "Do not deploy or promote production",
            "Do not release or publish ASCOS V1",
            "Do not bill, spend budget, or accept risk",
            "Do not self-record subjective founder acceptance",
        ),
        "issued_at": NOW + timedelta(minutes=180),
        "expires_at": NOW + timedelta(hours=8),
    }
    values.update(changes)
    return V1HardeningWorkOrder(**values)


def _authority(order: V1HardeningWorkOrder, **changes):
    values = {
        "authority_id": "authority-ascos-v1-hardening-1",
        "issuer_id": "founder-day37-start-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "pilot_id": order.pilot_id,
        "work_order_digest": order.digest,
        "source_pilot_artifact_digest": order.source_pilot_artifact_digest,
        "control_source_digests": order.control_source_digests,
        "allowed_action_ids": V1_HARDENING_ACTIONS,
        "allowed_tool_ids": V1_HARDENING_TOOL_IDS,
        "issued_at": NOW + timedelta(minutes=180),
        "expires_at": NOW + timedelta(hours=8),
    }
    values.update(changes)
    return V1HardeningAuthority(**values)


def _fixture(tmp_path: Path, *, browser_provider=None, provider=None, clock=None):  # noqa: ANN001
    pilot_values = _run_pilot(tmp_path, browser_provider)
    pilot = pilot_values[-1]
    order = _work_order(pilot)
    authority = _authority(order)
    inner = provider or OfflineV1HardeningProvider(clock=lambda: NOW + timedelta(minutes=181))
    controlled = ControlledV1HardeningProvider(inner)
    store = FileV1HardeningAcceptanceArtifactStore(tmp_path / "v1-hardening-state")
    service = V1HardeningAcceptanceService(
        controlled,
        pilot_values[3],
        store,
        clock=clock or (lambda: NOW + timedelta(minutes=181)),
    )
    return service, controlled, inner, store, pilot, order, authority, pilot_values


def _run_hardening(tmp_path: Path, *, browser_provider=None):  # noqa: ANN001
    values = _fixture(tmp_path, browser_provider=browser_provider)
    service, _, _, _, pilot, order, authority, _ = values
    artifact = service.run(
        execution_id="execution-ascos-v1-hardening-1",
        work_order=order,
        authority=authority,
        pilot=pilot,
    )
    return (*values, artifact)


def test_v1_hardening_binds_all_final_controls(tmp_path: Path) -> None:
    *values, artifact = _run_hardening(tmp_path)
    controlled, inner = values[1], values[2]
    assert controlled.execution_count == inner.calls == 1
    assert tuple(item.control_id for item in artifact.control_receipts) == HARDENING_CONTROL_IDS
    assert tuple(item.state for item in artifact.control_receipts) == HARDENING_CONTROL_STATES
    assert tuple(item.signal_id for item in artifact.monitoring_receipts) == MONITORING_SIGNAL_IDS
    assert artifact.documentation_ids == DOCUMENTATION_IDS
    assert artifact.governance_capability_ids == V1_HARDENING_CAPABILITIES


def test_v1_hardening_preserves_exact_day36_source_chain(tmp_path: Path) -> None:
    *values, artifact = _run_hardening(tmp_path)
    pilot = values[4]
    assert artifact.source_pilot_artifact_digest == pilot.digest
    assert artifact.security_artifact_digest == pilot.security_artifact_digest
    assert artifact.devops_artifact_digest == pilot.devops_artifact_digest
    assert artifact.runtime_acceptance_artifact_digest == pilot.runtime_acceptance_artifact_digest
    assert artifact.approved_commit == pilot.approved_commit
    assert artifact.approved_tree == pilot.approved_tree
    assert artifact.journey_ids == pilot.journey_ids


def test_terminal_state_is_truthful_and_release_blocked(tmp_path: Path) -> None:
    *_, artifact = _run_hardening(tmp_path)
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.founder_uat_status == FOUNDER_UAT_STATUS
    assert artifact.release_state == RELEASE_STATE
    assert artifact.production_state == PRODUCTION_STATE
    assert artifact.backup_copy_count == artifact.recovery_drill_count == 1
    assert artifact.audit_entry_count == artifact.documentation_record_count == 7
    assert artifact.monitoring_signal_count == 5
    assert artifact.founder_uat_journey_count == 4
    assert artifact.founder_acceptance_count == 0


def test_no_external_or_elevated_effect_is_recorded(tmp_path: Path) -> None:
    *_, artifact = _run_hardening(tmp_path)
    assert artifact.repository_write_count == artifact.pull_request_mutation_count == 0
    assert artifact.merge_count == artifact.production_deployment_count == 0
    assert artifact.release_count == artifact.billing_count == 0
    assert artifact.risk_acceptance_count == artifact.founder_acceptance_count == 0


def test_exact_retry_and_restart_do_not_execute_provider_again(tmp_path: Path) -> None:
    *values, first = _run_hardening(tmp_path)
    service, controlled, inner, _, pilot, order, authority = values[:7]
    second = service.run(
        execution_id=first.execution_id,
        work_order=order,
        authority=authority,
        pilot=pilot,
    )
    assert second == first
    assert controlled.execution_count == inner.calls == 1
    assert service.get(first.tenant_id, first.execution_id) == first


def test_retry_with_changed_authority_conflicts(tmp_path: Path) -> None:
    *values, artifact = _run_hardening(tmp_path)
    service, _, _, _, pilot, order, authority = values[:7]
    changed = replace(authority, authority_id="authority-ascos-v1-hardening-2")
    with pytest.raises(V1HardeningConflict):
        service.run(
            execution_id=artifact.execution_id,
            work_order=order,
            authority=changed,
            pilot=pilot,
        )


def test_unpersisted_day36_pilot_fails_before_provider(tmp_path: Path) -> None:
    service, controlled, _, _, pilot, order, authority, _ = _fixture(tmp_path)
    changed = replace(pilot, security_artifact_digest="f" * 64)
    with pytest.raises(V1HardeningPolicyError, match="exact persisted"):
        service.run(
            execution_id="execution-ascos-v1-hardening-1",
            work_order=order,
            authority=authority,
            pilot=changed,
        )
    assert controlled.execution_count == 0


def test_changed_hardening_contract_fails_before_provider(tmp_path: Path) -> None:
    service, controlled, _, _, pilot, order, _, _ = _fixture(tmp_path)
    changed_digests = ("f" * 64, *order.control_source_digests[1:])
    changed_order = replace(order, control_source_digests=changed_digests)
    changed_authority = _authority(changed_order)
    with pytest.raises(V1HardeningPolicyError, match="contract digest"):
        service.run(
            execution_id="execution-ascos-v1-hardening-1",
            work_order=changed_order,
            authority=changed_authority,
            pilot=pilot,
        )
    assert controlled.execution_count == 0


class _WrongSnapshotProvider(V1HardeningProvider):
    provider_id = "wrong-snapshot-provider"

    def execute(self, work_order, authority, snapshot):  # noqa: ANN001
        inner = OfflineV1HardeningProvider(clock=lambda: NOW + timedelta(minutes=181))
        return replace(inner.execute(work_order, authority, snapshot), snapshot_digest="0" * 64)


def test_provider_source_identity_drift_fails_closed(tmp_path: Path) -> None:
    service, controlled, _, _, pilot, order, authority, _ = _fixture(
        tmp_path, provider=_WrongSnapshotProvider()
    )
    with pytest.raises(V1HardeningPolicyError, match="source identity"):
        service.run(
            execution_id="execution-ascos-v1-hardening-1",
            work_order=order,
            authority=authority,
            pilot=pilot,
        )
    assert controlled.execution_count == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("draft_pull_request_number", 0),
        ("feature_branch", "main"),
        ("approved_commit", "bad"),
        ("preview_url", "http://preview.invalid"),
        ("monitoring_signal_ids", tuple(reversed(MONITORING_SIGNAL_IDS))),
        ("documentation_ids", tuple(reversed(DOCUMENTATION_IDS))),
        ("status", "APPROVED"),
    ],
)
def test_work_order_rejects_invalid_or_elevated_values(tmp_path: Path, field, value) -> None:
    pilot = _run_pilot(tmp_path)[-1]
    with pytest.raises(ValueError):
        replace(_work_order(pilot), **{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "founder_acceptance_allowed",
        "repository_write_allowed",
        "pull_request_mutation_allowed",
        "merge_allowed",
        "production_deployment_allowed",
        "release_allowed",
        "billing_allowed",
        "risk_acceptance_allowed",
    ],
)
def test_authority_rejects_prohibited_permissions(tmp_path: Path, field: str) -> None:
    pilot = _run_pilot(tmp_path)[-1]
    authority = _authority(_work_order(pilot))
    with pytest.raises(ValueError, match="prohibited"):
        replace(authority, **{field: True})


def test_expired_authority_fails_before_provider(tmp_path: Path) -> None:
    service, controlled, _, _, pilot, order, _, _ = _fixture(tmp_path)
    expired = _authority(
        order,
        issued_at=NOW + timedelta(minutes=120),
        expires_at=NOW + timedelta(minutes=121),
    )
    with pytest.raises(V1HardeningPolicyError, match="not current"):
        service.run(
            execution_id="execution-ascos-v1-hardening-1",
            work_order=order,
            authority=expired,
            pilot=pilot,
        )
    assert controlled.execution_count == 0


def test_audit_receipts_form_one_tamper_evident_chain(tmp_path: Path) -> None:
    *_, artifact = _run_hardening(tmp_path)
    previous = "0" * 64
    for receipt in artifact.control_receipts:
        assert receipt.previous_audit_digest == previous
        previous = receipt.audit_digest
    assert len({item.audit_digest for item in artifact.control_receipts}) == 7


def test_store_writes_mode_0600_primary_and_verified_backup(tmp_path: Path) -> None:
    *values, artifact = _run_hardening(tmp_path)
    store = values[3]
    directory = tmp_path / "v1-hardening-state" / artifact.tenant_id / artifact.execution_id
    primary = directory / "v1-hardening-acceptance-v1.json"
    backup = directory / "v1-hardening-acceptance-v1.backup.json"
    assert stat.S_IMODE(primary.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert primary.read_bytes() == backup.read_bytes()
    store.verify_backup(artifact)


def test_explicit_recovery_restores_exact_artifact(tmp_path: Path) -> None:
    *values, artifact = _run_hardening(tmp_path)
    store = values[3]
    directory = tmp_path / "v1-hardening-state" / artifact.tenant_id / artifact.execution_id
    primary = directory / "v1-hardening-acceptance-v1.json"
    primary.write_text("corrupt")
    with pytest.raises(V1HardeningCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    assert store.recover(artifact.tenant_id, artifact.execution_id) == artifact
    assert store.load(artifact.tenant_id, artifact.execution_id) == artifact


def test_store_rejects_tamper_unknown_entries_and_symlinks(tmp_path: Path) -> None:
    *values, artifact = _run_hardening(tmp_path)
    store = values[3]
    directory = tmp_path / "v1-hardening-state" / artifact.tenant_id / artifact.execution_id
    backup = directory / "v1-hardening-acceptance-v1.backup.json"
    envelope = json.loads(backup.read_text())
    envelope["record"]["release_count"] = 1
    backup.write_text(json.dumps(envelope))
    with pytest.raises(V1HardeningCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    backup.write_bytes((directory / "v1-hardening-acceptance-v1.json").read_bytes())
    unknown = directory / "unknown.txt"
    unknown.write_text("unsafe")
    with pytest.raises(V1HardeningCorrupt, match="closed"):
        store.load(artifact.tenant_id, artifact.execution_id)
    unknown.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    backup.unlink()
    backup.symlink_to(outside)
    with pytest.raises(V1HardeningCorrupt, match="unsafe"):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_missing_artifact_and_unsafe_identity_are_rejected(tmp_path: Path) -> None:
    store = FileV1HardeningAcceptanceArtifactStore(tmp_path / "missing")
    with pytest.raises(V1HardeningNotFound):
        store.load("tenant-alpha", "missing-execution")
    with pytest.raises(V1HardeningCorrupt):
        store.load("../unsafe", "missing-execution")


def test_persisted_artifact_contains_no_secret_or_host_path(tmp_path: Path) -> None:
    _run_hardening(tmp_path)
    content = "".join(
        path.read_text() for path in (tmp_path / "v1-hardening-state").rglob("*.json")
    )
    assert "correct-horse-battery-staple" not in content
    assert "founder@example.invalid" not in content
    assert str(tmp_path) not in content
    assert "authorization" not in content.casefold()
