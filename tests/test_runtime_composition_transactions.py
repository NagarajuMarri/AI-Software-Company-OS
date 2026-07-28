import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.composition import create_runtime_container
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.events.publisher import EventPublisher
from runtime.events.store import EventStore
from runtime.events.types import EventType
from runtime.exceptions import (
    ExecutionFailedError,
    NestedTransactionError,
    RuntimeCompositionError,
    TransactionAlreadyCompletedError,
    TransactionCommitError,
)
from runtime.execution.executor import DeterministicExecutor
from runtime.models.lifecycle import LifecycleState
from runtime.transactions import RuntimeTransaction


def agent() -> AgentMetadata:
    return AgentMetadata(
        "agent",
        "Agent",
        AgentRole.BACKEND_ENGINEER,
        "Runtime agent",
        state=AgentState.AVAILABLE,
        supported_capabilities=[
            AgentCapability("python", "Python", "Python", "1")
        ],
    )


def ready_container(*, failing_executor: bool = False):
    container = create_runtime_container()
    container.agent_registry.register_agent(agent())
    container.runtime_engine.create_work_package(
        "wp", "Package", "Description", "owner"
    )
    container.runtime_engine.add_work_item(
        "wp", "wi", "Work", "Description"
    )
    container.runtime_engine.change_work_item_state(
        "wp", "wi", LifecycleState.READY
    )
    container.orchestrator.assign_work_item(
        "assignment",
        "wp",
        "wi",
        AgentRole.BACKEND_ENGINEER,
        ["python"],
    )
    container.executor_registry.register_executor(
        DeterministicExecutor(
            "executor",
            [AgentRole.BACKEND_ENGINEER],
            ["python"],
            should_fail=failing_executor,
            failure_message="expected failure",
        )
    )
    return container


def fail_storage(container) -> None:
    def broken_add_events(events):
        raise RuntimeError("storage failed")

    container.event_store.add_events = broken_add_events


def test_default_container_wires_one_shared_publisher() -> None:
    container = create_runtime_container()
    publisher = container.event_publisher

    assert publisher is not None
    assert publisher.event_store is container.event_store
    assert container.runtime_engine.event_publisher is publisher
    assert container.agent_registry.event_publisher is publisher
    assert container.orchestrator.event_publisher is publisher
    assert container.execution_service.event_publisher is publisher
    assert container.execution_recovery_service.event_publisher is publisher
    assert container.orchestrator.runtime_engine is container.runtime_engine
    assert container.execution_service.orchestrator is container.orchestrator


def test_container_configuration_and_no_singleton_state() -> None:
    disabled = create_runtime_container(eventing_enabled=False)
    other = create_runtime_container()

    assert disabled.event_publisher is None
    assert disabled.event_store.list_events() == []
    disabled.runtime_engine.create_work_package(
        "wp", "Package", "Description", "owner"
    )
    assert disabled.event_store.list_events() == []
    assert other.event_store is not disabled.event_store
    with pytest.raises(RuntimeCompositionError):
        create_runtime_container(eventing_enabled="yes")  # type: ignore[arg-type]


def test_independent_construction_remains_supported() -> None:
    engine = RuntimeEngine()
    agents = AgentRegistry(EventPublisher(EventStore()))

    assert engine.create_work_package(
        "wp", "Package", "Description", "owner"
    ).id == "wp"
    assert agents.register_agent(agent()).id == "agent"


def test_events_are_staged_until_commit_and_discarded_on_rollback() -> None:
    store = EventStore()
    publisher = EventPublisher(store)

    with publisher.transaction():
        publisher.publish(
            EventType.WORK_PACKAGE_CREATED,
            "WORK_PACKAGE",
            "wp",
            {},
        )
        assert store.list_events() == []
    assert len(store.list_events()) == 1

    with pytest.raises(RuntimeError):
        with publisher.transaction():
            publisher.publish(
                EventType.WORK_PACKAGE_CREATED,
                "WORK_PACKAGE",
                "other",
                {},
            )
            raise RuntimeError("domain failed")
    assert len(store.list_events()) == 1


