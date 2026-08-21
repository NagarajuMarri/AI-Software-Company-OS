from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import stat

import pytest

from runtime.complete_runtime_acceptance import FileCompleteRuntimeAcceptanceArtifactStore
from runtime.customer_application import FileCustomerProductRequestStore
from runtime.customer_prd import FileCustomerPrdApprovalStore, FileCustomerPrdStore
from runtime.customer_roadmap import (
    FileCustomerRoadmapApprovalStore,
    FileCustomerRoadmapStore,
)
from runtime.end_to_end_product_pilot import (
    ARTIFACT_STATUS,
    END_TO_END_PRODUCT_PILOT_ACTIONS,
    END_TO_END_PRODUCT_PILOT_CAPABILITIES,
    END_TO_END_PRODUCT_PILOT_TOOL_IDS,
    PILOT_STAGE_IDS,
    PILOT_STAGE_STATES,
    PILOT_STATUS,
    PRODUCTION_STATE,
    ControlledEndToEndProductPilotProvider,
    EndToEndProductPilotAuthority,
    EndToEndProductPilotObservation,
    EndToEndProductPilotProvider,
    EndToEndProductPilotService,
    EndToEndProductPilotWorkOrder,
    FileEndToEndProductPilotArtifactStore,
    ProductPilotConflict,
    ProductPilotCorrupt,
    ProductPilotNotFound,
    ProductPilotPolicyError,
    ProductPilotStageReceipt,
    product_binding_digest_for,
)
from runtime.preview_deployment import FilePreviewDeploymentArtifactStore
from tests.test_complete_runtime_acceptance import _run_acceptance
from tests.test_customer_roadmap_approval import (
    _approve as _approve_roadmap,
    _services as _customer_services,
)
from tests.test_workforce_leadership import NOW


class DeterministicProductPilotProvider(EndToEndProductPilotProvider):
    provider_id = "deterministic-product-pilot-v1"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, work_order, authority, snapshot):  # noqa: ANN001
        del work_order, authority
        self.calls += 1
        sources = (
            snapshot.source_request_digest,
            snapshot.prd_approval_digest,
            snapshot.roadmap_approval_digest,
            snapshot.orchestration_artifact_digest,
            snapshot.coding_review_artifact_digest,
            snapshot.github_delivery_artifact_digest,
            snapshot.preview_artifact_digest,
            snapshot.runtime_acceptance_artifact_digest,
        )
        receipts = tuple(
            ProductPilotStageReceipt(stage_id, digest, state, 1, NOW + timedelta(minutes=121))
            for stage_id, state, digest in zip(
                PILOT_STAGE_IDS, PILOT_STAGE_STATES, sources, strict=True
            )
        )
        return EndToEndProductPilotObservation(
            provider_id=self.provider_id,
            pilot_id=snapshot.pilot_id,
            snapshot_digest=snapshot.digest,
            stage_receipts=receipts,
            source_record_count=7,
            completed_journey_count=len(snapshot.journey_ids),
            passed_journey_count=len(snapshot.journey_ids),
        )


