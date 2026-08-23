from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from runtime.complete_runtime_acceptance import (
    ARTIFACT_STATUS,
    AUTHENTICATION_STATE,
    BROWSER_STATE,
    COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS,
    COMPLETE_RUNTIME_ACCEPTANCE_CAPABILITIES,
    COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS,
    JOURNEY_STATE,
    PILOT_STATUS,
    PREVIEW_STATE,
    PRODUCTION_STATE,
    CompleteRuntimeAcceptanceAuthority,
    CompleteRuntimeAcceptanceService,
    CompleteRuntimeAcceptanceWorkOrder,
    ControlledCompleteRuntimeAcceptanceProvider,
    FileCompleteRuntimeAcceptanceArtifactStore,
    RuntimeAcceptanceConflict,
    RuntimeAcceptanceCorrupt,
    RuntimeAcceptanceNotFound,
    RuntimeAcceptancePolicyError,
)
from runtime.managed_product_browser import (
    BrowserActionKind,
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserInputBinding,
    BrowserJourneyPlan,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
    BrowserStep,
    ContentAddressedBrowserArtifactStore,
    FileBrowserJourneyPlanStore,
)
from runtime.managed_product_runtime import (
    CommandSpec,
    FileRuntimeConfigurationStore,
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    OneShotCommand,
    ReadinessProbe,
)
from runtime.runtime_acceptance import (
    AcceptanceJourney,
    CapabilityAcceptanceContract,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
    RuntimeAcceptanceProfile,
)
from tests.test_preview_deployment import _run_preview
from tests.test_workforce_leadership import NOW


PASSWORD = "correct-horse-battery-staple"
JOURNEY_SPECS = (
    (
        "authentication.login",
        "AUTHENTICATION",
        "Customer logs in to the isolated preview",
        "/acceptance/login",
        "Authenticated preview session",
    ),
    (
        "records.create_and_view",
        "RECORDS",
        "Customer creates and views a module record",
        "/acceptance/records-create",
        "Record created and visible",
    ),
    (
        "records.refresh_persistence",
        "RECORDS",
        "Customer refreshes and retains the saved record",
        "/acceptance/records-refresh",
        "Saved record persisted after refresh",
    ),
    (
        "validation.safe_recovery",
        "VALIDATION",
        "Customer recovers from a validation error",
        "/acceptance/validation",
        "Validation error recovered safely",
    ),
)


class MappingResolver:
    def __init__(self, values):  # noqa: ANN001
        self.values = values
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        return self.values[reference]


class DeterministicCompleteBrowserProvider:
    provider_id = "deterministic-complete-browser-v1"

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, plan, configuration, inputs, redactions, artifact_store):  # noqa: ANN001
        del configuration
        self.calls += 1
        assert inputs["user-password"] == PASSWORD
        assert PASSWORD in redactions
        evidence: list[EvidenceArtifact] = []
        results: list[JourneyResult] = []
        observed = NOW + timedelta(minutes=119)
        for journey in plan.journeys:
            journey_evidence = []
            for kind in (
                EvidenceKind.BROWSER,
                EvidenceKind.BROWSER_CONSOLE,
                EvidenceKind.BROWSER_NETWORK,
                EvidenceKind.SCREENSHOT,
            ):
                if kind is EvidenceKind.SCREENSHOT:
                    uri, digest = artifact_store.write_bytes(
                        plan.product_id,
                        plan.run_id,
                        b"\x89PNG\r\n\x1a\n" + journey.journey_id.encode(),
                        "png",
                    )
                else:
                    uri, digest = artifact_store.write_json(
                        plan.product_id,
                        plan.run_id,
                        {
                            "journey_id": journey.journey_id,
                            "kind": kind.value,
                            "status": "PASS",
                        },
                    )
                item = EvidenceArtifact(
                    evidence_id=(
                        f"{plan.run_id}.{journey.journey_id}."
                        f"{kind.value.casefold().replace('_evidence', '')}"
                    ),
                    run_id=plan.run_id,
                    capability_id=journey.capability_id,
                    journey_id=journey.journey_id,
                    kind=kind,
                    outcome=EvidenceOutcome.PASS,
                    commit_sha=plan.commit_sha,
                    artifact_uri=uri,
                    digest=digest,
                    observed_at=observed,
                    summary=f"Verified {kind.value}",
                    metadata=(
                        ("plan_digest", plan.digest),
                        ("provider_id", self.provider_id),
                    ),
                )
                evidence.append(item)
                journey_evidence.append(item.evidence_id)
            results.append(
                JourneyResult(
                    journey.journey_id,
                    EvidenceOutcome.PASS,
                    tuple(journey_evidence),
                    observed,
                )
            )
        return BrowserExecutionResult(
            plan.run_id,
            plan.product_id,
            plan.plan_id,
            plan.digest,
            plan.commit_sha,
            BrowserExecutionStage.COMPLETED,
            tuple(evidence),
            tuple(results),
            observed,
            observed,
        )


