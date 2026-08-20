"""Ports for PWA verification and aggregate-submission authority."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runtime.managed_product_pwa.models import (
    AcceptanceSubmissionPlan,
    AcceptanceSubmissionReceipt,
    PwaVerificationPlan,
)


@runtime_checkable
class PwaVerificationPlanStore(Protocol):
    def save(self, plan: PwaVerificationPlan) -> PwaVerificationPlan: ...

    def load(self, product_id: str, run_id: str, plan_id: str) -> PwaVerificationPlan: ...


@runtime_checkable
class AcceptanceSubmissionStore(Protocol):
    def save_plan(self, plan: AcceptanceSubmissionPlan) -> AcceptanceSubmissionPlan: ...

    def load_plan(
        self, product_id: str, run_id: str, submission_id: str
    ) -> AcceptanceSubmissionPlan: ...

    def save_receipt(
        self, receipt: AcceptanceSubmissionReceipt
    ) -> AcceptanceSubmissionReceipt: ...

    def find_receipt(
        self, product_id: str, run_id: str, submission_id: str
    ) -> AcceptanceSubmissionReceipt | None: ...