def _work_order(request, prd, prd_approval, roadmap, roadmap_approval, preview, runtime, **changes):  # noqa: ANN001
    pilot_id = "fixture-first-product-pilot"
    binding = product_binding_digest_for(
        pilot_id, prd.product_id, runtime.product_id, request.digest
    )
    values = {
        "work_order_id": "work-order-first-product-pilot-1",
        "tenant_id": runtime.tenant_id,
        "customer_id": request.customer_id,
        "request_id": request.request_id,
        "opportunity_id": runtime.opportunity_id,
        "assignment_id": "assignment-first-product-pilot-1",
        "pilot_id": pilot_id,
        "source_request_digest": request.digest,
        "prd_digest": prd.digest,
        "prd_approval_digest": prd_approval.digest,
        "roadmap_digest": roadmap.digest,
        "roadmap_approval_digest": roadmap_approval.digest,
        "preview_artifact_digest": preview.digest,
        "runtime_acceptance_artifact_digest": runtime.digest,
        "product_binding_digest": binding,
        "customer_product_id": prd.product_id,
        "runtime_product_id": runtime.product_id,
        "repository_full_name": runtime.repository_full_name,
        "feature_branch": runtime.feature_branch,
        "approved_commit": runtime.approved_commit,
        "approved_tree": runtime.approved_tree,
        "draft_pull_request_number": preview.draft_pull_request_number,
        "preview_environment_id": runtime.preview_environment_id,
        "preview_url": runtime.preview_url,
        "journey_ids": runtime.journey_ids,
        "objectives": (
            "Verify one exact persisted customer idea",
            "Bind the locked PRD and approved roadmap",
            "Prove governed agents produced reviewed code and a draft PR",
            "Prove the healthy preview passed every declared browser journey",
        ),
        "acceptance_checks": (
            "Customer request is exact and persisted",
            "PRD and PRD approval are exact and locked",
            "Roadmap and roadmap approval are exact and locked",
            "Governed orchestration artifact is present",
            "QA and Security reviewed code is present",
            "Controlled delivery produced one open draft pull request",
            "Preview remains healthy and isolated",
            "Every declared runtime journey passed with screenshots",
            "No source identity or digest drift is present",
            "Production, merge, release, billing, and Day 37 counts stay zero",
        ),
        "constraints": (
            "Use only the seven exact persisted source records",
            "Do not mutate the customer request, PRD, or roadmap",
            "Do not write or change a product repository",
            "Do not update, approve, close, or merge the draft pull request",
            "Do not mutate or promote the preview",
            "Do not deploy production or release",
            "Do not bill, spend budget, or accept risk",
            "Do not start Day 37 hardening work",
        ),
        "issued_at": NOW + timedelta(minutes=120),
        "expires_at": NOW + timedelta(hours=7),
    }
    values.update(changes)
    return EndToEndProductPilotWorkOrder(**values)


def _authority(order: EndToEndProductPilotWorkOrder, **changes):
    values = {
        "authority_id": "authority-first-product-pilot-1",
        "issuer_id": "founder-day36-start-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "pilot_id": order.pilot_id,
        "work_order_digest": order.digest,
        "source_request_digest": order.source_request_digest,
        "roadmap_approval_digest": order.roadmap_approval_digest,
        "runtime_acceptance_artifact_digest": order.runtime_acceptance_artifact_digest,
        "product_binding_digest": order.product_binding_digest,
        "allowed_action_ids": END_TO_END_PRODUCT_PILOT_ACTIONS,
        "allowed_tool_ids": END_TO_END_PRODUCT_PILOT_TOOL_IDS,
        "issued_at": NOW + timedelta(minutes=120),
        "expires_at": NOW + timedelta(hours=7),
        "max_journeys": 12,
    }
    values.update(changes)
    return EndToEndProductPilotAuthority(**values)


def _fixture(tmp_path: Path, browser_provider=None):  # noqa: ANN001
    customer_root = tmp_path / "customer-chain"
    customer = _customer_services(customer_root)
    roadmap_approval = _approve_roadmap(customer[15], customer[13])
    request, prd, prd_approval, roadmap = customer[5], customer[8], customer[10], customer[13]
    runtime_values = _run_acceptance(tmp_path, browser_provider)
    preview, runtime = runtime_values[4], runtime_values[-1]
    order = _work_order(
        request, prd, prd_approval, roadmap, roadmap_approval, preview, runtime
    )
    authority = _authority(order)
    inner = DeterministicProductPilotProvider()
    controlled = ControlledEndToEndProductPilotProvider(inner)
    store = FileEndToEndProductPilotArtifactStore(tmp_path / "product-pilot-state")
    service = EndToEndProductPilotService(
        controlled,
        FileCustomerProductRequestStore(customer_root / "requests"),
        FileCustomerPrdStore(customer_root / "prds"),
        FileCustomerPrdApprovalStore(customer_root / "prd-approvals"),
        FileCustomerRoadmapStore(customer_root / "roadmaps"),
        FileCustomerRoadmapApprovalStore(customer_root / "roadmap-approvals"),
        FilePreviewDeploymentArtifactStore(tmp_path / "preview-deployment-state"),
        FileCompleteRuntimeAcceptanceArtifactStore(
            tmp_path / "complete-runtime-acceptance-state"
        ),
        store,
        clock=lambda: NOW + timedelta(minutes=121),
    )
    return (
        service, controlled, inner, store, request, prd, prd_approval, roadmap,
        roadmap_approval, preview, runtime, order, authority,
    )