def _profile() -> RuntimeAcceptanceProfile:
    capabilities = (
        CapabilityAcceptanceContract(
            "AUTHENTICATION",
            "1.0",
            "Preview customer authentication",
            ("authentication.login",),
        ),
        CapabilityAcceptanceContract(
            "RECORDS",
            "1.0",
            "Preview customer record workflow",
            ("records.create_and_view", "records.refresh_persistence"),
        ),
        CapabilityAcceptanceContract(
            "VALIDATION",
            "1.0",
            "Preview validation recovery",
            ("validation.safe_recovery",),
        ),
    )
    required = (
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
    )
    journeys = tuple(
        AcceptanceJourney(journey_id, capability_id, title, required)
        for journey_id, capability_id, title, _, _ in JOURNEY_SPECS
    )
    return RuntimeAcceptanceProfile(
        "fixture-complete-runtime-v1",
        "1.0",
        capabilities,
        journeys,
    )


def _configuration(preview) -> ManagedProductRuntimeConfiguration:  # noqa: ANN001
    profile = _profile()
    origin = preview.preview_url
    return ManagedProductRuntimeConfiguration(
        configuration_id="fixture-preview-runtime",
        project_id="fixture-preview-product",
        revision=1,
        repository_url=f"https://github.com/{preview.repository_full_name}.git",
        branch=preview.feature_branch,
        commit_sha=preview.approved_commit,
        frontend_url=f"{origin}/",
        backend_url=f"{origin}/api",
        allowed_origins=(origin,),
        migration_commands=(),
        services=(
            ManagedRuntimeService(
                "preview-app",
                CommandSpec("python", ("service.py",)),
                ReadinessProbe("preview-ready", f"{origin}/health"),
                OneShotCommand("stop-preview-app", CommandSpec("python", ("stop.py",))),
            ),
        ),
        environment_allow_list=(),
        environment=(),
        secret_references=(),
        acceptance_profile_id=profile.profile_id,
        acceptance_profile_version=profile.version,
        acceptance_profile_digest=profile.digest,
        created_by="day35-fixture",
        created_at=NOW + timedelta(minutes=110),
    )


def _steps(title: str, path: str, expected: str) -> tuple[BrowserStep, ...]:
    return (
        BrowserStep(
            f"{title}-email",
            BrowserActionKind.FILL,
            BrowserLocator(BrowserLocatorKind.LABEL, "Email"),
            "user-email",
        ),
        BrowserStep(
            f"{title}-password",
            BrowserActionKind.FILL,
            BrowserLocator(BrowserLocatorKind.LABEL, "Password"),
            "user-password",
        ),
        BrowserStep(
            f"{title}-submit",
            BrowserActionKind.CLICK,
            BrowserLocator(BrowserLocatorKind.ROLE, "button", "Run journey"),
        ),
        BrowserStep(
            f"{title}-result",
            BrowserActionKind.ASSERT_TEXT,
            BrowserLocator(BrowserLocatorKind.TEST_ID, "journey-result"),
            expected_text=expected,
        ),
        BrowserStep(
            f"{title}-path",
            BrowserActionKind.ASSERT_URL_PATH,
            expected_path=path,
        ),
    )


