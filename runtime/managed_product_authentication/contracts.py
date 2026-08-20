"""Ports for immutable authentication verification plans."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runtime.managed_product_authentication.models import AuthenticationVerificationPlan


@runtime_checkable
class AuthenticationVerificationPlanStore(Protocol):
    def save(self, plan: AuthenticationVerificationPlan) -> AuthenticationVerificationPlan: ...

    def load(
        self, product_id: str, run_id: str, verification_id: str
    ) -> AuthenticationVerificationPlan: ...