def _run_pilot(tmp_path: Path, browser_provider=None):  # noqa: ANN001
    values = _fixture(tmp_path, browser_provider)
    (
        service, _, _, _, request, prd, prd_approval, roadmap,
        roadmap_approval, preview, runtime, order, authority,
    ) = values
    artifact = service.run(
        execution_id="execution-first-product-pilot-1",
        work_order=order,
        authority=authority,
        product_request=request,
        prd=prd,
        prd_approval=prd_approval,
        roadmap=roadmap,
        roadmap_approval=roadmap_approval,
        preview=preview,
        runtime_acceptance=runtime,
    )
    return (*values, artifact)


def test_product_pilot_binds_all_eight_end_to_end_stages(tmp_path: Path) -> None:
    *values, artifact = _run_pilot(tmp_path)
    controlled, inner = values[1], values[2]
    assert controlled.execution_count == inner.calls == 1
    assert tuple(item.stage_id for item in artifact.stage_receipts) == PILOT_STAGE_IDS
    assert tuple(item.state for item in artifact.stage_receipts) == PILOT_STAGE_STATES
    assert artifact.source_record_count == 7
    assert artifact.completed_journey_count == artifact.passed_journey_count == 4
    assert artifact.governance_capability_ids == END_TO_END_PRODUCT_PILOT_CAPABILITIES


def test_product_pilot_preserves_exact_customer_and_runtime_source_chain(tmp_path: Path) -> None:
    *values, artifact = _run_pilot(tmp_path)
    request, prd, prd_approval, roadmap, roadmap_approval = values[4:9]
    preview, runtime = values[9:11]
    assert artifact.source_request_digest == request.digest
    assert artifact.prd_digest == prd.digest
    assert artifact.prd_approval_digest == prd_approval.digest
    assert artifact.roadmap_digest == roadmap.digest
    assert artifact.roadmap_approval_digest == roadmap_approval.digest
    assert artifact.preview_artifact_digest == preview.digest
    assert artifact.runtime_acceptance_artifact_digest == runtime.digest
    assert artifact.github_delivery_artifact_digest == preview.github_delivery_artifact_digest
    assert artifact.browser_execution_digest == runtime.browser_execution_digest


def test_product_pilot_terminal_state_has_no_elevated_effects(tmp_path: Path) -> None:
    *_, artifact = _run_pilot(tmp_path)
    assert artifact.status == ARTIFACT_STATUS
    assert artifact.pilot_status == PILOT_STATUS
    assert artifact.production_state == PRODUCTION_STATE
    assert artifact.repository_write_count == 0
    assert artifact.pull_request_mutation_count == 0
    assert artifact.preview_mutation_count == 0
    assert artifact.merge_count == artifact.production_deployment_count == 0
    assert artifact.release_count == artifact.billing_count == 0
    assert artifact.risk_acceptance_count == artifact.day37_action_count == 0


def test_exact_retry_and_restart_do_not_execute_provider_again(tmp_path: Path) -> None:
    *values, first = _run_pilot(tmp_path)
    service, controlled, inner = values[:3]
    request, prd, prd_approval, roadmap, roadmap_approval = values[4:9]
    preview, runtime, order, authority = values[9:13]
    second = service.run(
        execution_id=first.execution_id,
        work_order=order,
        authority=authority,
        product_request=request,
        prd=prd,
        prd_approval=prd_approval,
        roadmap=roadmap,
        roadmap_approval=roadmap_approval,
        preview=preview,
        runtime_acceptance=runtime,
    )
    assert second == first
    assert controlled.execution_count == inner.calls == 1
    assert service.get(first.tenant_id, first.execution_id) == first


def test_retry_with_changed_authority_conflicts(tmp_path: Path) -> None:
    *values, artifact = _run_pilot(tmp_path)
    service = values[0]
    request, prd, prd_approval, roadmap, roadmap_approval = values[4:9]
    preview, runtime, order, authority = values[9:13]
    changed = replace(authority, authority_id="authority-first-product-pilot-2")
    with pytest.raises(ProductPilotConflict):
        service.run(
            execution_id=artifact.execution_id,
            work_order=order,
            authority=changed,
            product_request=request,
            prd=prd,
            prd_approval=prd_approval,
            roadmap=roadmap,
            roadmap_approval=roadmap_approval,
            preview=preview,
            runtime_acceptance=runtime,
        )


