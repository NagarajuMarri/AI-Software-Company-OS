"""Closed GitHub Actions preview and Playwright acceptance adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import subprocess
import time
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from runtime.customer_acceptance.errors import (
    CustomerAcceptanceConflict,
    CustomerAcceptancePolicyError,
)
from runtime.customer_acceptance.models import (
    CustomerAcceptanceConfiguration,
    CustomerAcceptanceRecord,
    CustomerAcceptanceStatus,
    PreviewDeploymentReceipt,
    WorkflowJobReceipt,
)
from runtime.managed_product_browser import (
    BrowserExecutionResult,
    BrowserExecutionStage,
    BrowserJourneyPlan,
    ContentAddressedBrowserArtifactStore,
    FileBrowserExecutionStore,
    PlaywrightChromiumProvider,
)
from runtime.runtime_acceptance import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
)


@dataclass(frozen=True)
class CustomerAcceptanceOutcome:
    deployment: PreviewDeploymentReceipt
    browser: BrowserExecutionResult
    evidence: tuple[EvidenceArtifact, ...]


class PreviewDeploymentGateway(Protocol):
    def preflight(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
    ) -> None: ...

    def deploy(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
    ) -> PreviewDeploymentReceipt: ...


class PreviewBrowserGateway(Protocol):
    def execute(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
        plan: BrowserJourneyPlan,
    ) -> BrowserExecutionResult: ...


class CustomerAcceptanceAdapter(Protocol):
    def preflight(self, record: CustomerAcceptanceRecord, plan: BrowserJourneyPlan) -> None: ...

    def execute(
        self,
        record: CustomerAcceptanceRecord,
        plan: BrowserJourneyPlan,
    ) -> CustomerAcceptanceOutcome: ...


class GitHubActionsPreviewGateway:
    """Dispatch one preview-only workflow using an existing GitHub CLI login."""

    provider_id = "github-actions-isolated-preview-v1"

    def __init__(self, executable: str = "gh", *, clock=None) -> None:  # noqa: ANN001
        self._executable = executable
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def preflight(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
    ) -> None:
        pull_request = self._json(
            "pr",
            "view",
            str(record.pull_request_number),
            "--repo",
            record.repository_full_name,
            "--json",
            "number,url,isDraft,state,baseRefName,headRefName,headRefOid",
        )
        if not isinstance(pull_request, dict) or not (
            pull_request.get("number") == record.pull_request_number
            and pull_request.get("url") == record.pull_request_url
            and pull_request.get("isDraft") is True
            and str(pull_request.get("state", "")).upper() == "OPEN"
            and pull_request.get("baseRefName") == record.base_branch
            and pull_request.get("headRefName") == record.head_branch
            and pull_request.get("headRefOid") == record.commit_sha
        ):
            raise CustomerAcceptanceConflict("Draft PR no longer matches preview authority")
        self._run(
            "workflow",
            "view",
            configuration.workflow_file,
            "--repo",
            record.repository_full_name,
            "--yaml",
        )

    def deploy(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
    ) -> PreviewDeploymentReceipt:
        self.preflight(record, configuration)
        before = self._run_ids(record, configuration)
        self._run(
            "workflow",
            "run",
            configuration.workflow_file,
            "--repo",
            record.repository_full_name,
            "--ref",
            record.head_branch,
            "--field",
            f"ascos_commit_sha={record.commit_sha}",
            "--field",
            f"ascos_tree_sha={record.tree_sha}",
            "--field",
            f"ascos_preview_environment={configuration.preview_environment_id}",
            "--field",
            f"ascos_preview_url={configuration.preview_url}",
            "--field",
            f"ascos_execution_id={record.acceptance_id}",
        )
        workflow = self._find_new_run(record, configuration, before)
        run_id = _positive_int(workflow.get("databaseId"), "workflow run ID")
        try:
            self._run(
                "run",
                "watch",
                str(run_id),
                "--repo",
                record.repository_full_name,
                "--exit-status",
                timeout=configuration.workflow_timeout_seconds,
            )
        except CustomerAcceptancePolicyError:
            raise
        result = self._json(
            "run",
            "view",
            str(run_id),
            "--repo",
            record.repository_full_name,
            "--json",
            "databaseId,headSha,status,conclusion,url,workflowName,jobs",
        )
        if not isinstance(result, dict) or not (
            result.get("databaseId") == run_id
            and result.get("headSha") == record.commit_sha
            and str(result.get("status", "")).upper() == "COMPLETED"
            and str(result.get("conclusion", "")).upper() == "SUCCESS"
        ):
            raise CustomerAcceptancePolicyError("Preview workflow did not complete successfully")
        jobs = self._required_jobs(result.get("jobs"), configuration)
        status, health_digest = _health(configuration.preview_url)
        url = result.get("url")
        if not isinstance(url, str):
            raise CustomerAcceptancePolicyError("Preview workflow URL is invalid")
        return PreviewDeploymentReceipt(
            provider_id=self.provider_id,
            workflow_run_id=run_id,
            workflow_run_url=url,
            repository_full_name=record.repository_full_name,
            branch=record.head_branch,
            commit_sha=record.commit_sha,
            tree_sha=record.tree_sha,
            preview_environment_id=configuration.preview_environment_id,
            preview_url=configuration.preview_url,
            deployment_revision=f"preview-run-{run_id}",
            health_status_code=status,
            health_digest=health_digest,
            jobs=jobs,
            deployed_at=self._clock(),
        )

    def _run_ids(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
    ) -> set[int]:
        values = self._runs(record, configuration)
        identifiers: set[int] = set()
        for value in values:
            identifier = value.get("databaseId")
            if isinstance(identifier, int) and not isinstance(identifier, bool):
                identifiers.add(identifier)
        return identifiers

    def _find_new_run(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
        before: set[int],
    ) -> dict[str, object]:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            matches = [
                value
                for value in self._runs(record, configuration)
                if value.get("databaseId") not in before
                and value.get("headSha") == record.commit_sha
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise CustomerAcceptancePolicyError("Preview workflow dispatch is ambiguous")
            time.sleep(1)
        raise CustomerAcceptancePolicyError("Preview workflow dispatch was not observed")

    def _runs(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
    ) -> list[dict[str, object]]:
        value = self._json(
            "run",
            "list",
            "--repo",
            record.repository_full_name,
            "--workflow",
            configuration.workflow_file,
            "--branch",
            record.head_branch,
            "--event",
            "workflow_dispatch",
            "--limit",
            "20",
            "--json",
            "databaseId,headSha,status,conclusion,url,workflowName,createdAt",
        )
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise CustomerAcceptancePolicyError("GitHub returned an invalid workflow list")
        return value

    @staticmethod
    def _required_jobs(
        value: object,
        configuration: CustomerAcceptanceConfiguration,
    ) -> tuple[WorkflowJobReceipt, ...]:
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise CustomerAcceptancePolicyError("GitHub returned invalid workflow jobs")
        selected = []
        for name in (configuration.automated_test_job, configuration.security_job):
            matches = [item for item in value if item.get("name") == name]
            if len(matches) != 1:
                raise CustomerAcceptancePolicyError("A required preview workflow job is missing")
            item = matches[0]
            selected.append(
                WorkflowJobReceipt(
                    job_id=_positive_int(item.get("databaseId"), "workflow job ID"),
                    name=name,
                    conclusion=str(item.get("conclusion", "")).upper(),
                    url=item.get("url"),
                )
            )
        return tuple(selected)

    def _json(self, *arguments: str) -> object:
        try:
            return json.loads(self._run(*arguments).stdout)
        except json.JSONDecodeError as error:
            raise CustomerAcceptancePolicyError("GitHub returned invalid JSON") from error

    def _run(
        self,
        *arguments: str,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        if shutil.which(self._executable) is None:
            raise CustomerAcceptancePolicyError("GitHub CLI is unavailable")
        try:
            result = subprocess.run(
                (self._executable, *arguments),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise CustomerAcceptancePolicyError("GitHub preview operation timed out") from error
        if result.returncode:
            raise CustomerAcceptancePolicyError("GitHub preview operation failed")
        return result


class EnvironmentBrowserInputResolver:
    """Resolve approved opaque references only from the launcher environment."""

    def __init__(self, environment: dict[str, str] | None = None) -> None:
        self._environment = environment if environment is not None else os.environ

    def resolve(self, reference: str) -> str:
        value = self._environment.get(reference)
        if not isinstance(value, str) or not value or len(value) > 8_192 or "\0" in value:
            raise CustomerAcceptancePolicyError("Opaque browser input is unavailable")
        return value


class PlaywrightPreviewBrowserGateway:
    """Run exact declarative journeys against an already-deployed preview."""

    def __init__(
        self,
        result_store: FileBrowserExecutionStore,
        artifact_store: ContentAddressedBrowserArtifactStore,
        resolver: EnvironmentBrowserInputResolver | None = None,
        provider: PlaywrightChromiumProvider | None = None,
    ) -> None:
        self._results = result_store
        self._artifacts = artifact_store
        self._resolver = resolver or EnvironmentBrowserInputResolver()
        self._provider = provider or PlaywrightChromiumProvider()

    def execute(
        self,
        record: CustomerAcceptanceRecord,
        configuration: CustomerAcceptanceConfiguration,
        plan: BrowserJourneyPlan,
    ) -> BrowserExecutionResult:
        existing = self._results.find(plan.product_id, plan.run_id, plan.plan_id)
        if existing is not None:
            if existing.plan_digest != plan.digest:
                raise CustomerAcceptancePolicyError("Stored browser result has different authority")
            for item in existing.evidence:
                self._artifacts.verify(item.artifact_uri, item.digest)
            return existing
        inputs: dict[str, str] = {}
        redactions: list[str] = []
        cdp_endpoint: str | None = None
        try:
            for binding in plan.inputs:
                if binding.public_value is not None:
                    inputs[binding.input_id] = binding.public_value
                else:
                    assert binding.secret_reference is not None
                    resolved = self._resolver.resolve(binding.secret_reference)
                    inputs[binding.input_id] = resolved
                    redactions.append(resolved)
            if configuration.browser_cdp_reference is not None:
                cdp_endpoint = self._resolver.resolve(configuration.browser_cdp_reference)
                redactions.append(cdp_endpoint)
            result = self._provider.execute_preview(
                plan,
                configuration.preview_url,
                configuration.allowed_origins,
                inputs,
                tuple(redactions),
                self._artifacts,
                cdp_endpoint=cdp_endpoint,
            )
        finally:
            inputs.clear()
            redactions.clear()
            cdp_endpoint = None
        if (
            result.run_id != record.acceptance_id
            or result.product_id != record.product_id
            or result.plan_id != record.browser_plan_id
            or result.plan_digest != record.browser_plan_digest
            or result.commit_sha != record.commit_sha
        ):
            raise CustomerAcceptancePolicyError("Browser result differs from exact preview authority")
        return self._results.save(result)


class ControlledCustomerAcceptanceAdapter:
    """Compose one preview workflow and one exact Playwright acceptance run."""

    def __init__(
        self,
        configuration: CustomerAcceptanceConfiguration,
        deployment_gateway: PreviewDeploymentGateway,
        browser_gateway: PreviewBrowserGateway,
        artifact_store: ContentAddressedBrowserArtifactStore,
        *,
        clock=None,  # noqa: ANN001
    ) -> None:
        self._configuration = configuration
        self._deployment = deployment_gateway
        self._browser = browser_gateway
        self._artifacts = artifact_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def preflight(self, record: CustomerAcceptanceRecord, plan: BrowserJourneyPlan) -> None:
        if record.status not in {
            CustomerAcceptanceStatus.APPROVED,
            CustomerAcceptanceStatus.EXECUTION_IN_PROGRESS,
        }:
            raise CustomerAcceptanceConflict("Exact preview acceptance is not approved")
        self._binding(record, plan)
        self._deployment.preflight(record, self._configuration)

    def execute(
        self,
        record: CustomerAcceptanceRecord,
        plan: BrowserJourneyPlan,
    ) -> CustomerAcceptanceOutcome:
        self._binding(record, plan)
        deployment = self._deployment.deploy(record, self._configuration)
        self._validate_deployment(record, deployment)
        automated = self._workflow_evidence(record, deployment, EvidenceKind.AUTOMATED_TEST)
        security = self._workflow_evidence(record, deployment, EvidenceKind.SECURITY)
        browser = self._browser.execute(record, self._configuration, plan)
        evidence = (automated, security) + browser.evidence
        self._validate_browser(record, plan, browser, evidence)
        return CustomerAcceptanceOutcome(deployment, browser, evidence)

    def _binding(self, record: CustomerAcceptanceRecord, plan: BrowserJourneyPlan) -> None:
        if not (
            self._configuration.live_enabled
            and record.configuration_digest == self._configuration.digest
            and record.preview_environment_id == self._configuration.preview_environment_id
            and record.preview_url == self._configuration.preview_url
            and record.workflow_file == self._configuration.workflow_file
            and record.browser_plan_id == plan.plan_id
            and record.browser_plan_digest == plan.digest
            and record.product_id == plan.product_id
            and record.commit_sha == plan.commit_sha
            and record.acceptance_id == plan.run_id
        ):
            raise CustomerAcceptancePolicyError("Acceptance provider binding changed")

    def _validate_deployment(
        self,
        record: CustomerAcceptanceRecord,
        deployment: PreviewDeploymentReceipt,
    ) -> None:
        if not isinstance(deployment, PreviewDeploymentReceipt) or not (
            deployment.repository_full_name == record.repository_full_name
            and deployment.branch == record.head_branch
            and deployment.commit_sha == record.commit_sha
            and deployment.tree_sha == record.tree_sha
            and deployment.preview_environment_id == record.preview_environment_id
            and deployment.preview_url == record.preview_url
            and {value.name for value in deployment.jobs}
            == {record.automated_test_job, record.security_job}
        ):
            raise CustomerAcceptancePolicyError("Preview deployment receipt changed authority")

    @staticmethod
    def _validate_browser(
        record: CustomerAcceptanceRecord,
        plan: BrowserJourneyPlan,
        browser: BrowserExecutionResult,
        evidence: tuple[EvidenceArtifact, ...],
    ) -> None:
        if not isinstance(browser, BrowserExecutionResult) or not (
            browser.stage in {BrowserExecutionStage.COMPLETED, BrowserExecutionStage.FAILED}
            and browser.run_id == record.acceptance_id
            and browser.product_id == record.product_id
            and browser.plan_id == record.browser_plan_id
            and browser.plan_digest == record.browser_plan_digest
            and browser.commit_sha == record.commit_sha
        ):
            raise CustomerAcceptancePolicyError("Browser acceptance result changed authority")
        planned = {value.journey_id: value for value in plan.journeys}
        results = {value.journey_id: value for value in browser.journey_results}
        if len(results) != len(browser.journey_results) or set(results) != set(planned):
            raise CustomerAcceptancePolicyError("Browser result did not cover every locked journey")
        evidence_ids = [value.evidence_id for value in evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise CustomerAcceptancePolicyError("Preview acceptance evidence is duplicated")
        browser_kinds = {
            EvidenceKind.BROWSER,
            EvidenceKind.BROWSER_CONSOLE,
            EvidenceKind.BROWSER_NETWORK,
            EvidenceKind.SCREENSHOT,
        }
        for journey_id, journey in planned.items():
            observed = tuple(value for value in browser.evidence if value.journey_id == journey_id)
            if (
                {value.kind for value in observed} != browser_kinds
                or any(
                    value.run_id != record.acceptance_id
                    or value.commit_sha != record.commit_sha
                    or value.capability_id != journey.capability_id
                    for value in observed
                )
                or set(results[journey_id].evidence_ids)
                != {value.evidence_id for value in observed}
            ):
                raise CustomerAcceptancePolicyError(
                    "A locked journey lacks complete exact browser evidence"
                )
        if {value.kind for value in evidence} != (
            browser_kinds | {EvidenceKind.AUTOMATED_TEST, EvidenceKind.SECURITY}
        ) or any(
            value.run_id != record.acceptance_id or value.commit_sha != record.commit_sha
            for value in evidence
        ):
            raise CustomerAcceptancePolicyError("Preview acceptance evidence is incomplete")

    def _workflow_evidence(
        self,
        record: CustomerAcceptanceRecord,
        deployment: PreviewDeploymentReceipt,
        kind: EvidenceKind,
    ) -> EvidenceArtifact:
        job_name = (
            record.automated_test_job
            if kind is EvidenceKind.AUTOMATED_TEST
            else record.security_job
        )
        job = next(value for value in deployment.jobs if value.name == job_name)
        payload = {
            "provider_id": deployment.provider_id,
            "workflow_run_id": deployment.workflow_run_id,
            "workflow_run_url": deployment.workflow_run_url,
            "job_id": job.job_id,
            "job_name": job.name,
            "job_url": job.url,
            "conclusion": job.conclusion,
            "commit_sha": deployment.commit_sha,
            "tree_sha": deployment.tree_sha,
            "preview_environment_id": deployment.preview_environment_id,
            "health_status_code": deployment.health_status_code,
            "health_digest": deployment.health_digest,
        }
        uri, digest = self._artifacts.write_json(record.product_id, record.acceptance_id, payload)
        suffix = "automated-tests" if kind is EvidenceKind.AUTOMATED_TEST else "security"
        return EvidenceArtifact(
            evidence_id=f"{record.acceptance_id}-{suffix}",
            run_id=record.acceptance_id,
            capability_id="product-preview-acceptance",
            journey_id="preview-deployment",
            kind=kind,
            outcome=EvidenceOutcome.PASS,
            commit_sha=record.commit_sha,
            artifact_uri=uri,
            digest=digest,
            observed_at=self._clock(),
            summary=f"Required preview workflow job passed: {job.name}",
            metadata=(("provider_id", deployment.provider_id),),
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        del req, fp, code, msg, headers, newurl
        return None


def _health(url: str) -> tuple[int, str]:
    request = Request(url + "/", headers={"User-Agent": "ASCOS-Preview-Health/1"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            status = int(response.status)
            content = response.read(65_537)
    except (HTTPError, URLError, OSError) as error:
        raise CustomerAcceptancePolicyError("Isolated preview health check failed") from error
    if not 200 <= status <= 399 or len(content) > 65_536:
        raise CustomerAcceptancePolicyError("Isolated preview health response is invalid")
    return status, hashlib.sha256(content).hexdigest()


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CustomerAcceptancePolicyError(f"GitHub returned an invalid {label}")
    return value
