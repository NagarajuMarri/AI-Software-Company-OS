"""Orchestration and current-policy enforcement for managed environments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Generic, TypeVar
from urllib.parse import urlparse

from runtime.managed_product_environment.contracts import (
    ManagedProductEnvironmentProvider,
    RuntimeSecretResolver,
)
from runtime.managed_product_environment.errors import (
    EnvironmentAuthorityError,
    EnvironmentExecutionError,
    EnvironmentSecretResolutionError,
)
from runtime.managed_product_environment.models import (
    EnvironmentExecutionPolicy,
    EnvironmentExecutionRequest,
    EnvironmentStage,
    ManagedProductEnvironmentResult,
)
from runtime.managed_product_runtime.models import (
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    endpoint_origin,
)
from runtime.managed_product_runtime.persistence import RuntimeConfigurationStore


_T = TypeVar("_T")


@dataclass(frozen=True)
class ReadyEnvironmentExecution(Generic[_T]):
    """Environment lifecycle result plus one probe run while services were ready."""

    environment_result: ManagedProductEnvironmentResult
    probe_result: _T | None


class ManagedProductEnvironmentService:
    """Verify one persisted configuration through startup, readiness, and shutdown."""

    def __init__(
        self,
        configuration_store: RuntimeConfigurationStore,
        provider: ManagedProductEnvironmentProvider,
        secret_resolver: RuntimeSecretResolver,
        policy: EnvironmentExecutionPolicy,
    ) -> None:
        self.configuration_store = configuration_store
        self.provider = provider
        self.secret_resolver = secret_resolver
        self.policy = policy

    def verify(
        self, request: EnvironmentExecutionRequest
    ) -> ManagedProductEnvironmentResult:
        return self.verify_with_ready_probe(request).environment_result

    def verify_with_ready_probe(
        self,
        request: EnvironmentExecutionRequest,
        ready_probe: Callable[[ManagedProductRuntimeConfiguration], _T] | None = None,
    ) -> ReadyEnvironmentExecution[_T]:
        """Run an optional bounded probe after readiness and before shutdown.

        Expected probe failures should be returned as a typed result. Unexpected
        exceptions are re-raised only after service shutdown and workspace cleanup.
        """

        configuration = self.configuration_store.get_revision(
            request.project_id,
            request.configuration_id,
            request.configuration_revision,
        )
        if (
            configuration.configuration_id != request.configuration_id
            or configuration.project_id != request.project_id
            or configuration.revision != request.configuration_revision
            or configuration.digest != request.configuration_digest
        ):
            raise EnvironmentAuthorityError(
                "Environment request does not match the exact persisted configuration"
            )
        self._authorize(configuration)
        started_at = _now()
        observations = []
        workspace = None
        service_handles: list[tuple[object, ManagedRuntimeService]] = []
        failure_code: str | None = None
        reconciliation_required = False
        environment: dict[str, str] = {
            item.name: item.value for item in configuration.environment
        }
        redactions: list[str] = []
        probe_result: _T | None = None

        try:
            for secret in configuration.secret_references:
                value = self._resolve_secret(secret.reference)
                environment[secret.target_environment] = value
                redactions.append(value)
            workspace, observation = self.provider.prepare(configuration, request.run_id)
            observations.append(observation)
            for migration in configuration.migration_commands:
                observations.append(
                    self.provider.run_migration(
                        workspace,
                        migration,
                        environment,
                        tuple(redactions),
                    )
                )
            for declared_service in configuration.services:
                handle, observation = self.provider.start_service(
                    workspace, declared_service, environment
                )
                service_handles.append((handle, declared_service))
                observations.append(observation)
            for handle, declared_service in service_handles:
                observations.append(
                    self.provider.await_readiness(handle, declared_service)
                )
            if ready_probe is not None:
                probe_result = ready_probe(configuration)
        except EnvironmentExecutionError as error:
            failure_code = error.code
            reconciliation_required = error.reconciliation_required
            if error.observation is not None:
                observations.append(error.observation)
        finally:
            for handle, declared_service in reversed(service_handles):
                if workspace is None:
                    raise AssertionError("Started service requires a prepared workspace")
                try:
                    observations.append(
                        self.provider.stop_service(
                            workspace,
                            handle,
                            declared_service,
                            environment,
                            tuple(redactions),
                        )
                    )
                except EnvironmentExecutionError as error:
                    failure_code = failure_code or error.code
                    reconciliation_required = (
                        reconciliation_required or error.reconciliation_required
                    )
                    if error.observation is not None:
                        observations.append(error.observation)
            if workspace is not None and not reconciliation_required:
                try:
                    observations.append(self.provider.cleanup(workspace))
                except EnvironmentExecutionError as error:
                    failure_code = failure_code or error.code
                    reconciliation_required = True
                    if error.observation is not None:
                        observations.append(error.observation)
            environment.clear()
            redactions.clear()

        stage = EnvironmentStage.STOPPED
        if reconciliation_required:
            stage = EnvironmentStage.RECONCILIATION_REQUIRED
        elif failure_code is not None:
            stage = EnvironmentStage.FAILED
        return ReadyEnvironmentExecution(
            ManagedProductEnvironmentResult(
                request.run_id,
                request.project_id,
                request.configuration_id,
                request.configuration_revision,
                request.configuration_digest,
                configuration.commit_sha,
                stage,
                tuple(observations),
                started_at,
                _now(),
                failure_code,
                reconciliation_required,
            ),
            probe_result,
        )

    def _authorize(self, configuration) -> None:  # noqa: ANN001
        host = (urlparse(configuration.repository_url).hostname or "").casefold()
        if host not in {item.casefold() for item in self.policy.allowed_repository_hosts}:
            raise EnvironmentAuthorityError(
                "Runtime repository host is not approved for environment execution"
            )
        executables = {
            item.command.executable for item in configuration.migration_commands
        }
        executables.update(
            item.start_command.executable for item in configuration.services
        )
        executables.update(
            item.stop_command.command.executable for item in configuration.services
        )
        if not executables <= self.policy.allowed_executables:
            raise EnvironmentAuthorityError(
                "Runtime executable is not approved for environment execution"
            )
        origins = {endpoint_origin(value) for value in configuration.allowed_origins}
        if not origins <= self.policy.allowed_origins:
            raise EnvironmentAuthorityError(
                "Runtime origin is not approved for environment execution"
            )
        if not set(configuration.environment_allow_list) <= (
            self.policy.allowed_environment_names
        ):
            raise EnvironmentAuthorityError(
                "Runtime environment name is not approved for execution"
            )
        for secret in configuration.secret_references:
            if secret.reference not in self.policy.allowed_secret_references and not any(
                secret.reference.startswith(prefix)
                for prefix in self.policy.allowed_secret_reference_prefixes
            ):
                raise EnvironmentAuthorityError(
                    "Runtime secret reference is not approved for execution"
                )

    def _resolve_secret(self, reference: str) -> str:
        failure = False
        value: str | None = None
        try:
            value = self.secret_resolver.resolve(reference)
        except Exception:  # provider details must not cross the redaction boundary
            failure = True
        if (
            failure
            or not isinstance(value, str)
            or not value
            or len(value) > 8_192
            or "\0" in value
        ):
            raise EnvironmentSecretResolutionError(
                "SECRET_RESOLUTION_FAILED",
                "An approved runtime secret reference could not be resolved",
            )
        return value


def _now() -> datetime:
    return datetime.now(timezone.utc)
