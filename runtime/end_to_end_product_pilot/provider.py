"""Closed provider boundary for Day 36 product-pilot evidence composition."""

from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.end_to_end_product_pilot.errors import ProductPilotPolicyError
from runtime.end_to_end_product_pilot.models import (
    EndToEndProductPilotAuthority,
    EndToEndProductPilotObservation,
    EndToEndProductPilotWorkOrder,
    ProductPilotSourceSnapshot,
)


class EndToEndProductPilotProvider(ABC):
    """Provider-neutral interface that composes evidence from verified sources only."""

    @abstractmethod
    def execute(
        self,
        work_order: EndToEndProductPilotWorkOrder,
        authority: EndToEndProductPilotAuthority,
        snapshot: ProductPilotSourceSnapshot,
    ) -> EndToEndProductPilotObservation:
        """Return one bounded observation without mutating any source system."""


class ControlledEndToEndProductPilotProvider(EndToEndProductPilotProvider):
    """Single-invocation wrapper that rejects stale or mismatched provider output."""

    def __init__(self, provider: EndToEndProductPilotProvider) -> None:
        if not isinstance(provider, EndToEndProductPilotProvider):
            raise TypeError("Product-pilot provider is invalid")
        self._provider = provider
        self.execution_count = 0

    def execute(
        self,
        work_order: EndToEndProductPilotWorkOrder,
        authority: EndToEndProductPilotAuthority,
        snapshot: ProductPilotSourceSnapshot,
    ) -> EndToEndProductPilotObservation:
        if self.execution_count != 0:
            raise ProductPilotPolicyError("Product-pilot provider may execute only once")
        if not (
            work_order.pilot_id == authority.pilot_id == snapshot.pilot_id
            and authority.work_order_digest == work_order.digest
            and snapshot.source_request_digest == work_order.source_request_digest
            and snapshot.roadmap_approval_digest == work_order.roadmap_approval_digest
            and snapshot.runtime_acceptance_artifact_digest
            == work_order.runtime_acceptance_artifact_digest
            and snapshot.product_binding_digest == work_order.product_binding_digest
        ):
            raise ProductPilotPolicyError("Product-pilot provider inputs are not exact")
        self.execution_count += 1
        observation = self._provider.execute(work_order, authority, snapshot)
        if not isinstance(observation, EndToEndProductPilotObservation):
            raise ProductPilotPolicyError("Product-pilot provider returned invalid output")
        if not (
            observation.pilot_id == work_order.pilot_id
            and observation.snapshot_digest == snapshot.digest
            and observation.completed_journey_count == len(snapshot.journey_ids)
            and observation.passed_journey_count == len(snapshot.journey_ids)
        ):
            raise ProductPilotPolicyError("Product-pilot provider output is stale or incomplete")
        return observation
