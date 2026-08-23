from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from runtime.customer_acceptance import (
    ControlledCustomerAcceptanceAdapter,
    EnvironmentBrowserInputResolver,
    PlaywrightPreviewBrowserGateway,
    PreviewDeploymentReceipt,
    WorkflowJobReceipt,
)
from runtime.managed_product_browser import (
    BrowserExecutionResult,
    BrowserExecutionStage,
    ContentAddressedBrowserArtifactStore,
    FileBrowserExecutionStore,
)
from runtime.runtime_acceptance import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
)
from tests.test_customer_acceptance import _configuration, _module5


NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


class _Deployment:
    def __init__(self) -> None:
        self.preflight_count = 0
        self.deploy_count = 0

    def preflight(self, record, configuration):
        self.preflight_count += 1
        assert record.configuration_digest == configuration.digest

    def deploy(self, record, configuration):
        self.deploy_count += 1
        return PreviewDeploymentReceipt(
            provider_id="fixture-preview",
            workflow_run_id=77,
            workflow_run_url="https://github.com/example/product/actions/runs/77",
            repository_full_name=record.repository_full_name,
            branch=record.head_branch,
            commit_sha=record.commit_sha,
            tree_sha=record.tree_sha,
            preview_environment_id=configuration.preview_environment_id,
            preview_url=configuration.preview_url,
            deployment_revision="preview-run-77",
            health_status_code=200,
            health_digest="7" * 64,
            jobs=(
                WorkflowJobReceipt(
                    701,
                    configuration.automated_test_job,
                    "SUCCESS",
                    "https://github.com/example/product/actions/runs/77/job/701",
                ),
                WorkflowJobReceipt(
                    702,
                    configuration.security_job,
                    "SUCCESS",
                    "https://github.com/example/product/actions/runs/77/job/702",
                ),
            ),
            deployed_at=NOW,
        )


class _Playwright:
    provider_id = "fixture-cloud-playwright"

    def __init__(self) -> None:
        self.cdp_endpoint = None
        self.redactions = ()

    def execute_preview(
        self,
        plan,
        frontend_url,
        allowed_origins,
        inputs,
        redactions,
        artifact_store,
        *,
        cdp_endpoint=None,
    ):
        assert frontend_url in allowed_origins
        assert inputs == {}
        self.cdp_endpoint = cdp_endpoint
        self.redactions = redactions
        journey = plan.journeys[0]
        evidence = []
        for index, kind in enumerate(
            (
                EvidenceKind.BROWSER,
                EvidenceKind.BROWSER_CONSOLE,
                EvidenceKind.BROWSER_NETWORK,
                EvidenceKind.SCREENSHOT,
            ),
            start=1,
        ):
            if kind is EvidenceKind.SCREENSHOT:
                uri, digest = artifact_store.write_bytes(
                    plan.product_id,
                    plan.run_id,
                    b"\x89PNG\r\n\x1a\nfixture",
                    "png",
                )
            else:
                uri, digest = artifact_store.write_json(
                    plan.product_id,
                    plan.run_id,
                    {"kind": kind.value, "outcome": "PASS"},
                )
            evidence.append(
                EvidenceArtifact(
                    evidence_id=f"cloud-browser-{index}",
                    run_id=plan.run_id,
                    capability_id=journey.capability_id,
                    journey_id=journey.journey_id,
                    kind=kind,
                    outcome=EvidenceOutcome.PASS,
                    commit_sha=plan.commit_sha,
                    artifact_uri=uri,
                    digest=digest,
                    observed_at=NOW,
                    summary="Cloud browser evidence passed",
                )
            )
        return BrowserExecutionResult(
            run_id=plan.run_id,
            product_id=plan.product_id,
            plan_id=plan.plan_id,
            plan_digest=plan.digest,
            commit_sha=plan.commit_sha,
            stage=BrowserExecutionStage.COMPLETED,
            evidence=tuple(evidence),
            journey_results=(
                JourneyResult(
                    journey.journey_id,
                    EvidenceOutcome.PASS,
                    tuple(value.evidence_id for value in evidence),
                    NOW,
                ),
            ),
            started_at=NOW,
            completed_at=NOW,
        )


def test_controlled_adapter_uses_opaque_cloud_browser_and_publishes_required_evidence(
    tmp_path,
):
    configuration = replace(
        _configuration(),
        browser_cdp_reference="ASCOS_BROWSER_CDP_ENDPOINT",
    )
    service, _, plans, _, _, _, _ = _module5(tmp_path, configuration=configuration)
    record = service.prepare("customer-1", "req-1")
    record = service.approve(
        "customer-1",
        "req-1",
        expected_approval_digest=record.approval_digest,
        confirm_preview_scope=True,
    )
    plan = plans.load(record.product_id, record.acceptance_id, record.browser_plan_id)
    artifacts = ContentAddressedBrowserArtifactStore(tmp_path / "provider-artifacts")
    playwright = _Playwright()
    browser = PlaywrightPreviewBrowserGateway(
        FileBrowserExecutionStore(tmp_path / "provider-results"),
        artifacts,
        EnvironmentBrowserInputResolver(
            {"ASCOS_BROWSER_CDP_ENDPOINT": "wss://browser.example.test/cdp?token=secret"}
        ),
        playwright,  # type: ignore[arg-type]
    )
    deployment = _Deployment()
    adapter = ControlledCustomerAcceptanceAdapter(
        configuration,
        deployment,
        browser,
        artifacts,
        clock=lambda: NOW,
    )

    adapter.preflight(record, plan)
    outcome = adapter.execute(record, plan)

    assert deployment.preflight_count == deployment.deploy_count == 1
    assert playwright.cdp_endpoint == "wss://browser.example.test/cdp?token=secret"
    assert playwright.cdp_endpoint in playwright.redactions
    assert {value.kind for value in outcome.evidence} == {
        EvidenceKind.AUTOMATED_TEST,
        EvidenceKind.SECURITY,
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
    }
    assert all(value.outcome is EvidenceOutcome.PASS for value in outcome.evidence)
    raw = b"".join(path.read_bytes() for path in (tmp_path / "provider-artifacts").rglob("*.*"))
    assert b"token=secret" not in raw