def _plan(configuration: ManagedProductRuntimeConfiguration) -> BrowserJourneyPlan:
    profile = _profile()
    journeys = tuple(
        BrowserJourneySpecification(
            journey_id,
            capability_id,
            title,
            path,
            _steps(journey_id.replace(".", "-"), path, expected),
            30,
        )
        for journey_id, capability_id, title, path, expected in JOURNEY_SPECS
    )
    return BrowserJourneyPlan(
        plan_id="fixture-complete-runtime-plan",
        run_id="fixture-complete-runtime-run",
        product_id=configuration.project_id,
        configuration_id=configuration.configuration_id,
        configuration_revision=configuration.revision,
        configuration_digest=configuration.digest,
        commit_sha=configuration.commit_sha,
        acceptance_profile_id=profile.profile_id,
        acceptance_profile_version=profile.version,
        acceptance_profile_digest=profile.digest,
        journeys=journeys,
        inputs=(
            BrowserInputBinding("user-email", "founder@example.invalid"),
            BrowserInputBinding(
                "user-password", secret_reference="fixture.preview-login-password"
            ),
        ),
        created_by="day35-fixture",
        created_at=NOW + timedelta(minutes=111),
    )


def _work_order(preview, configuration, plan, **changes):  # noqa: ANN001
    values = {
        "work_order_id": "work-order-complete-runtime-acceptance-1",
        "tenant_id": preview.tenant_id,
        "opportunity_id": preview.opportunity_id,
        "assignment_id": "assignment-complete-runtime-acceptance-1",
        "preview_artifact_digest": preview.digest,
        "product_id": configuration.project_id,
        "runtime_configuration_id": configuration.configuration_id,
        "runtime_configuration_revision": configuration.revision,
        "runtime_configuration_digest": configuration.digest,
        "acceptance_run_id": plan.run_id,
        "acceptance_profile_id": plan.acceptance_profile_id,
        "acceptance_profile_version": plan.acceptance_profile_version,
        "acceptance_profile_digest": plan.acceptance_profile_digest,
        "browser_plan_id": plan.plan_id,
        "browser_plan_digest": plan.digest,
        "repository_id": preview.repository_id,
        "repository_full_name": preview.repository_full_name,
        "feature_branch": preview.feature_branch,
        "approved_commit": preview.approved_commit,
        "approved_tree": preview.approved_tree,
        "preview_environment_id": preview.preview_environment_id,
        "preview_url": preview.preview_url,
        "deployment_revision": preview.deployment_revision,
        "preview_configuration_digest": preview.configuration_digest,
        "capability_ids": tuple(
            dict.fromkeys(item.capability_id for item in plan.journeys)
        ),
        "journey_ids": tuple(item.journey_id for item in plan.journeys),
        "authentication_journey_id": "authentication.login",
        "login_secret_reference_ids": ("fixture.preview-login-password",),
        "objectives": (
            "Verify the exact persisted Day 34 isolated preview",
            "Log in through only an opaque credential reference",
            "Execute every locked module-specific end-user journey in Chromium",
            "Persist complete secret-safe browser evidence for founder review",
        ),
        "acceptance_checks": (
            "Preview source is exact, healthy, current, and non-production",
            "Runtime configuration and browser plan are both persisted and immutable",
            "Repository, branch, commit, tree, profile, and preview origin are exact",
            "Authentication journey completes with a scoped opaque login reference",
            "Every declared module journey returns PASS",
            "Every journey has browser, console, network, and screenshot evidence",
            "Console and network failure counts remain zero",
            "Repository write, preview mutation, production, merge, and release counts stay zero",
        ),
        "constraints": (
            "Use one isolated Chromium launch for the exact declared plan",
            "Do not accept raw passwords, tokens, cookies, or credential values",
            "Do not change the preview environment or its deployed source",
            "Do not write a repository, approve a pull request, or merge",
            "Do not deploy or promote production",
            "Do not release, bill, spend budget, or accept risk",
            "Do not select an official product pilot",
            "Do not start Day 36 end-to-end pilot work",
        ),
        "issued_at": NOW + timedelta(minutes=109),
        "expires_at": NOW + timedelta(hours=7),
    }
    values.update(changes)
    return CompleteRuntimeAcceptanceWorkOrder(**values)


def _authority(order: CompleteRuntimeAcceptanceWorkOrder, **changes):
    values = {
        "authority_id": "authority-complete-runtime-acceptance-1",
        "issuer_id": "founder-day35-runtime-acceptance-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "work_order_digest": order.digest,
        "preview_artifact_digest": order.preview_artifact_digest,
        "product_id": order.product_id,
        "acceptance_run_id": order.acceptance_run_id,
        "browser_plan_digest": order.browser_plan_digest,
        "approved_commit": order.approved_commit,
        "preview_environment_id": order.preview_environment_id,
        "allowed_action_ids": COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS,
        "allowed_tool_ids": COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS,
        "issued_at": NOW + timedelta(minutes=109),
        "expires_at": NOW + timedelta(hours=7),
        "max_browser_launches": 1,
        "max_journeys": 12,
        "max_secret_references": 4,
    }
    values.update(changes)
    return CompleteRuntimeAcceptanceAuthority(**values)


