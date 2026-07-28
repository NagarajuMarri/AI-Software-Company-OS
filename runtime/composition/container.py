"""Typed, validated runtime dependency container."""

from dataclasses import dataclass

from runtime.agents.registry import AgentRegistry
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.events.publisher import EventPublisher
from runtime.events.store import EventStore
from runtime.exceptions import RuntimeCompositionError
from runtime.execution.recovery import ExecutionRecoveryService
from runtime.execution.registry import ExecutorRegistry
from runtime.execution.service import ExecutionService
from runtime.orchestration.orchestrator import Orchestrator


@dataclass(frozen=True)
class RuntimeContainerConfiguration:
    """Configuration for one isolated in-memory runtime."""

    eventing_enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.eventing_enabled, bool):
            raise RuntimeCompositionError(
                "eventing_enabled must be a boolean value"
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
            self.execution_service = ExecutionService(
                self.orchestrator,
                self.executor_registry,
                self.event_publisher,
            )
            self.execution_recovery_service = ExecutionRecoveryService(
                self.execution_service,
                self.event_publisher,
            )
        except RuntimeCompositionError:
            raise
        except Exception as error:
            raise RuntimeCompositionError(
                "Failed to compose the ASCOS runtime"
            ) from error
