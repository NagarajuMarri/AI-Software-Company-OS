"""Generate a traceable PRD draft from one exact approved customer baseline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac

from runtime.customer_application.models import CustomerProductRequest
from runtime.customer_prd.errors import CustomerPrdConflict, CustomerPrdCorrupt
from runtime.customer_prd.models import (
    GENERATION_PROFILE,
    CustomerPrdDraft,
    CustomerPrdRequirement,
    ids_for,
)
from runtime.customer_prd.persistence import FileCustomerPrdStore
from runtime.customer_requirements import (
    CustomerRequirementsApproval,
    CustomerRequirementsApprovalService,
    CustomerRequirementsDraft,
    DataSensitivity,
    DeliveryPriority,
)
from runtime.product_requirements import RequirementCategory, RequirementPriority, validate_prd


class CustomerPrdService:
    """Create one deterministic draft without granting downstream authority."""

    def __init__(
        self,
        store: FileCustomerPrdStore,
        approvals: CustomerRequirementsApprovalService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._approvals = approvals
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def context(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[
        CustomerProductRequest,
        CustomerRequirementsDraft | None,
        CustomerRequirementsApproval | None,
        CustomerPrdDraft | None,
    ]:
        request, draft, approval = self._approvals.context(customer_id, request_id)
        value = self._store.find(customer_id, request_id)
        if value is not None:
            if (
                draft is None
                or approval is None
                or value.customer_id != customer_id
                or value.request_id != request_id
                or not hmac.compare_digest(value.source_request_digest, request.digest)
                or not hmac.compare_digest(value.requirements_digest, draft.digest)
                or not hmac.compare_digest(value.approval_digest, approval.digest)
                or validate_prd(value.to_governed_document())
            ):
                raise CustomerPrdCorrupt("Customer PRD does not bind current approved authority")
        return request, draft, approval, value

    def generate(
        self,
        *,
        customer_id: str,
        request_id: str,
        expected_approval_digest: str,
    ) -> CustomerPrdDraft:
        request, draft, approval, existing = self.context(customer_id, request_id)
        if draft is None or approval is None:
            raise CustomerPrdConflict("Approved customer requirements are required")
        if (
            not isinstance(expected_approval_digest, str)
            or not hmac.compare_digest(expected_approval_digest, approval.digest)
        ):
            raise CustomerPrdConflict("Customer PRD generation form is stale")
        if existing is not None:
            return existing
        value = _build(request, draft, approval, self._clock())
        issues = validate_prd(value.to_governed_document())
        if issues:
            raise CustomerPrdConflict("Generated customer PRD failed governed validation")
        return self._store.save(value)


def _build(
    request: CustomerProductRequest,
    draft: CustomerRequirementsDraft,
    approval: CustomerRequirementsApproval,
    generated_at: datetime,
) -> CustomerPrdDraft:
    artifact_id, product_id, prd_id = ids_for(request.request_id)
    priority = (
        RequirementPriority.HIGH
        if draft.delivery_priority is DeliveryPriority.TIME_SENSITIVE
        else RequirementPriority.MEDIUM
    )
    requirements: list[CustomerPrdRequirement] = [
        CustomerPrdRequirement(
            "REQ-JOURNEY-001",
            "Complete the primary user journey",
            draft.primary_user_journey,
            draft.desired_outcomes,
            RequirementCategory.FUNCTIONAL,
            priority,
            "primary_user_journey + desired_outcomes",
        )
    ]
    requirements.extend(
        CustomerPrdRequirement(
            f"REQ-FEATURE-{index:03d}",
            feature,
            f"The product must provide the approved capability: {feature}.",
            draft.success_metrics,
            RequirementCategory.FUNCTIONAL,
            priority,
            f"must_have_features[{index}]",
        )
        for index, feature in enumerate(draft.must_have_features, 1)
    )
    requirements.append(
        CustomerPrdRequirement(
            "REQ-PLATFORM-001",
            "Support approved delivery platforms",
            "The product delivery boundary includes only the approved platforms.",
            tuple(f"{platform.title()} delivery is included." for platform in draft.platforms),
            RequirementCategory.ARCHITECTURE,
            priority,
            "platforms",
        )
    )
    data_label = draft.data_sensitivity.value.replace("_", " ").title()
    data_priority = (
        RequirementPriority.CRITICAL
        if draft.data_sensitivity is DataSensitivity.SENSITIVE_DATA
        else RequirementPriority.HIGH
    )
    requirements.append(
        CustomerPrdRequirement(
            "REQ-DATA-001",
            "Respect the declared data boundary",
            f"The product design must explicitly address the declared data class: {data_label}.",
            (f"The reviewed design identifies controls appropriate to {data_label}.",),
            RequirementCategory.PRIVACY,
            data_priority,
            "data_sensitivity",
        )
    )
    exclusions = _dedupe(request.constraints + draft.non_goals)
    return CustomerPrdDraft(
        artifact_id,
        request.customer_id,
        request.request_id,
        product_id,
        prd_id,
        "0.1",
        GENERATION_PROFILE,
        request.digest,
        draft.digest,
        approval.digest,
        f"{request.product_name} — Product Requirements Document",
        request.product_summary,
        request.target_users,
        draft.primary_user_journey,
        tuple(requirements),
        draft.success_metrics,
        exclusions,
        draft.platforms,
        draft.data_sensitivity,
        draft.delivery_priority,
        generated_at,
    )


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)