def _fixture(tmp_path: Path, browser_provider=None):  # noqa: ANN001
    *_, preview = _run_preview(tmp_path)
    configuration = _configuration(preview)
    configuration_store = FileRuntimeConfigurationStore(tmp_path / "runtime-config")
    configuration_store.save(configuration)
    plan = _plan(configuration)
    plan_store = FileBrowserJourneyPlanStore(tmp_path / "browser-plans-day35")
    plan_store.save(plan)
    order = _work_order(preview, configuration, plan)
    authority = _authority(order)
    resolver = MappingResolver({"fixture.preview-login-password": PASSWORD})
    selected_provider = browser_provider or DeterministicCompleteBrowserProvider()
    controlled = ControlledCompleteRuntimeAcceptanceProvider(
        selected_provider,
        resolver,
        ContentAddressedBrowserArtifactStore(tmp_path / "day35-browser-artifacts"),
    )
    service = CompleteRuntimeAcceptanceService(
        controlled,
        preview_store=_preview_store(tmp_path),
        configuration_store=configuration_store,
        plan_store=plan_store,
        artifact_store=FileCompleteRuntimeAcceptanceArtifactStore(
            tmp_path / "complete-runtime-acceptance-state"
        ),
        clock=lambda: NOW + timedelta(minutes=120),
    )
    return (
        service,
        controlled,
        selected_provider,
        resolver,
        preview,
        configuration,
        plan,
        order,
        authority,
    )


def _preview_store(tmp_path: Path):
    from runtime.preview_deployment import FilePreviewDeploymentArtifactStore

    return FilePreviewDeploymentArtifactStore(tmp_path / "preview-deployment-state")


def _run_acceptance(tmp_path: Path, browser_provider=None):  # noqa: ANN001
    values = _fixture(tmp_path, browser_provider)
    service, _, _, _, preview, configuration, plan, order, authority = values
    artifact = service.run(
        execution_id="execution-complete-runtime-acceptance-1",
        work_order=order,
        authority=authority,
        preview_artifact=preview,
        runtime_configuration=configuration,
        browser_plan=plan,
    )
    return (*values, artifact)


def test_complete_runtime_acceptance_runs_all_declared_journeys_once(tmp_path: Path) -> None:
    (
        service,
        controlled,
        browser,
        resolver,
        preview,
        configuration,
        plan,
        _,
        _,
        artifact,
    ) = _run_acceptance(tmp_path)
    assert controlled.execution_count == browser.calls == 1
    assert resolver.calls == ["fixture.preview-login-password"]
    assert artifact.preview_artifact_digest == preview.digest
    assert artifact.runtime_configuration_digest == configuration.digest
    assert artifact.browser_plan_digest == plan.digest
    assert artifact.journey_ids == tuple(item.journey_id for item in plan.journeys)
    assert all(item.outcome == "PASS" for item in artifact.journey_receipts)
    assert artifact.evidence_artifact_count == 4 * len(plan.journeys)
    assert artifact.screenshot_count == len(plan.journeys)
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_runtime_source_chain_and_terminal_states_are_exact(tmp_path: Path) -> None:
    *_, artifact = _run_acceptance(tmp_path)
    assert artifact.preview_state == PREVIEW_STATE
    assert artifact.authentication_state == AUTHENTICATION_STATE
    assert artifact.journey_state == JOURNEY_STATE
    assert artifact.browser_state == BROWSER_STATE
    assert artifact.production_state == PRODUCTION_STATE
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS
    assert artifact.governance_capability_ids == COMPLETE_RUNTIME_ACCEPTANCE_CAPABILITIES
    assert artifact.action_ids == COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS
    assert artifact.tool_ids == COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS
    assert artifact.preview_mutation_count == artifact.production_deployment_count == 0
    assert artifact.repository_write_count == artifact.merge_count == artifact.release_count == 0


