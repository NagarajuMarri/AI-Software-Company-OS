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
            self.persistence_service = None
            if configuration.persistence_enabled:
                from runtime.persistence.service import (
                    RuntimePersistenceService,
                )

                self.persistence_service = RuntimePersistenceService(
                    configuration.persistence_provider,
                    configuration.runtime_id,
                    self,
                    automatic_checkpoint_policy=(
                        configuration.automatic_checkpoint_policy
                    ),
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
