from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from runtime.customer_acceptance import (
    CustomerAcceptanceApplication,
    CustomerAcceptanceConfiguration,
    CustomerAcceptanceConflict,
    CustomerAcceptanceCorrupt,
    CustomerAcceptanceOutcome,
    CustomerAcceptanceReconciliationRequired,
    CustomerAcceptanceService,
    CustomerAcceptanceStatus,
    FileCustomerAcceptanceStore,
    PreviewDeploymentReceipt,
    WorkflowJobReceipt,
)
from runtime.managed_product_browser import (
    BrowserActionKind,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
    BrowserStep,
    FileBrowserJourneyPlanStore,
)
from runtime.runtime_acceptance import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
)
from tests.test_customer_delivery import _module4
from tests.test_customer_prd_approval import CSRF, NOW, _call


class _Evidence:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, **values):
        self.calls.append(values)
        return SimpleNamespace(package_id="customer-evidence-123", digest="9" * 64)


class _Adapter:
    def __init__(self, *, fail: bool = False) -> None:
        self.preflight_count = 0
        self.execute_count = 0
        self.fail = fail

    def preflight(self, record, plan):
        self.preflight_count += 1
        assert record.browser_plan_digest == plan.digest

    def execute(self, record, plan):
        self.execute_count += 1
        if self.fail:
            raise RuntimeError("preview effect became uncertain")
        return _outcome(record, plan)


def _configuration(*, enabled: bool = True) -> CustomerAcceptanceConfiguration:
    journey = BrowserJourneySpecification(
        journey_id="landing-ready",
        capability_id="product-preview-acceptance",
        title="Product landing page is ready",
        start_path="/",
        steps=(
            BrowserStep(
                step_id="ready-visible",
                action=BrowserActionKind.ASSERT_VISIBLE,
                locator=BrowserLocator(BrowserLocatorKind.TEXT, "Product ready"),
            ),
        ),
    )
    return CustomerAcceptanceConfiguration(
        preview_environment_id="preview-customer-product",
        preview_url="https://preview.example.test",
        workflow_file=".github/workflows/ascos-preview.yml",
        automated_test_job="automated-tests",
        security_job="security-review",
        acceptance_profile_id="customer-product-v1",
        acceptance_profile_version="1.0",
        allowed_origins=("https://preview.example.test",),
        journeys=(journey,),
        enabled=enabled,
        preview_deployment_confirmed=enabled,
        browser_execution_confirmed=enabled,
    )


def _module5(
    root: Path,
    *,
    fail: bool = False,
    enabled: bool = True,
    configuration: CustomerAcceptanceConfiguration | None = None,
):
    deliveries, _, _, _, gateway, _ = _module4(root)
    review = deliveries.prepare("customer-1", "req-1")
    review = deliveries.approve(
        "customer-1",
        "req-1",
        expected_review_digest=review.review_digest,
        confirm_review=True,
    )
    delivery = deliveries.deliver(
        "customer-1",
        "req-1",
        expected_review_digest=review.review_digest,
        confirm_repository_write=True,
    )
    evidence = _Evidence()
    adapter = _Adapter(fail=fail)
    store = FileCustomerAcceptanceStore(root / "acceptance" / "records")
    plans = FileBrowserJourneyPlanStore(root / "acceptance" / "plans")
    service = CustomerAcceptanceService(
        store,
        plans,
        deliveries,
        evidence,  # type: ignore[arg-type]
        configuration or _configuration(enabled=enabled),
        adapter,
        lambda: NOW,
    )
    return service, store, plans, evidence, adapter, delivery, gateway