def test_exact_retry_and_restart_do_not_launch_chromium_again(tmp_path: Path) -> None:
    values = _run_acceptance(tmp_path)
    service, controlled, browser, _, preview, configuration, plan, order, authority, expected = values
    kwargs = {
        "execution_id": expected.execution_id,
        "work_order": order,
        "authority": authority,
        "preview_artifact": preview,
        "runtime_configuration": configuration,
        "browser_plan": plan,
    }
    assert service.run(**kwargs) == expected
    restarted_browser = DeterministicCompleteBrowserProvider()
    restarted_controlled = ControlledCompleteRuntimeAcceptanceProvider(
        restarted_browser,
        MappingResolver({"fixture.preview-login-password": PASSWORD}),
        ContentAddressedBrowserArtifactStore(tmp_path / "unused-browser-artifacts"),
    )
    restarted = CompleteRuntimeAcceptanceService(
        restarted_controlled,
        _preview_store(tmp_path),
        FileRuntimeConfigurationStore(tmp_path / "runtime-config"),
        FileBrowserJourneyPlanStore(tmp_path / "browser-plans-day35"),
        FileCompleteRuntimeAcceptanceArtifactStore(
            tmp_path / "complete-runtime-acceptance-state"
        ),
        clock=lambda: NOW + timedelta(minutes=121),
    )
    assert restarted.run(**kwargs) == expected
    assert controlled.execution_count == browser.calls == 1
    assert restarted_controlled.execution_count == restarted_browser.calls == 0


def test_changed_retry_conflicts_without_another_browser_launch(tmp_path: Path) -> None:
    values = _run_acceptance(tmp_path)
    service, controlled, browser, _, preview, configuration, plan, order, _, artifact = values
    changed = _work_order(
        preview,
        configuration,
        plan,
        objectives=order.objectives[:-1] + ("Changed objective is forbidden on retry",),
    )
    with pytest.raises(RuntimeAcceptanceConflict):
        service.run(
            execution_id=artifact.execution_id,
            work_order=changed,
            authority=_authority(changed),
            preview_artifact=preview,
            runtime_configuration=configuration,
            browser_plan=plan,
        )
    assert controlled.execution_count == browser.calls == 1


@pytest.mark.parametrize(
    "change",
    (
        {"assignment_id": "wrong-assignment"},
        {"product_id": "wrong-product"},
        {"acceptance_run_id": "wrong-run"},
        {"approved_commit": "f" * 40},
        {"preview_environment_id": "wrong-environment"},
        {"browser_plan_digest": "0" * 64},
    ),
)
def test_authority_drift_fails_before_browser_launch(tmp_path: Path, change) -> None:
    service, controlled, browser, _, preview, configuration, plan, order, _ = _fixture(tmp_path)
    with pytest.raises(RuntimeAcceptancePolicyError):
        service.run(
            execution_id="execution-authority-drift",
            work_order=order,
            authority=_authority(order, **change),
            preview_artifact=preview,
            runtime_configuration=configuration,
            browser_plan=plan,
        )
    assert controlled.execution_count == browser.calls == 0


def test_expired_authority_fails_before_browser_launch(tmp_path: Path) -> None:
    service, controlled, browser, _, preview, configuration, plan, order, _ = _fixture(tmp_path)
    authority = _authority(
        order,
        issued_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=119),
    )
    with pytest.raises(RuntimeAcceptancePolicyError, match="authority"):
        service.run(
            execution_id="execution-expired-authority",
            work_order=order,
            authority=authority,
            preview_artifact=preview,
            runtime_configuration=configuration,
            browser_plan=plan,
        )
    assert controlled.execution_count == browser.calls == 0


def test_unpersisted_configuration_or_plan_drift_fails_closed(tmp_path: Path) -> None:
    service, controlled, browser, _, preview, configuration, plan, order, authority = _fixture(tmp_path)
    with pytest.raises(RuntimeAcceptancePolicyError, match="persisted configuration"):
        service.run(
            execution_id="execution-config-drift",
            work_order=order,
            authority=authority,
            preview_artifact=preview,
            runtime_configuration=replace(configuration, created_by="changed-actor"),
            browser_plan=plan,
        )
    with pytest.raises(RuntimeAcceptancePolicyError, match="persisted browser plan"):
        service.run(
            execution_id="execution-plan-drift",
            work_order=order,
            authority=authority,
            preview_artifact=preview,
            runtime_configuration=configuration,
            browser_plan=replace(plan, created_by="changed-actor"),
        )
    assert controlled.execution_count == browser.calls == 0


