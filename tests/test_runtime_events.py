from datetime import datetime
from typing import Mapping

import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.events.event import RuntimeEvent
from runtime.events.publisher import EventPublisher
from runtime.events.store import EventStore
from runtime.events.types import EventType
from runtime.exceptions import (
    DuplicateActiveAssignmentError,
    DuplicateEventError,
    DuplicateWorkPackageError,
    EventNotFoundError,
    EventPublicationError,
    ExecutionFailedError,
    InvalidEventTypeError,
    ValidationError,
)
from runtime.execution.executor import DeterministicExecutor
from runtime.execution.recovery import ExecutionRecoveryService
from runtime.execution.registry import ExecutorRegistry
from runtime.execution.service import ExecutionService
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.orchestrator import Orchestrator


def publisher() -> tuple[EventStore, EventPublisher]:
    store = EventStore()
    return store, EventPublisher(store)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RuntimeEvent(
            "",
            EventType.WORK_PACKAGE_CREATED,
            "WORK_PACKAGE",
            "wp",
            1,
            {},
        ),
        lambda: RuntimeEvent(
            "event",
            "WORK_PACKAGE_CREATED",  # type: ignore[arg-type]
            "WORK_PACKAGE",
            "wp",
            1,
            {},
        ),
        lambda: RuntimeEvent(
            "event",
            EventType.WORK_PACKAGE_CREATED,
            "WORK_PACKAGE",
            "wp",
            0,
            {},
        ),
        lambda: RuntimeEvent(
            "event",
            EventType.WORK_PACKAGE_CREATED,
            "WORK_PACKAGE",
            "wp",
            1,
            {},
            occurred_at=datetime.now(),
        ),
    ],
)
def test_event_validation(factory: object) -> None:
    with pytest.raises((ValidationError, InvalidEventTypeError)):
        factory()


def test_duplicate_event_ids_are_rejected() -> None:
    store, events = publisher()
    events.publish(
        EventType.WORK_PACKAGE_CREATED,
        "WORK_PACKAGE",
        "wp",
        {},
        event_id="same",
    )

    with pytest.raises(DuplicateEventError):
        events.publish(
            EventType.WORK_ITEM_CREATED,
            "WORK_ITEM",
            "wp:wi",
            {},
            event_id="same",
        )


def test_payload_is_recursively_immutable_and_defensively_copied() -> None:
    _, events = publisher()
    payload = {"nested": {"items": ["original"]}}
    event = events.publish(
        EventType.WORK_PACKAGE_CREATED,
        "WORK_PACKAGE",
        "wp",
        payload,
    )
    payload["nested"]["items"].append("caller-change")

    assert event.payload["nested"]["items"] == ("original",)
    with pytest.raises(TypeError):
        event.payload["new"] = "value"
    with pytest.raises(TypeError):
        event.payload["nested"]["new"] = "value"


def test_payload_rejects_unsupported_mutable_custom_values() -> None:
    class MutableValue:
        pass

    _, events = publisher()

    with pytest.raises(ValidationError, match="payload values"):
        events.publish(
            EventType.WORK_PACKAGE_CREATED,
            "WORK_PACKAGE",
            "wp",
            {"unsupported": MutableValue()},
        )


def test_generated_event_ids_are_unambiguous_with_separators() -> None:
    _, events = publisher()

    first = events.publish(
        EventType.WORK_PACKAGE_CREATED,
        "A:B",
        "C",
        {},
    )
    second = events.publish(
        EventType.WORK_PACKAGE_CREATED,
        "A",
        "B:C",
        {},
    )

    assert first.id != second.id


def test_sequence_numbers_are_monotonic_per_aggregate() -> None:
    store, events = publisher()
    first = events.publish(
        EventType.WORK_PACKAGE_CREATED,
        "WORK_PACKAGE",
        "wp",
        {},
    )
    second = events.publish(
        EventType.WORK_ITEM_CREATED,
        "WORK_PACKAGE",
        "wp",
        {},
    )
    other = events.publish(
        EventType.WORK_PACKAGE_CREATED,
        "WORK_PACKAGE",
        "other",
        {},
    )

    assert (first.sequence_number, second.sequence_number) == (1, 2)
    assert other.sequence_number == 1
    assert store.next_sequence_number("WORK_PACKAGE", "wp") == 3


