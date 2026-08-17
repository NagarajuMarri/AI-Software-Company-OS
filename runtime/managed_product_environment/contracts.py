"""Provider-neutral ports for the Day 6 environment lifecycle."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runtime.managed_product_environment.models import (
    EnvironmentObservation,
    PreparedEnvironment,
)
from runtime.managed_product_runtime.models import (
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    OneShotCommand,
)


@runtime_checkable
class RuntimeSecretResolver(Protocol):
    """Resolve one operator-approved opaque reference at the execution boundary."""

    def resolve(self, reference: str) -> str: ...


@runtime_checkable
class ManagedProductEnvironmentProvider(Protocol):
    """Perform bounded workspace, process, readiness, and cleanup operations."""

    def prepare(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        run_id: str,
    ) -> tuple[PreparedEnvironment, EnvironmentObservation]: ...

    def run_migration(
        self,
        workspace: PreparedEnvironment,
        command: OneShotCommand,
        environment: dict[str, str],
        redactions: tuple[str, ...],
    ) -> EnvironmentObservation: ...

    def start_service(
        self,
        workspace: PreparedEnvironment,
        service: ManagedRuntimeService,
        environment: dict[str, str],
    ) -> tuple[object, EnvironmentObservation]: ...

    def await_readiness(
        self,
        handle: object,
        service: ManagedRuntimeService,
    ) -> EnvironmentObservation: ...

    def stop_service(
        self,
        workspace: PreparedEnvironment,
        handle: object,
        service: ManagedRuntimeService,
        environment: dict[str, str],
        redactions: tuple[str, ...],
    ) -> EnvironmentObservation: ...

    def cleanup(self, workspace: PreparedEnvironment) -> EnvironmentObservation: ...