def test_transaction_lifecycle_and_nested_policy() -> None:
    store = EventStore()
    transaction = RuntimeTransaction(store)
    transaction.commit()

    with pytest.raises(TransactionAlreadyCompletedError):
        transaction.commit()
    with pytest.raises(TransactionAlreadyCompletedError):
        transaction.rollback()

    rolled_back = RuntimeTransaction(store)
    rolled_back.rollback()
    with pytest.raises(TransactionAlreadyCompletedError):
        rolled_back.stage(None)  # type: ignore[arg-type]

    publisher = EventPublisher(store)
    with publisher.transaction():
        with pytest.raises(NestedTransactionError):
            with publisher.transaction():
                pass


def test_runtime_and_agent_storage_failures_roll_back_state_and_events() -> None:
    container = create_runtime_container()
    fail_storage(container)

    with pytest.raises(TransactionCommitError):
        container.runtime_engine.create_work_package(
            "wp", "Package", "Description", "owner"
        )
    with pytest.raises(TransactionCommitError):
        container.agent_registry.register_agent(agent())

    assert container.runtime_engine.list_work_packages() == []
    assert container.agent_registry.list_agents() == []
    assert container.event_store.list_events() == []


def test_work_item_mutation_storage_failure_rolls_back() -> None:
    container = create_runtime_container()
    package = container.runtime_engine.create_work_package(
        "wp", "Package", "Description", "owner"
    )
    fail_storage(container)

    with pytest.raises(TransactionCommitError):
        container.runtime_engine.add_work_item(
            "wp", "wi", "Work", "Description"
        )

    assert package.work_items == []


def test_assignment_storage_failure_leaves_no_partial_assignment() -> None:
    container = create_runtime_container()
    container.agent_registry.register_agent(agent())
    container.runtime_engine.create_work_package(
        "wp", "Package", "Description", "owner"
    )
    container.runtime_engine.add_work_item(
        "wp", "wi", "Work", "Description"
    )
    container.runtime_engine.change_work_item_state(
        "wp", "wi", LifecycleState.READY
    )
    before_events = list(container.event_store.list_events())
    fail_storage(container)

    with pytest.raises(TransactionCommitError):
        container.orchestrator.assign_work_item(
            "assignment",
            "wp",
            "wi",
            AgentRole.BACKEND_ENGINEER,
            ["python"],
        )

    item = container.runtime_engine.get_work_item("wp", "wi")
    assert item.lifecycle_state == LifecycleState.READY
    assert item.assigned_to is None
    assert container.orchestrator.list_assignments() == []
    assert container.agent_registry.get_agent("agent").state == AgentState.AVAILABLE
    assert container.event_store.list_events() == before_events


def test_execution_storage_failure_leaves_no_partial_execution() -> None:
    container = ready_container()
    before_events = list(container.event_store.list_events())
    fail_storage(container)

    with pytest.raises(TransactionCommitError):
        container.execution_service.execute_assignment(
            "execution", "assignment"
        )

    assert container.execution_service.list_executions() == []
    assert (
        container.runtime_engine.get_work_item("wp", "wi").lifecycle_state
        == LifecycleState.ASSIGNED
    )
    assert container.event_store.list_events() == before_events


def test_recovery_storage_failure_leaves_no_partial_recovery() -> None:
    container = ready_container(failing_executor=True)
    with pytest.raises(ExecutionFailedError):
        container.execution_service.execute_assignment(
            "failed", "assignment"
        )
    before_events = list(container.event_store.list_events())
    fail_storage(container)

    with pytest.raises(TransactionCommitError):
        container.execution_recovery_service.reset_failed_execution(
            "recovery", "failed", "Reset"
        )

    assert container.execution_recovery_service.list_recovery_records() == []
    assert (
        container.runtime_engine.get_work_item("wp", "wi").lifecycle_state
        == LifecycleState.RUNNING
    )
    assert container.orchestrator.get_assignment("assignment").status.value == "ACTIVE"
    assert container.event_store.list_events() == before_events