def _outcome(record, plan):  # noqa: ANN001
    deployed_at = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    jobs = (
        WorkflowJobReceipt(101, "automated-tests", "SUCCESS", "https://github.com/example/product/actions/runs/7/job/101"),
        WorkflowJobReceipt(102, "security-review", "SUCCESS", "https://github.com/example/product/actions/runs/7/job/102"),
    )
    deployment = PreviewDeploymentReceipt(
        provider_id="fixture-preview",
        workflow_run_id=7,
        workflow_run_url="https://github.com/example/product/actions/runs/7",
        repository_full_name=record.repository_full_name,
        branch=record.head_branch,
        commit_sha=record.commit_sha,
        tree_sha=record.tree_sha,
        preview_environment_id=record.preview_environment_id,
        preview_url=record.preview_url,
        deployment_revision="preview-run-7",
        health_status_code=200,
        health_digest="7" * 64,
        jobs=jobs,
        deployed_at=deployed_at,
    )
    browser_evidence = tuple(
        EvidenceArtifact(
            evidence_id=f"evidence-{index}",
            run_id=record.acceptance_id,
            capability_id="product-preview-acceptance",
            journey_id="landing-ready",
            kind=kind,
            outcome=EvidenceOutcome.PASS,
            commit_sha=record.commit_sha,
            artifact_uri=f"artifact://browser/{record.product_id}/{record.acceptance_id}/{index}.json",
            digest=f"{index}" * 64,
            observed_at=deployed_at,
            summary="Governed browser evidence passed",
        )
        for index, kind in enumerate(
            (
                EvidenceKind.BROWSER,
                EvidenceKind.BROWSER_CONSOLE,
                EvidenceKind.BROWSER_NETWORK,
                EvidenceKind.SCREENSHOT,
            ),
            start=1,
        )
    )
    browser = BrowserExecutionResult(
        run_id=record.acceptance_id,
        product_id=record.product_id,
        plan_id=record.browser_plan_id,
        plan_digest=plan.digest,
        commit_sha=record.commit_sha,
        stage=BrowserExecutionStage.COMPLETED,
        evidence=browser_evidence,
        journey_results=(
            JourneyResult(
                "landing-ready",
                EvidenceOutcome.PASS,
                tuple(value.evidence_id for value in browser_evidence),
                deployed_at,
            ),
        ),
        started_at=deployed_at,
        completed_at=deployed_at,
    )
    extra = tuple(
        EvidenceArtifact(
            evidence_id=f"workflow-{kind.value.lower()}",
            run_id=record.acceptance_id,
            capability_id="product-preview-acceptance",
            journey_id="preview-deployment",
            kind=kind,
            outcome=EvidenceOutcome.PASS,
            commit_sha=record.commit_sha,
            artifact_uri=f"artifact://browser/{record.product_id}/{record.acceptance_id}/{kind.value}.json",
            digest="8" * 64 if kind is EvidenceKind.AUTOMATED_TEST else "9" * 64,
            observed_at=deployed_at,
            summary="Required workflow gate passed",
        )
        for kind in (EvidenceKind.AUTOMATED_TEST, EvidenceKind.SECURITY)
    )
    return CustomerAcceptanceOutcome(deployment, browser, extra + browser_evidence)


def test_exact_delivery_becomes_approved_preview_plan_without_external_effect(tmp_path):
    service, store, plans, evidence, adapter, delivery, _ = _module5(tmp_path)
    record = service.prepare("customer-1", "req-1")

    assert record.status is CustomerAcceptanceStatus.AWAITING_APPROVAL
    assert record.delivery_digest == delivery.digest
    assert record.commit_sha == delivery.commit_sha
    assert record.pull_request_number == delivery.pull_request_number
    assert record.preview_url == "https://preview.example.test"
    assert record.journeys[0].journey_id == "landing-ready"
    assert plans.load(record.product_id, record.acceptance_id, record.browser_plan_id).digest == record.browser_plan_digest
    assert store.load("customer-1", "req-1") == record
    assert adapter.preflight_count == adapter.execute_count == 0
    assert evidence.calls == []

    with pytest.raises(CustomerAcceptanceConflict, match="stale"):
        service.approve(
            "customer-1",
            "req-1",
            expected_approval_digest="0" * 64,
            confirm_preview_scope=True,
        )


