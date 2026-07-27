from datetime import datetime, timezone

import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.exceptions import (
    AgentCapacityError,
    AssignmentNotFoundError,
    DuplicateActiveAssignmentError,
    InvalidAssignmentStateTransitionError,
    NoEligibleAgentError,
    RuntimeDomainError,
    ValidationError,
    WorkItemNotFoundError,
    WorkPackageNotFoundError,
)
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.assignment import AssignmentStatus, WorkAssignment
from runtime.orchestration.orchestrator import Orchestrator


def capability(capability_id: str) -> AgentCapability:
    return AgentCapability(
        id=capability_id,
        name=capability_id.title(),
        description=f"Support {capability_id}",
        version="1.0",
    )


def agent(
    agent_id: str,
    *,
    role: AgentRole = AgentRole.BACKEND_ENGINEER,
    state: AgentState = AgentState.AVAILABLE,
    capabilities: list[str] | None = None,
    max_parallel_tasks: int = 1,
    priority: int = 0,
) -> AgentMetadata:
    return AgentMetadata(
        id=agent_id,
        display_name=agent_id,
        role=role,
        description=f"Agent {agent_id}",
        state=state,
        supported_capabilities=[
            capability(item) for item in capabilities or []
        ],
        max_parallel_tasks=max_parallel_tasks,
        priority=priority,
    )


def add_ready_work_item(
    engine: RuntimeEngine,
    package_id: str,
    work_item_id: str,
) -> None:
    if not any(
        package.id == package_id
        for package in engine.list_work_packages()
    ):
        engine.create_work_package(
            package_id,
            f"Package {package_id}",
            "Orchestrated work",
            "platform",
        )
    engine.add_work_item(
        package_id,
        work_item_id,
        f"Item {work_item_id}",
        "Executable work",
    )
    engine.change_work_item_state(
        package_id,
        work_item_id,
        LifecycleState.READY,
    )


@pytest.fixture
def orchestration() -> tuple[RuntimeEngine, AgentRegistry, Orchestrator]:
    engine = RuntimeEngine()
    registry = AgentRegistry()
    return engine, registry, Orchestrator(engine, registry)


