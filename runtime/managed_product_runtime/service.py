"""Policy gate and acceptance binding for managed-product runtime declarations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
import re
from urllib.parse import urlparse

from runtime.events.types import EventType
from runtime.managed_product_runtime.errors import (
    RuntimeConfigurationNotFoundError,
    RuntimeConfigurationPolicyError,
)
from runtime.managed_product_runtime.models import (
    ManagedProductRuntimeConfiguration,
    endpoint_origin,
    repository_key,
)
from runtime.managed_product_runtime.persistence import RuntimeConfigurationStore
from runtime.projects.models import ProjectLifecycle
from runtime.projects.registry import ProjectRegistry
from runtime.runtime_acceptance.models import (
    AcceptanceStage,
    RuntimeAcceptanceProfile,
    RuntimeAcceptanceRun,
    acceptance_profile_digest,
)


_POLICY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")


class ManagedProductRuntimeConfigurationService:
    """Registers declarations only after intersecting them with operator policy."""

    def __init__(
        self,
        project_registry: ProjectRegistry,
        store: RuntimeConfigurationStore,
        profiles: Mapping[str, RuntimeAcceptanceProfile]
        | Iterable[RuntimeAcceptanceProfile],
        *,
        allowed_executables: frozenset[str],
        allowed_repository_hosts: frozenset[str],
        allowed_origins: frozenset[str],
        allowed_environment_names: frozenset[str],
        allowed_secret_references: frozenset[str] = frozenset(),
        allowed_secret_reference_prefixes: tuple[str, ...] = (),
        event_publisher=None,
    ) -> None:
        if not isinstance(project_registry, ProjectRegistry):
            raise TypeError("project_registry must implement ProjectRegistry")
        if not isinstance(store, RuntimeConfigurationStore):
            raise TypeError("store must implement RuntimeConfigurationStore")
        self.project_registry = project_registry
        self.store = store
        self.event_publisher = event_publisher
        self._profiles = _profiles(profiles)
        self._allowed_executables = _policy_names(
            allowed_executables, "allowed executables"
        )
        self._allowed_repository_hosts = frozenset(
            _host(value) for value in allowed_repository_hosts
        )
        self._allowed_origins = frozenset(endpoint_origin(value) for value in allowed_origins)
        self._allowed_environment_names = _environment_names(allowed_environment_names)
        self._allowed_secret_references = _policy_names(
            allowed_secret_references,
            "allowed secret references",
            allow_empty=True,
        )
        self._allowed_secret_reference_prefixes = _prefixes(
            allowed_secret_reference_prefixes
        )
        if not self._allowed_executables:
            raise ValueError("Operator policy requires allowed executables")
        if not self._allowed_repository_hosts:
            raise ValueError("Operator policy requires repository hosts")
        if not self._allowed_origins:
            raise ValueError("Operator policy requires network origins")

    def register(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        *,
        expected_revision: int | None = None,
    ) -> ManagedProductRuntimeConfiguration:
        if not isinstance(configuration, ManagedProductRuntimeConfiguration):
            raise TypeError("configuration must be a ManagedProductRuntimeConfiguration")
        self._authorize(configuration)
        try:
            previous = self.store.get(
                configuration.project_id, configuration.configuration_id
            )
        except RuntimeConfigurationNotFoundError:
            previous = None
        saved = self.store.save(configuration, expected_revision=expected_revision)
        if previous == saved:
            return saved
        self._event(
            EventType.MANAGED_PRODUCT_RUNTIME_CONFIGURATION_CREATED
            if previous is None
            else EventType.MANAGED_PRODUCT_RUNTIME_CONFIGURATION_REVISED,
            saved,
        )
        return saved

    def revise(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        *,
        expected_revision: int,
    ) -> ManagedProductRuntimeConfiguration:
        return self.register(configuration, expected_revision=expected_revision)

    def get(
        self, project_id: str, configuration_id: str
    ) -> ManagedProductRuntimeConfiguration:
        return self.store.get(project_id, configuration_id)

    def get_revision(
        self, project_id: str, configuration_id: str, revision: int
    ) -> ManagedProductRuntimeConfiguration:
        return self.store.get_revision(project_id, configuration_id, revision)

    def list_for_project(
        self, project_id: str
    ) -> tuple[ManagedProductRuntimeConfiguration, ...]:
        return self.store.list_for_project(project_id)

    def bind_acceptance_run(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        run: RuntimeAcceptanceRun,
    ) -> RuntimeAcceptanceRun:
        """Bind a PLANNED run to one persisted config revision and profile."""

        if not isinstance(configuration, ManagedProductRuntimeConfiguration):
            raise TypeError("configuration must be a ManagedProductRuntimeConfiguration")
        if not isinstance(run, RuntimeAcceptanceRun):
            raise TypeError("run must be a RuntimeAcceptanceRun")
        persisted = self.store.get_revision(
            configuration.project_id,
            configuration.configuration_id,
            configuration.revision,
        )
        if persisted.digest != configuration.digest:
            raise RuntimeConfigurationPolicyError(
                "Acceptance binding requires the exact persisted configuration revision"
            )
        self._authorize(persisted)
        if run.stage is not AcceptanceStage.PLANNED:
            raise RuntimeConfigurationPolicyError(
                "Only a PLANNED acceptance run can be configuration-bound"
            )
        if run.product_id != configuration.project_id:
            raise RuntimeConfigurationPolicyError(
                "Acceptance run product does not match runtime configuration"
            )
        if run.commit_sha != configuration.commit_sha:
            raise RuntimeConfigurationPolicyError(
                "Acceptance run commit does not match runtime configuration"
            )
        profile = self._profile(configuration)
        run_profile_digest = acceptance_profile_digest(
            profile.profile_id,
            profile.version,
            run.capabilities,
            run.journeys,
        )
        if run_profile_digest != profile.digest:
            raise RuntimeConfigurationPolicyError(
                "Acceptance run contract does not match the configured profile"
            )
        existing_binding = (
            run.runtime_configuration_id,
            run.runtime_configuration_revision,
            run.runtime_configuration_digest,
            run.acceptance_profile_id,
            run.acceptance_profile_version,
            run.acceptance_profile_digest,
        )
        target_binding = (
            configuration.configuration_id,
            configuration.revision,
            configuration.digest,
            profile.profile_id,
            profile.version,
            profile.digest,
        )
        if any(existing_binding):
            if existing_binding == target_binding:
                return run
            raise RuntimeConfigurationPolicyError(
                "Acceptance run configuration binding is immutable"
            )
        return replace(
            run,
            runtime_configuration_id=configuration.configuration_id,
            runtime_configuration_revision=configuration.revision,
            runtime_configuration_digest=configuration.digest,
            acceptance_profile_id=profile.profile_id,
            acceptance_profile_version=profile.version,
            acceptance_profile_digest=profile.digest,
        )

    def bind_acceptance(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        run: RuntimeAcceptanceRun,
    ) -> RuntimeAcceptanceRun:
        """Compatibility spelling for callers composing the Day 5 boundary."""

        return self.bind_acceptance_run(configuration, run)

    def _authorize(self, configuration: ManagedProductRuntimeConfiguration) -> None:
        project = self.project_registry.get(configuration.project_id)
        if project.lifecycle in {ProjectLifecycle.PAUSED, ProjectLifecycle.ARCHIVED}:
            raise RuntimeConfigurationPolicyError(
                "Paused or archived projects cannot register runtime configuration"
            )
        if repository_key(project.repository_url) != repository_key(
            configuration.repository_url
        ):
            raise RuntimeConfigurationPolicyError(
                "Runtime configuration repository does not match the project registry"
            )
        host = (urlparse(configuration.repository_url).hostname or "").casefold()
        if host not in self._allowed_repository_hosts:
            raise RuntimeConfigurationPolicyError(
                "Runtime configuration repository host is not operator-approved"
            )
        executables = {
            item.command.executable for item in configuration.migration_commands
        }
        executables.update(item.start_command.executable for item in configuration.services)
        executables.update(
            item.stop_command.command.executable for item in configuration.services
        )
        if not executables <= self._allowed_executables:
            raise RuntimeConfigurationPolicyError(
                "Runtime configuration executable is not operator-approved"
            )
        if not set(configuration.allowed_origins) <= self._allowed_origins:
            raise RuntimeConfigurationPolicyError(
                "Runtime configuration origin is not operator-approved"
            )
        if not set(configuration.environment_allow_list) <= self._allowed_environment_names:
            raise RuntimeConfigurationPolicyError(
                "Runtime environment name is not operator-approved"
            )
        for secret in configuration.secret_references:
            if secret.reference not in self._allowed_secret_references and not any(
                secret.reference.startswith(prefix)
                for prefix in self._allowed_secret_reference_prefixes
            ):
                raise RuntimeConfigurationPolicyError(
                    "Runtime secret reference is not operator-approved"
                )
        self._profile(configuration)

    def _profile(
        self, configuration: ManagedProductRuntimeConfiguration
    ) -> RuntimeAcceptanceProfile:
        profile = self._profiles.get(
            (
                configuration.acceptance_profile_id,
                configuration.acceptance_profile_version,
            )
        )
        if profile is None:
            raise RuntimeConfigurationPolicyError(
                "Runtime acceptance profile ID/version is not registered"
            )
        if configuration.acceptance_profile_digest != profile.digest:
            raise RuntimeConfigurationPolicyError(
                "Runtime acceptance profile digest is stale or untrusted"
            )
        return profile

    def _event(
        self,
        event_type: EventType,
        configuration: ManagedProductRuntimeConfiguration,
    ) -> None:
        if self.event_publisher is None:
            return
        self.event_publisher.publish(
            event_type,
            "MANAGED_PRODUCT_RUNTIME_CONFIGURATION",
            configuration.configuration_id,
            {
                "project_id": configuration.project_id,
                "revision": configuration.revision,
                "configuration_digest": configuration.digest,
                "commit_sha": configuration.commit_sha,
                "acceptance_profile_id": configuration.acceptance_profile_id,
                "acceptance_profile_version": configuration.acceptance_profile_version,
                "acceptance_profile_digest": configuration.acceptance_profile_digest,
            },
        )


def _profiles(
    values: Mapping[str, RuntimeAcceptanceProfile] | Iterable[RuntimeAcceptanceProfile],
) -> dict[tuple[str, str], RuntimeAcceptanceProfile]:
    candidates = values.values() if isinstance(values, Mapping) else values
    result: dict[tuple[str, str], RuntimeAcceptanceProfile] = {}
    for value in candidates:
        if not isinstance(value, RuntimeAcceptanceProfile):
            raise TypeError("profiles must contain RuntimeAcceptanceProfile values")
        key = (value.profile_id, value.version)
        if key in result:
            raise ValueError("Acceptance profile ID/version must be unique")
        result[key] = value
    if not result:
        raise ValueError("At least one acceptance profile is required")
    return result


def _policy_names(
    values: frozenset[str], label: str, *, allow_empty: bool = False
) -> frozenset[str]:
    if not isinstance(values, frozenset) or (not values and not allow_empty):
        raise ValueError(f"Operator {label} must be a frozenset")
    if any(not isinstance(value, str) or not _POLICY_NAME.fullmatch(value) for value in values):
        raise ValueError(f"Operator {label} contains an unsafe value")
    return values


def _environment_names(values: frozenset[str]) -> frozenset[str]:
    if not isinstance(values, frozenset):
        raise ValueError("Operator environment names must be a frozenset")
    if any(not isinstance(value, str) or not _ENVIRONMENT_NAME.fullmatch(value) for value in values):
        raise ValueError("Operator environment names contain an unsafe value")
    return values


def _host(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or ":" in value
        or "/" in value
        or value != value.strip()
    ):
        raise ValueError("Operator repository host is invalid")
    return value.casefold()


def _prefixes(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) != len(set(values)):
        raise ValueError("Operator secret-reference prefixes must be a unique tuple")
    for value in values:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 128
            or not value.endswith((".", "-", "_"))
            or not _POLICY_NAME.fullmatch(value.rstrip(".-_"))
        ):
            raise ValueError("Operator secret-reference prefix is invalid")
    return values
