"""Typed, validated runtime dependency container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from runtime.agents.registry import AgentRegistry
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.events.publisher import EventPublisher
from runtime.events.store import EventStore
from runtime.exceptions import RuntimeCompositionError
from runtime.execution.recovery import ExecutionRecoveryService
from runtime.execution.registry import ExecutorRegistry
from runtime.execution.service import ExecutionService
from runtime.orchestration.orchestrator import Orchestrator
from runtime.storage.artifact_store import ArtifactStore
from runtime.workflows.service import SoftwareDeliveryWorkflowService
from runtime.coding_agents.registry import CodingAgentProviderRegistry
from runtime.tasks.service import ExternalTaskService
from runtime.outbox.repository import InMemoryOutboxRepository
from runtime.outbox.service import OutboxService
from runtime.outbox.dispatcher import ProviderRegistry
from runtime.operations import (
    IdempotencyStore, ResultApplicationService,
)
from runtime.operations.registry import default_handler_registry
from runtime.projects.registry import InMemoryProjectRegistry

if TYPE_CHECKING:
    from runtime.persistence.interfaces import PersistenceProvider


@dataclass(frozen=True)
class RuntimeContainerConfiguration:
    """Configuration for one isolated in-memory runtime."""

    eventing_enabled: bool = True
    persistence_enabled: bool = False
    persistence_provider: PersistenceProvider | None = None
    runtime_id: str = "default-runtime"
    automatic_checkpoint_policy: bool = False
    writer_owner_id: str | None = None
    lease_ttl_seconds: int = 30

    def __post_init__(self) -> None:
        if not isinstance(self.eventing_enabled, bool):
            raise RuntimeCompositionError(
                "eventing_enabled must be a boolean value"
            )
        if not isinstance(self.persistence_enabled, bool):
            raise RuntimeCompositionError(
                "persistence_enabled must be a boolean value"
            )
        if not isinstance(self.runtime_id, str) or not self.runtime_id:
            raise RuntimeCompositionError("runtime_id must be a non-empty string")
        if not isinstance(self.automatic_checkpoint_policy, bool):
            raise RuntimeCompositionError(
                "automatic_checkpoint_policy must be boolean"
            )
        if self.writer_owner_id is not None and (
            not isinstance(self.writer_owner_id, str) or not self.writer_owner_id
        ):
            raise RuntimeCompositionError(
                "writer_owner_id must be a non-empty string"
            )
        if (
            not isinstance(self.lease_ttl_seconds, int)
            or isinstance(self.lease_ttl_seconds, bool)
            or self.lease_ttl_seconds < 1
        ):
            raise RuntimeCompositionError(
                "lease_ttl_seconds must be a positive integer"
            )
        if self.persistence_enabled and self.persistence_provider is None:
            raise RuntimeCompositionError(
                "persistence_provider is required when persistence is enabled"
            )


class ASCOSRuntimeContainer:
    """Create and retain one shared runtime object graph."""

    def __init__(
        self,
        configuration: RuntimeContainerConfiguration | None = None,
    ) -> None:
        if configuration is None:
            configuration = RuntimeContainerConfiguration()
        if not isinstance(configuration, RuntimeContainerConfiguration):
            raise RuntimeCompositionError(
                "configuration must be a RuntimeContainerConfiguration value"
            )
        self.configuration = configuration
        try:
            self.event_store = EventStore()
            self.event_publisher = (
                EventPublisher(self.event_store)
                if configuration.eventing_enabled
                else None
            )
            self.runtime_engine = RuntimeEngine(self.event_publisher)
            self.agent_registry = AgentRegistry(self.event_publisher)
            self.project_registry = InMemoryProjectRegistry(
                event_publisher=self.event_publisher
            )
            self.orchestrator = Orchestrator(
                self.runtime_engine,
                self.agent_registry,
                self.event_publisher,
            )
            self.executor_registry = ExecutorRegistry()
            self.artifact_store = ArtifactStore()
            self.execution_service = ExecutionService(
                self.orchestrator,
                self.executor_registry,
                self.event_publisher,
            )
            self.execution_recovery_service = ExecutionRecoveryService(
                self.execution_service,
                self.event_publisher,
            )
            self.software_delivery_workflow_service = (
                SoftwareDeliveryWorkflowService(
                    self.runtime_engine,
                    self.agent_registry,
                    self.orchestrator,
                    self.executor_registry,
                    self.execution_service,
                    self.execution_recovery_service,
                    self.event_publisher,
                )
            )
            self.coding_agent_provider_registry = CodingAgentProviderRegistry()
            self.external_task_service = ExternalTaskService(
                self.coding_agent_provider_registry,
                event_publisher=self.event_publisher,
            )
            self.outbox_repository = InMemoryOutboxRepository()
            self.outbox_service = OutboxService(
                self.outbox_repository, self.event_publisher
            )
            self.operation_handler_registry = default_handler_registry()
            self.dispatch_provider_registry = ProviderRegistry()
            self.idempotency_store = IdempotencyStore()
            self.result_application_service = ResultApplicationService(
                self.idempotency_store,
                event_publisher=self.event_publisher,
            )
            if self.event_publisher is not None:
                self.event_publisher.register_snapshot_provider(
                    self.result_application_service.snapshot_targets
                )
            self.persistence_service = None
            self.runtime_lease = None
            if configuration.persistence_enabled:
                from runtime.persistence.service import (
                    RuntimePersistenceService,
                )

                if configuration.writer_owner_id is not None:
                    lease_repository = getattr(
                        configuration.persistence_provider, "leases", None
                    )
                    if lease_repository is None:
                        raise RuntimeCompositionError(
                            "writer_owner_id requires a lease-capable provider"
                        )
                    self.runtime_lease = lease_repository.acquire_lease(
                        configuration.runtime_id,
                        configuration.writer_owner_id,
                        ttl_seconds=configuration.lease_ttl_seconds,
                    )
                self.persistence_service = RuntimePersistenceService(
                    configuration.persistence_provider,
                    configuration.runtime_id,
                    self,
                    automatic_checkpoint_policy=(
                        configuration.automatic_checkpoint_policy
                    ),
                    runtime_lease=self.runtime_lease,
                )
                self.software_delivery_workflow_service.configure_persistence_callback(
                    self.persistence_service.after_atomic_operation
                )
        except RuntimeCompositionError:
            raise
        except Exception as error:
            raise RuntimeCompositionError(
                "Failed to compose the ASCOS runtime"
            ) from error
