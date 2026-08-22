"""Bind one exact draft delivery to isolated preview and browser evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock

from runtime.customer_acceptance.errors import (
    CustomerAcceptanceConflict,
    CustomerAcceptanceNotConfigured,
    CustomerAcceptancePolicyError,
    CustomerAcceptanceReconciliationRequired,
)
from runtime.customer_acceptance.models import (
    AcceptanceJourneySummary,
    CustomerAcceptanceConfiguration,
    CustomerAcceptanceRecord,
    CustomerAcceptanceStatus,
    acceptance_id_for,
    browser_plan_id_for,
)
from runtime.customer_acceptance.persistence import FileCustomerAcceptanceStore
from runtime.customer_acceptance.provider import CustomerAcceptanceAdapter
from runtime.customer_delivery import (
    CustomerDeliveryReview,
    CustomerDeliveryService,
    CustomerDeliveryStatus,
)
from runtime.customer_evidence import CustomerPreviewEvidenceService
from runtime.managed_product_browser import BrowserJourneyPlan, FileBrowserJourneyPlanStore


class CustomerAcceptanceService:
    """Prepare, approve, and run one exact Completion Module 5 acceptance."""

    def __init__(
        self,
        store: FileCustomerAcceptanceStore,
        plan_store: FileBrowserJourneyPlanStore,
        deliveries: CustomerDeliveryService,
        evidence: CustomerPreviewEvidenceService,
        configuration: CustomerAcceptanceConfiguration | None,
        adapter: CustomerAcceptanceAdapter | None,
        clock=None,  # noqa: ANN001
    ) -> None:
        self._store = store
        self._plans = plan_store
        self._deliveries = deliveries
        self._evidence = evidence
        self._configuration = configuration
        self._adapter = adapter
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    @property
    def configured(self) -> bool:
        return self._configuration is not None

    @property
    def live_enabled(self) -> bool:
        return bool(
            self._configuration
            and self._configuration.live_enabled
            and self._adapter is not None
        )

    def find(self, customer_id: str, request_id: str) -> CustomerAcceptanceRecord | None:
        self._require_delivery(customer_id, request_id)
        return self._store.find(customer_id, request_id)

    def prepare(self, customer_id: str, request_id: str) -> CustomerAcceptanceRecord:
        configuration = self._require_configuration()
        with self._lock:
            delivery = self._require_delivery(customer_id, request_id)
            if delivery.commit_sha is None or delivery.tree_sha is None:
                raise CustomerAcceptancePolicyError("Draft delivery commit evidence is incomplete")
            if len(delivery.commit_sha) != 40 or len(delivery.tree_sha) != 40:
                raise CustomerAcceptancePolicyError("Preview requires exact GitHub SHA-1 identities")
            now = self._clock()
            acceptance_id = acceptance_id_for(request_id)
            plan = BrowserJourneyPlan(
                plan_id=browser_plan_id_for(request_id),
                run_id=acceptance_id,
                product_id=delivery.product_id,
                configuration_id=configuration.preview_environment_id,
                configuration_revision=1,
                configuration_digest=configuration.digest,
                commit_sha=delivery.commit_sha,
                acceptance_profile_id=configuration.acceptance_profile_id,
                acceptance_profile_version=configuration.acceptance_profile_version,
                acceptance_profile_digest=configuration.digest,
                journeys=configuration.journeys,
                inputs=configuration.inputs,
                created_by=customer_id,
                created_at=now,
            )
            self._plans.save(plan)
            record = CustomerAcceptanceRecord(
                acceptance_id=acceptance_id,
                customer_id=customer_id,
                request_id=request_id,
                product_id=delivery.product_id,
                delivery_id=delivery.delivery_id,
                delivery_digest=delivery.digest,
                delivery_review_digest=delivery.review_digest,
                repository_full_name=delivery.repository_full_name,
                base_branch=delivery.base_branch,
                head_branch=delivery.workspace_branch,
                commit_sha=delivery.commit_sha,
                tree_sha=delivery.tree_sha,
                pull_request_number=delivery.pull_request_number or 0,
                pull_request_url=delivery.pull_request_url or "",
                configuration_digest=configuration.digest,
                preview_environment_id=configuration.preview_environment_id,
                preview_url=configuration.preview_url,
                workflow_file=configuration.workflow_file,
                automated_test_job=configuration.automated_test_job,
                security_job=configuration.security_job,
                browser_plan_id=plan.plan_id,
                browser_plan_digest=plan.digest,
                journeys=tuple(
                    AcceptanceJourneySummary(
                        journey_id=value.journey_id,
                        capability_id=value.capability_id,
                        title=value.title,
                        start_path=value.start_path,
                        step_count=len(value.steps),
                    )
                    for value in plan.journeys
                ),
                created_at=now,
                updated_at=now,
            )
            return self._store.create(record)

    def approve(
        self,
        customer_id: str,
        request_id: str,
        *,
        expected_approval_digest: str,
        confirm_preview_scope: bool,
    ) -> CustomerAcceptanceRecord:
        if not confirm_preview_scope:
            raise CustomerAcceptancePolicyError("Exact preview acceptance confirmation is required")
        with self._lock:
            delivery = self._require_delivery(customer_id, request_id)
            record = self._store.load(customer_id, request_id)
            self._require_binding(record, delivery)
            if record.status is CustomerAcceptanceStatus.APPROVED:
                if record.approval_digest == expected_approval_digest:
                    return record
                raise CustomerAcceptanceConflict("Preview acceptance approval is stale")
            if record.status is not CustomerAcceptanceStatus.AWAITING_APPROVAL:
                raise CustomerAcceptanceConflict("Preview acceptance cannot be approved now")
            if record.approval_digest != expected_approval_digest:
                raise CustomerAcceptanceConflict("Preview acceptance approval is stale")
            now = self._clock()
            approved = replace(
                record,
                status=CustomerAcceptanceStatus.APPROVED,
                approved_at=now,
                approved_by=customer_id,
                updated_at=now,
            )
            return self._store.replace(approved, expected_digest=record.digest)

    def execute(
        self,
        customer_id: str,
        request_id: str,
        *,
        expected_approval_digest: str,
        confirm_preview_deployment: bool,
        confirm_browser_execution: bool,
    ) -> CustomerAcceptanceRecord:
        self._require_configuration()
        if not self.live_enabled:
            raise CustomerAcceptanceNotConfigured(
                "Preview acceptance requires operator enablement and both effect confirmations"
            )
        if not confirm_preview_deployment or not confirm_browser_execution:
            raise CustomerAcceptancePolicyError(
                "Separate preview-deployment and browser-execution confirmations are required"
            )
        assert self._adapter is not None
        with self._lock:
            delivery = self._require_delivery(customer_id, request_id)
            record = self._store.load(customer_id, request_id)
            self._require_binding(record, delivery)
            if record.status is CustomerAcceptanceStatus.EVIDENCE_READY:
                if record.approval_digest == expected_approval_digest:
                    return record
                raise CustomerAcceptanceConflict("Preview acceptance request is stale")
            if record.status is not CustomerAcceptanceStatus.APPROVED:
                raise CustomerAcceptanceConflict("Exact preview acceptance is not approved")
            if record.approval_digest != expected_approval_digest:
                raise CustomerAcceptanceConflict("Preview acceptance request is stale")
            plan = self._load_plan(record)
            self._adapter.preflight(record, plan)
            in_progress = replace(
                record,
                status=CustomerAcceptanceStatus.EXECUTION_IN_PROGRESS,
                updated_at=self._clock(),
            )
            in_progress = self._store.replace(in_progress, expected_digest=record.digest)
            try:
                outcome = self._adapter.execute(in_progress, plan)
                package = self._evidence.publish(
                    customer_id=customer_id,
                    request_id=request_id,
                    preview_label="Governed isolated product preview",
                    preview_url=in_progress.preview_url + "/",
                    commit_sha=in_progress.commit_sha,
                    evidence=outcome.evidence,
                )
                ready = replace(
                    in_progress,
                    status=CustomerAcceptanceStatus.EVIDENCE_READY,
                    workflow_run_id=outcome.deployment.workflow_run_id,
                    workflow_run_url=outcome.deployment.workflow_run_url,
                    deployment_revision=outcome.deployment.deployment_revision,
                    deployment_receipt_digest=outcome.deployment.digest,
                    browser_execution_digest=outcome.browser.digest,
                    evidence_package_id=package.package_id,
                    evidence_package_digest=package.digest,
                    updated_at=self._clock(),
                )
                return self._store.replace(ready, expected_digest=in_progress.digest)
            except Exception as error:
                current = self._store.load(customer_id, request_id)
                failed = replace(
                    current,
                    status=CustomerAcceptanceStatus.RECONCILIATION_REQUIRED,
                    failure_classification=type(error).__name__,
                    updated_at=self._clock(),
                )
                self._store.replace(failed, expected_digest=current.digest)
                raise CustomerAcceptanceReconciliationRequired(
                    "A preview or browser effect requires manual reconciliation"
                ) from error

    def _require_configuration(self) -> CustomerAcceptanceConfiguration:
        if self._configuration is None:
            raise CustomerAcceptanceNotConfigured(
                "The operator has not bound an isolated preview and browser plan"
            )
        return self._configuration

    def _require_delivery(
        self,
        customer_id: str,
        request_id: str,
    ) -> CustomerDeliveryReview:
        delivery = self._deliveries.find(customer_id, request_id)
        if delivery is None or delivery.status is not CustomerDeliveryStatus.DRAFT_PR_CREATED:
            raise CustomerAcceptanceConflict("Module 4 has not produced an exact draft delivery")
        return delivery

    @staticmethod
    def _require_binding(
        record: CustomerAcceptanceRecord,
        delivery: CustomerDeliveryReview,
    ) -> None:
        if not (
            record.customer_id == delivery.customer_id
            and record.request_id == delivery.request_id
            and record.product_id == delivery.product_id
            and record.delivery_id == delivery.delivery_id
            and record.delivery_digest == delivery.digest
            and record.delivery_review_digest == delivery.review_digest
            and record.repository_full_name == delivery.repository_full_name
            and record.base_branch == delivery.base_branch
            and record.head_branch == delivery.workspace_branch
            and record.commit_sha == delivery.commit_sha
            and record.tree_sha == delivery.tree_sha
            and record.pull_request_number == delivery.pull_request_number
            and record.pull_request_url == delivery.pull_request_url
        ):
            raise CustomerAcceptancePolicyError("Acceptance differs from Module 4 delivery authority")

    def _load_plan(self, record: CustomerAcceptanceRecord) -> BrowserJourneyPlan:
        plan = self._plans.load(record.product_id, record.acceptance_id, record.browser_plan_id)
        if not (
            plan.digest == record.browser_plan_digest
            and plan.run_id == record.acceptance_id
            and plan.product_id == record.product_id
            and plan.commit_sha == record.commit_sha
        ):
            raise CustomerAcceptancePolicyError("Persisted browser plan changed")
        return plan