def test_successful_deterministic_assignment(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    add_ready_work_item(engine, "wp", "wi")
    selected = registry.register_agent(
        agent("agent", capabilities=["python"], priority=5)
    )

    result = orchestrator.select_agent(
        AgentRole.BACKEND_ENGINEER,
        ["python"],
    )
    assignment = orchestrator.assign_work_item(
        "assignment",
        "wp",
        "wi",
        AgentRole.BACKEND_ENGINEER,
        ["python"],
    )

    assert result.agent is selected
    assert result.score == 1
    assert result.matched_capabilities == ["python"]
    assert assignment.status == AssignmentStatus.ACTIVE
    assert assignment.agent_id == selected.id
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.ASSIGNED
    assert engine.get_work_item("wp", "wi").assigned_to == selected.id
    assert selected.state == AgentState.BUSY


def test_role_matching(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    _, registry, orchestrator = orchestration
    registry.register_agent(agent("backend"))
    frontend = registry.register_agent(
        agent("frontend", role=AgentRole.FRONTEND_ENGINEER)
    )

    assert orchestrator.select_agent(
        required_role=AgentRole.FRONTEND_ENGINEER
    ).agent is frontend


def test_capability_matching_requires_every_capability(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    _, registry, orchestrator = orchestration
    registry.register_agent(agent("python", capabilities=["python"]))
    full_match = registry.register_agent(
        agent("full", capabilities=["python", "postgres"])
    )

    assert orchestrator.select_agent(
        required_capabilities=["python", "postgres"]
    ).agent is full_match


@pytest.mark.parametrize(
    ("required_role", "required_capabilities"),
    [
        ("BACKEND_ENGINEER", []),
        (None, "python"),
        (None, [""]),
        (None, ["python", "python"]),
    ],
)
def test_selection_requirements_are_validated(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
    required_role: object | None,
    required_capabilities: object,
) -> None:
    _, _, orchestrator = orchestration

    with pytest.raises(ValidationError):
        orchestrator.select_agent(
            required_role=required_role,  # type: ignore[arg-type]
            required_capabilities=required_capabilities,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("state", [AgentState.OFFLINE, AgentState.DISABLED])
def test_unavailable_and_disabled_agents_are_excluded(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
    state: AgentState,
) -> None:
    _, registry, orchestrator = orchestration
    registry.register_agent(agent("excluded", state=state))

    with pytest.raises(NoEligibleAgentError):
        orchestrator.select_agent()


def test_capacity_is_enforced_and_agent_becomes_busy(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    worker = registry.register_agent(
        agent("worker", max_parallel_tasks=2)
    )
    for work_item_id in ("wi-1", "wi-2", "wi-3"):
        add_ready_work_item(engine, "wp", work_item_id)

    orchestrator.assign_work_item("a-1", "wp", "wi-1")
    assert worker.state == AgentState.AVAILABLE
    orchestrator.assign_work_item("a-2", "wp", "wi-2")
    assert worker.state == AgentState.BUSY
    assert orchestrator.get_active_assignment_count(worker.id) == 2

    with pytest.raises(AgentCapacityError):
        orchestrator.assign_work_item("a-3", "wp", "wi-3")


def test_priority_ordering(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    _, registry, orchestrator = orchestration
    registry.register_agent(agent("low", priority=1))
    high = registry.register_agent(agent("high", priority=10))

    assert orchestrator.select_agent().agent is high


def test_lowest_active_count_precedes_registration_order(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    first = registry.register_agent(
        agent(
            "first",
            capabilities=["python", "exclusive"],
            max_parallel_tasks=2,
        )
    )
    second = registry.register_agent(
        agent("second", capabilities=["python"], max_parallel_tasks=2)
    )
    add_ready_work_item(engine, "wp", "wi-1")
    orchestrator.assign_work_item(
        "a-1",
        "wp",
        "wi-1",
        required_capabilities=["exclusive"],
    )

    assert orchestrator.select_agent(
        required_capabilities=["python"]
    ).agent is second
    assert orchestrator.get_active_assignment_count(first.id) == 1


def test_registration_order_breaks_complete_tie(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    _, registry, orchestrator = orchestration
    first = registry.register_agent(agent("first"))
    registry.register_agent(agent("second"))

    assert orchestrator.select_agent().agent is first


def test_duplicate_active_assignment_is_prevented(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    registry.register_agent(agent("worker", max_parallel_tasks=2))
    add_ready_work_item(engine, "wp", "wi")
    orchestrator.assign_work_item("a-1", "wp", "wi")

    with pytest.raises(DuplicateActiveAssignmentError):
        orchestrator.assign_work_item("a-2", "wp", "wi")


def test_missing_package_and_work_item_use_runtime_errors(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    registry.register_agent(agent("worker"))

    with pytest.raises(WorkPackageNotFoundError):
        orchestrator.assign_work_item("a", "missing", "wi")

    engine.create_work_package("wp", "Package", "Description", "owner")
    with pytest.raises(WorkItemNotFoundError):
        orchestrator.assign_work_item("a", "wp", "missing")


@pytest.mark.parametrize(
    ("assignment_id", "package_id", "work_item_id"),
    [
        ("", "wp", "wi"),
        ("a", " ", "wi"),
        ("a", "wp", ""),
    ],
)
def test_assignment_relationship_ids_are_validated_before_lookup(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
    assignment_id: str,
    package_id: str,
    work_item_id: str,
) -> None:
    _, _, orchestrator = orchestration

    with pytest.raises(ValidationError):
        orchestrator.assign_work_item(
            assignment_id,
            package_id,
            work_item_id,
        )


def test_no_eligible_agent(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    add_ready_work_item(engine, "wp", "wi")
    registry.register_agent(
        agent("frontend", role=AgentRole.FRONTEND_ENGINEER)
    )

    with pytest.raises(NoEligibleAgentError):
        orchestrator.assign_work_item(
            "a",
            "wp",
            "wi",
            required_role=AgentRole.BACKEND_ENGINEER,
        )


@pytest.mark.parametrize("review_state", [LifecycleState.REVIEW, LifecycleState.APPROVED])
def test_assignment_completion(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
    review_state: LifecycleState,
) -> None:
    engine, registry, orchestrator = orchestration
    worker = registry.register_agent(agent("worker"))
    add_ready_work_item(engine, "wp", "wi")
    assignment = orchestrator.assign_work_item("a", "wp", "wi")
    engine.change_work_item_state("wp", "wi", LifecycleState.RUNNING)
    engine.change_work_item_state("wp", "wi", LifecycleState.REVIEW)
    if review_state == LifecycleState.APPROVED:
        engine.change_work_item_state("wp", "wi", LifecycleState.APPROVED)

    completed = orchestrator.complete_assignment(assignment.id)

    assert completed.status == AssignmentStatus.COMPLETED
    assert engine.get_work_item("wp", "wi").lifecycle_state == LifecycleState.COMPLETED
    assert worker.state == AgentState.AVAILABLE
    assert orchestrator.get_active_assignment_count(worker.id) == 0
    with pytest.raises(InvalidAssignmentStateTransitionError):
        orchestrator.complete_assignment(assignment.id)


def test_completion_requires_review_or_approval(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    registry.register_agent(agent("worker"))
    add_ready_work_item(engine, "wp", "wi")
    assignment = orchestrator.assign_work_item("a", "wp", "wi")

    with pytest.raises(InvalidAssignmentStateTransitionError):
        orchestrator.complete_assignment(assignment.id)
    assert assignment.status == AssignmentStatus.ACTIVE


def test_assignment_cancellation_returns_work_to_ready(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    worker = registry.register_agent(agent("worker"))
    add_ready_work_item(engine, "wp", "wi")
    assignment = orchestrator.assign_work_item("a", "wp", "wi")

    cancelled = orchestrator.cancel_assignment(assignment.id)

    work_item = engine.get_work_item("wp", "wi")
    assert cancelled.status == AssignmentStatus.CANCELLED
    assert work_item.lifecycle_state == LifecycleState.READY
    assert work_item.assigned_to is None
    assert worker.state == AgentState.AVAILABLE
    with pytest.raises(InvalidAssignmentStateTransitionError):
        orchestrator.cancel_assignment(assignment.id)


def test_cancellation_does_not_bypass_running_lifecycle(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    registry.register_agent(agent("worker"))
    add_ready_work_item(engine, "wp", "wi")
    assignment = orchestrator.assign_work_item("a", "wp", "wi")
    engine.change_work_item_state("wp", "wi", LifecycleState.RUNNING)

    with pytest.raises(InvalidAssignmentStateTransitionError):
        orchestrator.cancel_assignment(assignment.id)
    assert assignment.status == AssignmentStatus.ACTIVE


def test_assignment_retrieval_listing_and_defensive_copies(
    orchestration: tuple[RuntimeEngine, AgentRegistry, Orchestrator],
) -> None:
    engine, registry, orchestrator = orchestration
    worker = registry.register_agent(agent("worker"))
    add_ready_work_item(engine, "wp", "wi")
    assignment = orchestrator.assign_work_item("a", "wp", "wi")

    assert orchestrator.get_assignment("a") is assignment
    assert orchestrator.list_assignments_for_agent(worker.id) == [assignment]
    assert orchestrator.list_assignments_for_work_item("wp", "wi") == [assignment]
    listed = orchestrator.list_assignments()
    listed.clear()
    assert orchestrator.list_assignments() == [assignment]
    with pytest.raises(AssignmentNotFoundError):
        orchestrator.get_assignment("missing")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: WorkAssignment("", "wp", "wi", "agent"),
        lambda: WorkAssignment("a", "", "wi", "agent"),
        lambda: WorkAssignment("a", "wp", "", "agent"),
        lambda: WorkAssignment("a", "wp", "wi", ""),
        lambda: WorkAssignment(
            "a",
            "wp",
            "wi",
            "agent",
            status="ACTIVE",  # type: ignore[arg-type]
        ),
        lambda: WorkAssignment(
            "a",
            "wp",
            "wi",
            "agent",
            created_at=datetime.now(),  # noqa: DTZ005
        ),
    ],
)
def test_assignment_validation(factory: object) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_assignment_timestamps_and_relationships_are_preserved() -> None:
    assignment = WorkAssignment("a", "wp", "wi", "agent")

    assert assignment.package_id == "wp"
    assert assignment.work_item_id == "wi"
    assert assignment.agent_id == "agent"
    assert assignment.created_at.tzinfo == timezone.utc
    assert assignment.updated_at.tzinfo == timezone.utc


def test_orchestration_exception_hierarchy() -> None:
    for error in (
        AssignmentNotFoundError,
        DuplicateActiveAssignmentError,
        NoEligibleAgentError,
        InvalidAssignmentStateTransitionError,
        AgentCapacityError,
    ):
        assert issubclass(error, RuntimeDomainError)
