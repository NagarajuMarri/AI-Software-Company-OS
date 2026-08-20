"""Provider-neutral orchestration for actual managed-product runtime probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from runtime.runtime_acceptance.models import EvidenceArtifact, JourneyResult


@dataclass(frozen=True)
class RuntimeProbeResult:
    evidence: tuple[EvidenceArtifact, ...]
    journey_results: tuple[JourneyResult, ...] = ()


@runtime_checkable
class ManagedProductRuntimeProvider(Protocol):
    """Boundary implemented by a product-specific local or hosted runtime adapter."""

    def verify_commit(self, expected_commit_sha: str) -> RuntimeProbeResult: ...

    def verify_migrations(self) -> RuntimeProbeResult: ...

    def start_services(self) -> RuntimeProbeResult: ...

    def await_readiness(self) -> RuntimeProbeResult: ...

    def run_browser_journeys(self) -> RuntimeProbeResult: ...

    def run_capability_journeys(self) -> RuntimeProbeResult: ...

    def verify_persistence(self) -> RuntimeProbeResult: ...

    def verify_pwa(self) -> RuntimeProbeResult: ...

    def stop_services(self) -> None: ...


class RuntimeAcceptanceOrchestrator:
    """Run probes in customer-runtime order and always stop managed services."""

    def execute(
        self,
        expected_commit_sha: str,
        provider: ManagedProductRuntimeProvider,
    ) -> RuntimeProbeResult:
        evidence: list[EvidenceArtifact] = []
        results: list[JourneyResult] = []
        started = False

        def collect(observation: RuntimeProbeResult) -> None:
            evidence.extend(observation.evidence)
            results.extend(observation.journey_results)

        try:
            collect(provider.verify_commit(expected_commit_sha))
            collect(provider.verify_migrations())
            collect(provider.start_services())
            started = True
            collect(provider.await_readiness())
            collect(provider.run_browser_journeys())
            collect(provider.run_capability_journeys())
            collect(provider.verify_persistence())
            collect(provider.verify_pwa())
        finally:
            if started:
                provider.stop_services()
        return RuntimeProbeResult(tuple(evidence), tuple(results))
