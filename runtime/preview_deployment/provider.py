"""Provider-neutral controlled platform adapter for Day 34 preview deployment."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Protocol, runtime_checkable

from runtime.preview_deployment.errors import (
    PreviewDeploymentPolicyError,
    PreviewDeploymentReconciliationRequired,
)
from runtime.preview_deployment.models import (
    PREVIEW_ENVIRONMENT_CLASS,
    PreviewDeploymentAuthority,
    PreviewDeploymentObservation,
    PreviewDeploymentWorkOrder,
    PreviewHealthReceipt,
)


@runtime_checkable
class PreviewPlatformGateway(Protocol):
    """Closed preview-platform port; it has no production or general command operation."""

    def find(self, environment_id: str) -> PreviewDeploymentObservation | None: ...

    def deploy(
        self,
        *,
        environment_id: str,
        preview_url: str,
        repository_full_name: str,
        feature_branch: str,
        approved_commit: str,
        approved_tree: str,
        configuration_digest: str,
        secret_reference_ids: tuple[str, ...],
        health_check_urls: tuple[str, ...],
    ) -> PreviewDeploymentObservation: ...

    def inspect(self, environment_id: str) -> PreviewDeploymentObservation: ...


class DeterministicPreviewPlatformGateway:
    """In-memory isolated preview gateway used for exact, offline verification."""

    gateway_id = "deterministic-isolated-preview-v1"

    def __init__(self, *, clock=None) -> None:  # noqa: ANN001
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._environments: dict[str, PreviewDeploymentObservation] = {}
        self.find_count = 0
        self.deploy_count = 0
        self.inspect_count = 0

    def find(self, environment_id: str) -> PreviewDeploymentObservation | None:
        self.find_count += 1
        return self._environments.get(environment_id)

    def deploy(
        self,
        *,
        environment_id: str,
        preview_url: str,
        repository_full_name: str,
        feature_branch: str,
        approved_commit: str,
        approved_tree: str,
        configuration_digest: str,
        secret_reference_ids: tuple[str, ...],
        health_check_urls: tuple[str, ...],
    ) -> PreviewDeploymentObservation:
        del repository_full_name, feature_branch
        self.deploy_count += 1
        if environment_id in self._environments:
            raise PreviewDeploymentReconciliationRequired(
                "The isolated preview environment already exists"
            )
        checked_at = self._clock()
        health = tuple(
            PreviewHealthReceipt(
                check_id=f"preview-health-{index}",
                url=url,
                status_code=200,
                response_digest=hashlib.sha256(f"healthy:{url}".encode()).hexdigest(),
                checked_at=checked_at,
            )
            for index, url in enumerate(health_check_urls, start=1)
        )
        observation = PreviewDeploymentObservation(
            provider_id=self.gateway_id,
            environment_id=environment_id,
            environment_class=PREVIEW_ENVIRONMENT_CLASS,
            preview_url=preview_url,
            deployed_commit=approved_commit,
            deployed_tree=approved_tree,
            deployment_revision=(
                "preview-"
                + hashlib.sha256(
                    f"{environment_id}:{approved_commit}:{configuration_digest}".encode()
                ).hexdigest()[:24]
            ),
            configuration_digest=configuration_digest,
            health_receipts=health,
            platform_call_count=3,
            credential_handle_count=len(secret_reference_ids),
        )
        self._environments[environment_id] = observation
        return observation

    def inspect(self, environment_id: str) -> PreviewDeploymentObservation:
        self.inspect_count += 1
        try:
            return self._environments[environment_id]
        except KeyError as error:
            raise PreviewDeploymentPolicyError(
                "The isolated preview environment was not found after deployment"
            ) from error

    def seed(self, observation: PreviewDeploymentObservation) -> None:
        self._environments[observation.environment_id] = observation


class PreviewDeploymentProvider(Protocol):
    def deploy(
        self,
        work_order: PreviewDeploymentWorkOrder,
        authority: PreviewDeploymentAuthority,
    ) -> PreviewDeploymentObservation: ...


class ControlledPreviewDeploymentProvider:
    """Perform one create-only deployment through a closed preview-platform gateway."""

    provider_id = "controlled-preview-deployment-v1"

    def __init__(self, gateway: PreviewPlatformGateway) -> None:
        if not isinstance(gateway, PreviewPlatformGateway):
            raise TypeError("Preview platform gateway is invalid")
        self._gateway = gateway
        self.execution_count = 0

    def deploy(
        self,
        work_order: PreviewDeploymentWorkOrder,
        authority: PreviewDeploymentAuthority,
    ) -> PreviewDeploymentObservation:
        if not isinstance(work_order, PreviewDeploymentWorkOrder) or not isinstance(
            authority, PreviewDeploymentAuthority
        ):
            raise PreviewDeploymentPolicyError("Preview provider input is invalid")
        self.execution_count += 1
        try:
            existing = self._gateway.find(work_order.preview_environment_id)
        except PreviewDeploymentReconciliationRequired:
            raise
        except Exception as error:
            raise PreviewDeploymentPolicyError(
                "Preview environment lookup failed before deployment"
            ) from error
        if existing is not None:
            raise PreviewDeploymentReconciliationRequired(
                "The requested preview environment already exists"
            )
        mutation_started = False
        try:
            mutation_started = True
            created = self._gateway.deploy(
                environment_id=work_order.preview_environment_id,
                preview_url=work_order.preview_url,
                repository_full_name=work_order.repository_full_name,
                feature_branch=work_order.feature_branch,
                approved_commit=work_order.approved_commit,
                approved_tree=work_order.approved_tree,
                configuration_digest=work_order.configuration_digest,
                secret_reference_ids=work_order.secret_reference_ids,
                health_check_urls=work_order.health_check_urls,
            )
            observed = self._gateway.inspect(work_order.preview_environment_id)
        except PreviewDeploymentReconciliationRequired:
            raise
        except Exception as error:
            if mutation_started:
                raise PreviewDeploymentReconciliationRequired(
                    "Preview deployment stopped after a platform effect may have started"
                ) from error
            raise PreviewDeploymentPolicyError(
                "Preview deployment failed before a platform effect"
            ) from error
        if created != observed:
            raise PreviewDeploymentReconciliationRequired(
                "Preview platform inspection does not match its deployment receipt"
            )
        if not (
            observed.environment_id == work_order.preview_environment_id
            and observed.environment_class == PREVIEW_ENVIRONMENT_CLASS
            and observed.preview_url == work_order.preview_url
            and observed.deployed_commit == work_order.approved_commit
            and observed.deployed_tree == work_order.approved_tree
            and observed.configuration_digest == work_order.configuration_digest
            and tuple(item.url for item in observed.health_receipts)
            == work_order.health_check_urls
            and observed.platform_call_count <= authority.max_platform_calls
            and len(observed.health_receipts) <= authority.max_health_checks
            and observed.credential_handle_count <= authority.max_secret_references
        ):
            raise PreviewDeploymentReconciliationRequired(
                "Preview platform receipt crossed the exact authorized deployment boundary"
            )
        return PreviewDeploymentObservation(
            provider_id=self.provider_id,
            environment_id=observed.environment_id,
            environment_class=observed.environment_class,
            preview_url=observed.preview_url,
            deployed_commit=observed.deployed_commit,
            deployed_tree=observed.deployed_tree,
            deployment_revision=observed.deployment_revision,
            configuration_digest=observed.configuration_digest,
            health_receipts=observed.health_receipts,
            platform_call_count=observed.platform_call_count,
            credential_handle_count=observed.credential_handle_count,
            deployment_count=observed.deployment_count,
            migration_count=observed.migration_count,
            monitoring_configuration_count=observed.monitoring_configuration_count,
            rollback_count=observed.rollback_count,
            production_deployment_count=observed.production_deployment_count,
            merge_count=observed.merge_count,
            release_count=observed.release_count,
            billing_count=observed.billing_count,
            secret_value_exposure_count=observed.secret_value_exposure_count,
            unapproved_network_call_count=observed.unapproved_network_call_count,
            general_command_count=observed.general_command_count,
        )