def test_unpersisted_customer_idea_fails_before_provider(tmp_path: Path) -> None:
    values = _fixture(tmp_path)
    service, controlled = values[:2]
    request, prd, prd_approval, roadmap, roadmap_approval = values[4:9]
    preview, runtime, order, authority = values[9:13]
    changed = replace(request, product_summary="A changed unpersisted customer idea.")
    with pytest.raises(ProductPilotPolicyError, match="persisted"):
        service.run(
            execution_id="execution-first-product-pilot-1",
            work_order=order,
            authority=authority,
            product_request=changed,
            prd=prd,
            prd_approval=prd_approval,
            roadmap=roadmap,
            roadmap_approval=roadmap_approval,
            preview=preview,
            runtime_acceptance=runtime,
        )
    assert controlled.execution_count == 0


def test_product_binding_drift_fails_closed(tmp_path: Path) -> None:
    values = _fixture(tmp_path)
    service, controlled = values[:2]
    request, prd, prd_approval, roadmap, roadmap_approval = values[4:9]
    preview, runtime, order = values[9:12]
    changed_order = replace(order, product_binding_digest="0" * 64)
    changed_authority = _authority(changed_order)
    with pytest.raises(ProductPilotPolicyError, match="binding"):
        service.run(
            execution_id="execution-first-product-pilot-1",
            work_order=changed_order,
            authority=changed_authority,
            product_request=request,
            prd=prd,
            prd_approval=prd_approval,
            roadmap=roadmap,
            roadmap_approval=roadmap_approval,
            preview=preview,
            runtime_acceptance=runtime,
        )
    assert controlled.execution_count == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("draft_pull_request_number", 0),
        ("feature_branch", "main"),
        ("approved_commit", "bad"),
        ("preview_url", "http://preview.invalid"),
        ("status", "APPROVED"),
    ],
)
def test_work_order_rejects_invalid_or_elevated_values(tmp_path: Path, field, value) -> None:
    values = _fixture(tmp_path)
    with pytest.raises(ValueError):
        replace(values[11], **{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "repository_write_allowed",
        "pull_request_mutation_allowed",
        "preview_mutation_allowed",
        "merge_allowed",
        "production_deployment_allowed",
        "release_allowed",
        "billing_allowed",
        "risk_acceptance_allowed",
        "day37_allowed",
    ],
)
def test_authority_rejects_prohibited_permissions(tmp_path: Path, field: str) -> None:
    authority = _fixture(tmp_path)[12]
    with pytest.raises(ValueError, match="prohibited"):
        replace(authority, **{field: True})


def test_store_is_mode_0600_restart_safe_and_tamper_evident(tmp_path: Path) -> None:
    *values, artifact = _run_pilot(tmp_path)
    store = values[3]
    path = next((tmp_path / "product-pilot-state").rglob("*.json"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.load(artifact.tenant_id, artifact.execution_id) == artifact
    envelope = json.loads(path.read_text())
    envelope["record"]["passed_journey_count"] = 3
    path.write_text(json.dumps(envelope))
    with pytest.raises(ProductPilotCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_store_rejects_unknown_entries_and_symlinks(tmp_path: Path) -> None:
    *values, artifact = _run_pilot(tmp_path)
    store = values[3]
    path = next((tmp_path / "product-pilot-state").rglob("*.json"))
    unknown = path.parent / "unknown.txt"
    unknown.write_text("unsafe")
    with pytest.raises(ProductPilotCorrupt, match="closed"):
        store.load(artifact.tenant_id, artifact.execution_id)
    unknown.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ProductPilotCorrupt, match="unsafe"):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_missing_artifact_and_unsafe_identity_are_rejected(tmp_path: Path) -> None:
    store = FileEndToEndProductPilotArtifactStore(tmp_path / "missing")
    with pytest.raises(ProductPilotNotFound):
        store.load("tenant-alpha", "missing-execution")
    with pytest.raises(ProductPilotCorrupt):
        store.load("../unsafe", "missing-execution")


def test_persisted_pilot_contains_no_raw_secret_or_host_path(tmp_path: Path) -> None:
    _run_pilot(tmp_path)
    path = next((tmp_path / "product-pilot-state").rglob("*.json"))
    content = path.read_text()
    assert "correct-horse-battery-staple" not in content
    assert "founder@example.invalid" not in content
    assert str(tmp_path) not in content
    assert "authorization" not in content.casefold()