def test_approved_plan_runs_once_and_publishes_exact_preview_evidence(tmp_path):
    service, store, _, evidence, adapter, delivery, _ = _module5(tmp_path)
    record = service.prepare("customer-1", "req-1")
    approved = service.approve(
        "customer-1",
        "req-1",
        expected_approval_digest=record.approval_digest,
        confirm_preview_scope=True,
    )
    ready = service.execute(
        "customer-1",
        "req-1",
        expected_approval_digest=approved.approval_digest,
        confirm_preview_deployment=True,
        confirm_browser_execution=True,
    )

    assert ready.status is CustomerAcceptanceStatus.EVIDENCE_READY
    assert ready.workflow_run_id == 7
    assert ready.deployment_revision == "preview-run-7"
    assert ready.browser_execution_digest
    assert ready.evidence_package_id == "customer-evidence-123"
    assert evidence.calls[0]["commit_sha"] == delivery.commit_sha
    assert evidence.calls[0]["preview_url"] == "https://preview.example.test/"
    assert {value.kind for value in evidence.calls[0]["evidence"]} >= {
        EvidenceKind.AUTOMATED_TEST,
        EvidenceKind.SECURITY,
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
    }
    assert adapter.preflight_count == adapter.execute_count == 1
    repeated = service.execute(
        "customer-1",
        "req-1",
        expected_approval_digest=ready.approval_digest,
        confirm_preview_deployment=True,
        confirm_browser_execution=True,
    )
    assert repeated == ready
    assert adapter.preflight_count == adapter.execute_count == 1
    assert store.load("customer-1", "req-1") == ready


def test_post_intent_failure_requires_reconciliation_and_never_retries(tmp_path):
    service, store, _, _, adapter, _, _ = _module5(tmp_path, fail=True)
    record = service.prepare("customer-1", "req-1")
    approved = service.approve(
        "customer-1",
        "req-1",
        expected_approval_digest=record.approval_digest,
        confirm_preview_scope=True,
    )
    with pytest.raises(CustomerAcceptanceReconciliationRequired):
        service.execute(
            "customer-1",
            "req-1",
            expected_approval_digest=approved.approval_digest,
            confirm_preview_deployment=True,
            confirm_browser_execution=True,
        )
    failed = store.load("customer-1", "req-1")
    assert failed.status is CustomerAcceptanceStatus.RECONCILIATION_REQUIRED
    assert failed.failure_classification == "RuntimeError"
    with pytest.raises(CustomerAcceptanceConflict, match="not approved"):
        service.execute(
            "customer-1",
            "req-1",
            expected_approval_digest=failed.approval_digest,
            confirm_preview_deployment=True,
            confirm_browser_execution=True,
        )
    assert adapter.execute_count == 1


def test_store_is_private_closed_and_detects_tamper(tmp_path):
    service, store, _, _, _, _, _ = _module5(tmp_path)
    service.prepare("customer-1", "req-1")
    path = next((tmp_path / "acceptance" / "records").rglob("preview-acceptance-v1.json"))
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["record"]["preview_url"] = "https://attacker.example"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(CustomerAcceptanceCorrupt, match="corrupt"):
        store.load("customer-1", "req-1")


def test_dashboard_accepts_no_preview_target_workflow_or_secret_input(tmp_path):
    service, _, _, _, adapter, _, _ = _module5(tmp_path)
    application = CustomerAcceptanceApplication(service)
    path = "/customer/requests/req-1/acceptance"
    status, headers, content = _call(application, path=path)
    assert status == "200 OK"
    assert b"Prepare exact preview acceptance" in content
    assert b'name="preview_url"' not in content
    assert b'name="workflow"' not in content
    assert b'name="credential"' not in content
    assert headers["Cache-Control"] == "no-store"

    assert _call(
        application,
        path=f"{path}/prepare",
        method="POST",
        body=urlencode({"csrf_token": CSRF}),
    )[0] == "303 See Other"
    record = service.find("customer-1", "req-1")
    assert record is not None
    assert _call(
        application,
        path=f"{path}/approve",
        method="POST",
        body=urlencode(
            {
                "csrf_token": CSRF,
                "approval_digest": record.approval_digest,
                "confirm_scope": "yes",
            }
        ),
    )[0] == "303 See Other"
    approved = service.find("customer-1", "req-1")
    assert approved is not None
    assert _call(
        application,
        path=f"{path}/execute",
        method="POST",
        body=urlencode(
            {
                "csrf_token": CSRF,
                "approval_digest": approved.approval_digest,
                "confirm_preview": "yes",
                "confirm_browser": "yes",
            }
        ),
    )[0] == "303 See Other"
    status, _, content = _call(application, path=path)
    assert status == "200 OK"
    assert b"Durable preview acceptance receipt" in content
    assert b"Review preview evidence" in content
    assert b"production" in content.lower() and b"FamilyVault" in content
    assert adapter.execute_count == 1
