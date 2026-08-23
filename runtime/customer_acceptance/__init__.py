"""Completion Module 5 isolated preview and browser acceptance."""

from runtime.customer_acceptance.errors import (
    CustomerAcceptanceConflict,
    CustomerAcceptanceCorrupt,
    CustomerAcceptanceError,
    CustomerAcceptanceNotConfigured,
    CustomerAcceptanceNotFound,
    CustomerAcceptancePolicyError,
    CustomerAcceptanceReconciliationRequired,
)
from runtime.customer_acceptance.models import (
    AcceptanceJourneySummary,
    CustomerAcceptanceConfiguration,
    CustomerAcceptanceRecord,
    CustomerAcceptanceStatus,
    PreviewDeploymentReceipt,
    WorkflowJobReceipt,
    acceptance_id_for,
    browser_plan_id_for,
    canonical_origin,
)
from runtime.customer_acceptance.persistence import FileCustomerAcceptanceStore
from runtime.customer_acceptance.planning import load_acceptance_plan
from runtime.customer_acceptance.provider import (
    ControlledCustomerAcceptanceAdapter,
    CustomerAcceptanceAdapter,
    CustomerAcceptanceOutcome,
    EnvironmentBrowserInputResolver,
    GitHubActionsPreviewGateway,
    PlaywrightPreviewBrowserGateway,
    PreviewBrowserGateway,
    PreviewDeploymentGateway,
)
from runtime.customer_acceptance.service import CustomerAcceptanceService
from runtime.customer_acceptance.web import CustomerAcceptanceApplication

__all__ = [
    "AcceptanceJourneySummary",
    "ControlledCustomerAcceptanceAdapter",
    "CustomerAcceptanceAdapter",
    "CustomerAcceptanceApplication",
    "CustomerAcceptanceConfiguration",
    "CustomerAcceptanceConflict",
    "CustomerAcceptanceCorrupt",
    "CustomerAcceptanceError",
    "CustomerAcceptanceNotConfigured",
    "CustomerAcceptanceNotFound",
    "CustomerAcceptanceOutcome",
    "CustomerAcceptancePolicyError",
    "CustomerAcceptanceReconciliationRequired",
    "CustomerAcceptanceRecord",
    "CustomerAcceptanceService",
    "CustomerAcceptanceStatus",
    "EnvironmentBrowserInputResolver",
    "FileCustomerAcceptanceStore",
    "GitHubActionsPreviewGateway",
    "PlaywrightPreviewBrowserGateway",
    "PreviewBrowserGateway",
    "PreviewDeploymentGateway",
    "PreviewDeploymentReceipt",
    "WorkflowJobReceipt",
    "acceptance_id_for",
    "browser_plan_id_for",
    "canonical_origin",
    "load_acceptance_plan",
]
