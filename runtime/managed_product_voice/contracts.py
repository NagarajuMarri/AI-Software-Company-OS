"""Ports for immutable voice verification plans."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runtime.managed_product_voice.models import VoiceVerificationPlan


@runtime_checkable
class VoiceVerificationPlanStore(Protocol):
    def save(self, plan: VoiceVerificationPlan) -> VoiceVerificationPlan: ...

    def load(self, product_id: str, run_id: str, verification_id: str) -> VoiceVerificationPlan: ...
