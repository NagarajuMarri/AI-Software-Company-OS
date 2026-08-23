"""Compose the real ASCOS customer applications into one local UAT service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import os
from pathlib import Path
from secrets import token_bytes

from runtime.customer_application import (
    CustomerPortalApplication,
    CustomerProductRequestService,
    FileCustomerProductRequestStore,
)
from runtime.customer_acceptance import (
    ControlledCustomerAcceptanceAdapter,
    CustomerAcceptanceApplication,
    CustomerAcceptanceConfiguration,
    CustomerAcceptanceService,
    EnvironmentBrowserInputResolver,
    FileCustomerAcceptanceStore,
    GitHubActionsPreviewGateway,
    PlaywrightPreviewBrowserGateway,
)
from runtime.customer_authentication import (
    AuthenticatedCustomerApplication,
    CustomerAuthenticationService,
    FileCustomerAccountStore,
    FileCustomerSessionStore,
)
from runtime.customer_estimate import (
    CustomerDeliveryEstimateApplication,
    CustomerDeliveryEstimateService,
    FileCustomerDeliveryEstimateStore,
)
from runtime.coding_providers import ProviderOperationStore
from runtime.customer_delivery import (
    ControlledCustomerDeliveryAdapter,
    CustomerDeliveryApplication,
    CustomerDeliveryConfiguration,
    CustomerDeliveryService,
    FileCustomerDeliveryStore,
    GitHubCliDraftPullRequestGateway,
)
from runtime.customer_evidence import (
    CustomerPreviewEvidenceApplication,
    CustomerPreviewEvidenceService,
    FileCustomerPreviewEvidenceStore,
    preview_origin,
)
from runtime.managed_product_browser import (
    ContentAddressedBrowserArtifactStore,
    FileBrowserExecutionStore,
    FileBrowserJourneyPlanStore,
)
from runtime.customer_execution import (
    CustomerExecutionApplication,
    CustomerExecutionConfiguration,
    CustomerExecutionService,
    FileCustomerExecutionStore,
    create_governed_codex_adapter,
)
from runtime.customer_prd import (
    CustomerPrdApplication,
    CustomerPrdApprovalApplication,
    CustomerPrdCriteriaApplication,
    CustomerPrdCriteriaService,
    CustomerPrdApprovalService,
    CustomerPrdService,
    FileCustomerPrdApprovalStore,
    FileCustomerPrdCriteriaStore,
    FileCustomerPrdStore,
)
from runtime.customer_progress import (
    CustomerProjectProgressApplication,
    CustomerProjectProgressService,
)
from runtime.customer_requirements import (
    CustomerRequirementsApprovalApplication,
    CustomerRequirementsApprovalService,
    CustomerRequirementsApplication,
    CustomerRequirementsService,
    CustomerWorkspaceApplication,
    FileCustomerRequirementsApprovalStore,
    FileCustomerRequirementsStore,
)
from runtime.customer_roadmap import (
    CustomerRoadmapApplication,
    CustomerRoadmapApprovalApplication,
    CustomerRoadmapApprovalService,
    CustomerRoadmapService,
    FileCustomerRoadmapApprovalStore,
    FileCustomerRoadmapStore,
)
from runtime.local_uat.web import LocalUatApplication, LocalUatWorkspaceApplication


Clock = Callable[[], datetime]
_SECRET_BYTES = 32
_SECRET_FILE = ".preauth-secret"


def create_local_uat_application(
    data_dir: Path,
    origin: str,
    *,
    clock: Clock | None = None,
    preauth_secret: bytes | None = None,
    execution_configuration: CustomerExecutionConfiguration | None = None,
    execution_adapter=None,
    delivery_configuration: CustomerDeliveryConfiguration | None = None,
    delivery_adapter=None,
    delivery_gateway=None,
    acceptance_configuration: CustomerAcceptanceConfiguration | None = None,
    acceptance_adapter=None,
    preview_deployment_gateway=None,
    preview_browser_gateway=None,
    browser_input_resolver=None,
    playwright_provider=None,
    codex_environment=None,
    codex_sdk_loader=None,
) -> LocalUatApplication:
    """Build one persistent, loopback-oriented ASCOS local UAT application.

    Without an execution configuration the launcher preserves the Day 21-only
    boundary. With an operator-bound configuration, explicit customer approval
    may invoke one governed Codex turn and apply its validated local patch. It
    Without a separately bound delivery configuration it never commits, pushes,
    or opens a PR. Completion Module 4 may create one reviewed commit, one
    non-force feature-branch push, and one open draft PR. It never merges,
    deploys production, releases, or selects a pilot product. Completion Module
    5 may dispatch one operator-bound isolated preview workflow and run one
    locked Playwright plan before publishing evidence for ACCEPT/REVISE review.
    """

    root = _prepare_root(data_dir)
    canonical_origin = preview_origin(f"{origin.rstrip('/')}/")
    if canonical_origin != origin:
        raise ValueError("Local UAT origin must be canonical and have no trailing slash")
    secret = bytes(preauth_secret) if preauth_secret is not None else _local_secret(root)
    if len(secret) < _SECRET_BYTES:
        raise ValueError("Local UAT pre-authentication secret must contain at least 32 bytes")

    requests = CustomerProductRequestService(
        FileCustomerProductRequestStore(root / "requests"),
        clock,
    )
    requirements_approval_store = FileCustomerRequirementsApprovalStore(
        root / "requirements-approvals"
    )
    requirements = CustomerRequirementsService(
        FileCustomerRequirementsStore(root / "requirements"),
        requests,
        clock,
        requirements_approval_store.is_locked,
    )
    requirements_approvals = CustomerRequirementsApprovalService(
        requirements_approval_store,
        requirements,
        clock,
    )
    prds = CustomerPrdService(
        FileCustomerPrdStore(root / "prds"),
        requirements_approvals,
        clock,
    )
    prd_approval_store = FileCustomerPrdApprovalStore(root / "prd-approvals")
    prd_criteria = CustomerPrdCriteriaService(
        FileCustomerPrdCriteriaStore(root / "prd-criteria"),
        prds,
        clock,
        prd_approval_locked=prd_approval_store.is_locked,
    )
    prd_approvals = CustomerPrdApprovalService(
        prd_approval_store,
        prds,
        clock,
        criteria=prd_criteria,
    )
    roadmaps = CustomerRoadmapService(
        FileCustomerRoadmapStore(root / "roadmaps"),
        prd_approvals,
        clock,
    )
    roadmap_approvals = CustomerRoadmapApprovalService(
        FileCustomerRoadmapApprovalStore(root / "roadmap-approvals"),
        roadmaps,
        clock,
    )
    estimates = CustomerDeliveryEstimateService(
        FileCustomerDeliveryEstimateStore(root / "estimates"),
        roadmap_approvals,
        clock,
    )
    progress = CustomerProjectProgressService(estimates)
    evidence_origins = [canonical_origin]
    if acceptance_configuration is not None:
        evidence_origins.append(preview_origin(acceptance_configuration.preview_url + "/"))
    evidence = CustomerPreviewEvidenceService(
        FileCustomerPreviewEvidenceStore(root / "evidence"),
        progress,
        tuple(dict.fromkeys(evidence_origins)),
        clock,
    )
    if execution_configuration is not None and execution_adapter is None:
        execution_adapter = create_governed_codex_adapter(
            root / "execution",
            execution_configuration,
            environment=codex_environment,
            sdk_loader=codex_sdk_loader,
        )
    execution_service = CustomerExecutionService(
        FileCustomerExecutionStore(root / "execution" / "plans"),
        progress,
        estimates,
        execution_configuration,
        execution_adapter,
        clock,
    )
    if delivery_configuration is not None:
        if execution_configuration is None:
            raise ValueError("Delivery configuration requires execution configuration")
        if (
            delivery_configuration.workspace_root.resolve()
            != execution_configuration.workspace_root.resolve()
        ):
            raise ValueError("Delivery and execution must bind the same product workspace")
        if delivery_adapter is None:
            gateway = delivery_gateway or GitHubCliDraftPullRequestGateway()
            delivery_adapter = ControlledCustomerDeliveryAdapter(
                delivery_configuration,
                gateway,
            )
    delivery_service = CustomerDeliveryService(
        FileCustomerDeliveryStore(root / "delivery" / "reviews"),
        execution_service,
        ProviderOperationStore(root / "execution" / "provider-state"),
        delivery_configuration,
        delivery_adapter,
        clock,
    )
    if acceptance_configuration is not None:
        if delivery_configuration is None:
            raise ValueError("Preview acceptance configuration requires delivery configuration")
        artifacts = ContentAddressedBrowserArtifactStore(
            root / "acceptance" / "browser-artifacts"
        )
        if acceptance_adapter is None:
            browser = preview_browser_gateway or PlaywrightPreviewBrowserGateway(
                FileBrowserExecutionStore(root / "acceptance" / "browser-results"),
                artifacts,
                browser_input_resolver or EnvironmentBrowserInputResolver(),
                playwright_provider,
            )
            acceptance_adapter = ControlledCustomerAcceptanceAdapter(
                acceptance_configuration,
                preview_deployment_gateway or GitHubActionsPreviewGateway(),
                browser,
                artifacts,
                clock=clock,
            )
    acceptance_service = CustomerAcceptanceService(
        FileCustomerAcceptanceStore(root / "acceptance" / "records"),
        FileBrowserJourneyPlanStore(root / "acceptance" / "browser-plans"),
        delivery_service,
        evidence,
        acceptance_configuration,
        acceptance_adapter,
        clock,
    )

    customer_workspace = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(requirements_approvals),
        CustomerPrdApplication(prds, prd_approvals, criteria=prd_criteria),
        CustomerPrdApprovalApplication(prd_approvals),
        CustomerRoadmapApplication(roadmaps, roadmap_approvals),
        CustomerRoadmapApprovalApplication(roadmap_approvals),
        CustomerDeliveryEstimateApplication(estimates),
        CustomerProjectProgressApplication(progress),
        CustomerPreviewEvidenceApplication(evidence),
        CustomerExecutionApplication(
            execution_service,
            delivery_available=delivery_configuration is not None,
        ),
        CustomerDeliveryApplication(delivery_service),
        CustomerAcceptanceApplication(acceptance_service),
        prd_criteria=CustomerPrdCriteriaApplication(prd_criteria, prd_approvals),
    )
    workspace = LocalUatWorkspaceApplication(
        customer_workspace,
        execution_configured=execution_configuration is not None,
        live_execution_enabled=execution_service.live_enabled,
        delivery_configured=delivery_configuration is not None,
        live_delivery_enabled=delivery_service.live_enabled,
        acceptance_configured=acceptance_configuration is not None,
        live_acceptance_enabled=acceptance_service.live_enabled,
    )
    authentication = CustomerAuthenticationService(
        FileCustomerAccountStore(root / "authentication"),
        FileCustomerSessionStore(root / "authentication"),
        clock=clock,
    )
    authenticated = AuthenticatedCustomerApplication(
        authentication,
        workspace,
        preauth_secret=secret,
        secure_cookies=False,
        clock=clock,
    )
    return LocalUatApplication(
        authenticated,
        execution_configured=execution_configuration is not None,
        live_execution_enabled=execution_service.live_enabled,
        delivery_configured=delivery_configuration is not None,
        live_delivery_enabled=delivery_service.live_enabled,
        acceptance_configured=acceptance_configuration is not None,
        live_acceptance_enabled=acceptance_service.live_enabled,
    )


def _prepare_root(value: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink():
        raise ValueError("Local UAT data directory cannot be a symbolic link")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = path.resolve()
    if not root.is_dir():
        raise ValueError("Local UAT data directory is not a directory")
    if os.name != "nt":
        root.chmod(0o700)
    return root


def _local_secret(root: Path) -> bytes:
    path = root / _SECRET_FILE
    if path.is_symlink():
        raise ValueError("Local UAT secret file cannot be a symbolic link")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_secret(path)
    secret = token_bytes(_SECRET_BYTES)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(secret)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            path.chmod(0o600)
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return secret


def _read_secret(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("Local UAT secret file cannot be a symbolic link")
    secret = path.read_bytes()
    if len(secret) != _SECRET_BYTES:
        raise ValueError("Local UAT secret file is invalid")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ValueError("Local UAT secret file permissions are too broad")
    return secret