class FailingBrowserProvider(DeterministicCompleteBrowserProvider):
    def execute(self, plan, configuration, inputs, redactions, artifact_store):  # noqa: ANN001
        value = super().execute(plan, configuration, inputs, redactions, artifact_store)
        failed_evidence = replace(value.evidence[0], outcome=EvidenceOutcome.FAIL)
        failed_result = replace(
            value.journey_results[0],
            outcome=EvidenceOutcome.FAIL,
        )
        return BrowserExecutionResult(
            value.run_id,
            value.product_id,
            value.plan_id,
            value.plan_digest,
            value.commit_sha,
            BrowserExecutionStage.FAILED,
            (failed_evidence,) + value.evidence[1:],
            (failed_result,) + value.journey_results[1:],
            value.started_at,
            value.completed_at,
            "BROWSER_JOURNEY_FAILED",
        )


def test_failed_journey_never_claims_runtime_acceptance(tmp_path: Path) -> None:
    browser = FailingBrowserProvider()
    service, controlled, _, _, preview, configuration, plan, order, authority = _fixture(
        tmp_path, browser
    )
    with pytest.raises(RuntimeAcceptancePolicyError, match="did not complete"):
        service.run(
            execution_id="execution-failed-journey",
            work_order=order,
            authority=authority,
            preview_artifact=preview,
            runtime_configuration=configuration,
            browser_plan=plan,
        )
    assert controlled.execution_count == browser.calls == 1
    with pytest.raises(RuntimeAcceptanceNotFound):
        service.get(order.tenant_id, "execution-failed-journey")


def test_persistence_is_mode_0600_restart_safe_and_tamper_evident(tmp_path: Path) -> None:
    *_, artifact = _run_acceptance(tmp_path)
    path = (
        tmp_path
        / "complete-runtime-acceptance-state"
        / artifact.tenant_id
        / artifact.execution_id
        / "complete-runtime-acceptance-v1.json"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    envelope = json.loads(path.read_text())
    envelope["record"]["production_deployment_count"] = 1
    path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    os.chmod(path, 0o600)
    store = FileCompleteRuntimeAcceptanceArtifactStore(
        tmp_path / "complete-runtime-acceptance-state"
    )
    with pytest.raises(RuntimeAcceptanceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_persistence_rejects_unknown_entries_permissions_and_escape(tmp_path: Path) -> None:
    *_, artifact = _run_acceptance(tmp_path)
    directory = (
        tmp_path
        / "complete-runtime-acceptance-state"
        / artifact.tenant_id
        / artifact.execution_id
    )
    path = directory / "complete-runtime-acceptance-v1.json"
    (directory / "unexpected.txt").write_text("unsafe", encoding="utf-8")
    store = FileCompleteRuntimeAcceptanceArtifactStore(
        tmp_path / "complete-runtime-acceptance-state"
    )
    with pytest.raises(RuntimeAcceptanceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    (directory / "unexpected.txt").unlink()
    os.chmod(path, 0o644)
    with pytest.raises(RuntimeAcceptanceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    with pytest.raises(RuntimeAcceptanceCorrupt):
        store.load("../tenant", "execution")


def test_models_reject_raw_login_secret_and_elevated_authority(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Secret-bearing"):
        BrowserInputBinding("user-password", "plaintext-password")
    *_, order, _ = _fixture(tmp_path)[-2:]
    with pytest.raises(ValueError):
        _authority(order, repository_write_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, preview_mutation_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, production_deployment_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, merge_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, release_allowed=True)
    with pytest.raises(ValueError):
        _authority(order, pilot_selection_allowed=True)


def test_day35_profile_contains_no_merge_production_release_or_day36_action() -> None:
    for forbidden in (
        "WRITE_REPOSITORY",
        "APPROVE_PULL_REQUEST",
        "MERGE_PULL_REQUEST",
        "DEPLOY_PRODUCTION",
        "PROMOTE_TO_PRODUCTION",
        "RELEASE",
        "BILL_CUSTOMER",
        "SELECT_PILOT_PRODUCT",
        "RUN_FIRST_END_TO_END_PILOT",
    ):
        assert forbidden not in COMPLETE_RUNTIME_ACCEPTANCE_ACTIONS
    assert COMPLETE_RUNTIME_ACCEPTANCE_TOOL_IDS == (
        "ISOLATED_CHROMIUM",
        "OPAQUE_RUNTIME_CREDENTIALS",
    )