def test_correlation_queries_and_defensive_lists() -> None:
    store, events = publisher()
    event = events.publish(
        EventType.WORK_PACKAGE_CREATED,
        "WORK_PACKAGE",
        "wp",
        {},
        correlation_id="correlation",
        causation_id="cause",
    )

    assert store.get_event(event.id) is event
    assert store.list_events_for_correlation("correlation") == [event]
    assert event.causation_id == "cause"
    listed = store.list_events()
    listed.clear()
    assert store.list_events() == [event]
    with pytest.raises(EventNotFoundError):
        store.get_event("missing")


def test_runtime_and_agent_operations_emit_after_success_only() -> None:
    store, events = publisher()
    engine = RuntimeEngine(events)
    agents = AgentRegistry(events)
    engine.create_work_package("wp", "Package", "Description", "owner")
    engine.add_work_item("wp", "wi", "Work", "Description")
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    agent = agents.register_agent(
        AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            "Event agent",
        )
    )
    agents.update_agent_state(agent.id, AgentState.AVAILABLE)
    count = len(store.list_events())

    with pytest.raises(DuplicateWorkPackageError):
        engine.create_work_package("wp", "Duplicate", "Description", "owner")

    assert len(store.list_events()) == count
    assert {
        event.event_type for event in store.list_events()
    } >= {
        EventType.WORK_PACKAGE_CREATED,
        EventType.WORK_ITEM_CREATED,
        EventType.WORK_ITEM_STATE_CHANGED,
        EventType.AGENT_REGISTERED,
        EventType.AGENT_STATE_CHANGED,
    }


def build_integrated_runtime(
    *,
    fail_execution: bool = False,
) -> tuple[
    EventStore,
    RuntimeEngine,
    AgentRegistry,
    Orchestrator,
    ExecutorRegistry,
    ExecutionService,
    ExecutionRecoveryService,
]:
    store, events = publisher()
    engine = RuntimeEngine(events)
    agents = AgentRegistry(events)
    orchestrator = Orchestrator(engine, agents, events)
    executors = ExecutorRegistry()
    executions = ExecutionService(orchestrator, executors, events)
    recovery = ExecutionRecoveryService(executions, events)
    capability = AgentCapability("python", "Python", "Python", "1")
    agents.register_agent(
        AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            "Integrated agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=[capability],
        )
    )
    engine.create_work_package("wp", "Package", "Description", "owner")
    engine.add_work_item("wp", "wi", "Work", "Description")
    engine.change_work_item_state("wp", "wi", LifecycleState.READY)
    orchestrator.assign_work_item(
        "assignment",
        "wp",
        "wi",
        AgentRole.BACKEND_ENGINEER,
        ["python"],
    )
    executors.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
            should_fail=fail_execution,
            failure_message="expected failure",
        )
    )
    return (
        store,
        engine,
        agents,
        orchestrator,
        executors,
        executions,
        recovery,
    )


def test_assignment_events_are_emitted() -> None:
    store, _, _, orchestrator, _, _, _ = build_integrated_runtime()
    orchestrator.cancel_assignment("assignment")

    assignment_events = store.list_events_for_aggregate(
        "ASSIGNMENT",
        "assignment",
    )
    assert [event.event_type for event in assignment_events] == [
        EventType.ASSIGNMENT_CREATED,
        EventType.ASSIGNMENT_CANCELLED,
    ]


def test_successful_execution_events_are_ordered() -> None:
    store, _, _, _, _, executions, _ = build_integrated_runtime()
    executions.execute_assignment(
        "execution",
        "assignment",
        {"correlation_id": "correlation", "causation_id": "assignment-event"},
    )

    execution_events = store.list_events_for_aggregate(
        "EXECUTION",
        "execution",
    )
    assert [event.event_type for event in execution_events] == [
        EventType.EXECUTION_STARTED,
        EventType.EXECUTION_SUCCEEDED,
    ]
    assert [event.sequence_number for event in execution_events] == [1, 2]
    assert all(
        event.correlation_id == "correlation" for event in execution_events
    )


def test_failed_execution_and_recovery_events_are_emitted() -> None:
    store, _, _, _, _, executions, recovery = build_integrated_runtime(
        fail_execution=True
    )
    with pytest.raises(ExecutionFailedError):
        executions.execute_assignment("failed", "assignment")
    recovery.reset_failed_execution("recovery", "failed", "Manual reset")

    assert [
        event.event_type
        for event in store.list_events_for_aggregate("EXECUTION", "failed")
    ] == [EventType.EXECUTION_STARTED, EventType.EXECUTION_FAILED]
    assert [
        event.event_type
        for event in store.list_events_for_aggregate("RECOVERY", "recovery")
    ] == [EventType.EXECUTION_RECOVERY_RESET]


