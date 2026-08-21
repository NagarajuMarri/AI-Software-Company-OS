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
from runtime.customer_evidence import (
    CustomerPreviewEvidenceApplication,
    CustomerPreviewEvidenceService,
    FileCustomerPreviewEvidenceStore,
    preview_origin,
)
from runtime.customer_prd import (
    CustomerPrdApplication,
    CustomerPrdApprovalApplication,
    CustomerPrdApprovalService,
    CustomerPrdService,
    FileCustomerPrdApprovalStore,
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
) -> LocalUatApplication:
    """Build one persistent, loopback-oriented ASCOS local UAT application.

    The application exposes the real customer journey through Day 21. It does
    not start a provider, mutate a product repository, publish evidence, or
    perform deployment effects.
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
    prd_approvals = CustomerPrdApprovalService(
        FileCustomerPrdApprovalStore(root / "prd-approvals"),
        prds,
        clock,
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
    evidence = CustomerPreviewEvidenceService(
        FileCustomerPreviewEvidenceStore(root / "evidence"),
        progress,
        (canonical_origin,),
        clock,
    )

    customer_workspace = CustomerWorkspaceApplication(
        CustomerPortalApplication(requests),
        CustomerRequirementsApplication(requirements),
        CustomerRequirementsApprovalApplication(requirements_approvals),
        CustomerPrdApplication(prds, prd_approvals),
        CustomerPrdApprovalApplication(prd_approvals),
        CustomerRoadmapApplication(roadmaps, roadmap_approvals),
        CustomerRoadmapApprovalApplication(roadmap_approvals),
        CustomerDeliveryEstimateApplication(estimates),
        CustomerProjectProgressApplication(progress),
        CustomerPreviewEvidenceApplication(evidence),
    )
    workspace = LocalUatWorkspaceApplication(customer_workspace)
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
    return LocalUatApplication(authenticated)


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
