"""Provider-neutral ports for persisted browser journeys and evidence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runtime.managed_product_browser.models import (
    BrowserExecutionResult,
    BrowserJourneyPlan,
)
from runtime.managed_product_runtime.models import ManagedProductRuntimeConfiguration


@runtime_checkable
class BrowserJourneyPlanStore(Protocol):
    def save(self, plan: BrowserJourneyPlan) -> BrowserJourneyPlan: ...

    def load(self, product_id: str, run_id: str, plan_id: str) -> BrowserJourneyPlan: ...


@runtime_checkable
class BrowserExecutionStore(Protocol):
    def save(self, result: BrowserExecutionResult) -> BrowserExecutionResult: ...

    def load(self, product_id: str, run_id: str, plan_id: str) -> BrowserExecutionResult: ...

    def find(
        self, product_id: str, run_id: str, plan_id: str
    ) -> BrowserExecutionResult | None: ...


@runtime_checkable
class BrowserInputResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


@runtime_checkable
class BrowserArtifactStore(Protocol):
    def write_json(self, product_id: str, run_id: str, payload: object) -> tuple[str, str]: ...

    def write_bytes(
        self,
        product_id: str,
        run_id: str,
        content: bytes,
        extension: str,
    ) -> tuple[str, str]: ...

    def verify(self, artifact_uri: str, expected_digest: str) -> None: ...

    def read_json(self, artifact_uri: str, expected_digest: str) -> object: ...


@runtime_checkable
class ManagedProductBrowserProvider(Protocol):
    provider_id: str

    def execute(
        self,
        plan: BrowserJourneyPlan,
        configuration: ManagedProductRuntimeConfiguration,
        inputs: dict[str, str],
        redactions: tuple[str, ...],
        artifact_store: BrowserArtifactStore,
    ) -> BrowserExecutionResult: ...