def test_retry_and_cancellation_recovery_events_are_emitted() -> None:
    retry_store, _, _, _, retry_executors, retry_executions, retry_recovery = (
        build_integrated_runtime(fail_execution=True)
    )
    with pytest.raises(ExecutionFailedError):
        retry_executions.execute_assignment("failed", "assignment")
    retry_executors.remove_executor("executor")
    retry_executors.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
        )
    )
    retry_recovery.retry_failed_execution(
        "retry-recovery",
        "failed",
        "retry",
        "Retry work",
    )

    cancel_store, _, _, _, _, cancel_executions, cancel_recovery = (
        build_integrated_runtime(fail_execution=True)
    )
    with pytest.raises(ExecutionFailedError):
        cancel_executions.execute_assignment("failed", "assignment")
    cancel_recovery.cancel_failed_assignment(
        "cancel-recovery",
        "failed",
        "Cancel work",
    )

    assert retry_store.list_events_for_aggregate(
        "RECOVERY",
        "retry-recovery",
    )[0].event_type == EventType.EXECUTION_RECOVERY_RETRIED
    assert cancel_store.list_events_for_aggregate(
        "RECOVERY",
        "cancel-recovery",
    )[0].event_type == EventType.EXECUTION_RECOVERY_CANCELLED


def test_failed_domain_mutation_does_not_emit_success_event() -> None:
    store, _, _, orchestrator, _, _, _ = build_integrated_runtime()
    before = list(store.list_events())

    with pytest.raises(DuplicateActiveAssignmentError):
        orchestrator.assign_work_item("duplicate", "wp", "wi")

    assert store.list_events() == before


class BrokenStore(EventStore):
    def add_event(self, event: RuntimeEvent) -> RuntimeEvent:
        raise RuntimeError("storage failed")


def test_event_publication_failure_is_not_silent() -> None:
    events = EventPublisher(BrokenStore())

    with pytest.raises(EventPublicationError):
        events.publish(
            EventType.WORK_PACKAGE_CREATED,
            "WORK_PACKAGE",
            "wp",
            {},
        )


@pytest.mark.parametrize(
    "integration",
    ["runtime", "agents", "orchestrator", "execution", "recovery"],
)
def test_integrations_propagate_event_publication_failures(
    integration: str,
) -> None:
    events = EventPublisher(BrokenStore())
    engine = RuntimeEngine(events)
    agents = AgentRegistry(events)

    if integration == "runtime":
        with pytest.raises(EventPublicationError):
            engine.create_work_package("wp", "Package", "Description", "owner")
        return
    if integration == "agents":
        with pytest.raises(EventPublicationError):
            agents.register_agent(
                AgentMetadata(
                    "agent",
                    "Agent",
                    AgentRole.BACKEND_ENGINEER,
                    "Agent",
                )
            )
        return

    plain_engine = RuntimeEngine()
    plain_agents = AgentRegistry()
    orchestrator = Orchestrator(plain_engine, plain_agents, events)
    capability = AgentCapability("python", "Python", "Python", "1")
    plain_agents.register_agent(
        AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            "Agent",
            state=AgentState.AVAILABLE,
            supported_capabilities=[capability],
        )
    )
    plain_engine.create_work_package("wp", "Package", "Description", "owner")
    plain_engine.add_work_item("wp", "wi", "Work", "Description")
    plain_engine.change_work_item_state("wp", "wi", LifecycleState.READY)

    if integration == "orchestrator":
        with pytest.raises(EventPublicationError):
            orchestrator.assign_work_item(
                "assignment",
                "wp",
                "wi",
                AgentRole.BACKEND_ENGINEER,
                ["python"],
            )
        return

    plain_orchestrator = Orchestrator(plain_engine, plain_agents)
    plain_orchestrator.assign_work_item(
        "assignment",
        "wp",
        "wi",
        AgentRole.BACKEND_ENGINEER,
        ["python"],
    )
    executors = ExecutorRegistry()
    executors.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
            should_fail=integration == "recovery",
            failure_message="expected failure",
        )
    )
    executions = ExecutionService(plain_orchestrator, executors, events)

    if integration == "execution":
        with pytest.raises(EventPublicationError):
            executions.execute_assignment("execution", "assignment")
        return

    plain_executions = ExecutionService(plain_orchestrator, executors)
    with pytest.raises(ExecutionFailedError):
        plain_executions.execute_assignment("failed", "assignment")
    recovery = ExecutionRecoveryService(plain_executions, events)
    with pytest.raises(EventPublicationError):
        recovery.reset_failed_execution("recovery", "failed", "Reset")
