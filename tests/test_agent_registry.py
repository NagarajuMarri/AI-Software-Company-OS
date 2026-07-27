import pytest

from runtime.agents.capability import AgentCapability
from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.exceptions import (
    AgentNotFoundError,
    DuplicateAgentError,
    InvalidAgentStateTransitionError,
    RuntimeDomainError,
    ValidationError,
)


@pytest.fixture
def python_capability() -> AgentCapability:
    return AgentCapability(
        id="python",
        name="Python",
        description="Build typed Python services",
        version="3.13",
        tags=["backend", "runtime"],
    )


def make_agent(
    agent_id: str = "agent-1",
    *,
    role: AgentRole = AgentRole.BACKEND_ENGINEER,
    capabilities: list[AgentCapability] | None = None,
) -> AgentMetadata:
    return AgentMetadata(
        id=agent_id,
        display_name=f"Agent {agent_id}",
        role=role,
        supported_capabilities=capabilities or [],
        max_parallel_tasks=2,
        priority=10,
        description="Production software engineering agent",
    )


def test_register_and_lookup_agent() -> None:
    registry = AgentRegistry()
    agent = registry.register_agent(make_agent())

    assert registry.get_agent("agent-1") is agent
    assert registry.list_agents() == [agent]


def test_duplicate_registration_is_rejected() -> None:
    registry = AgentRegistry()
    original = registry.register_agent(make_agent())

    with pytest.raises(DuplicateAgentError):
        registry.register_agent(make_agent())

    assert registry.get_agent("agent-1") is original


def test_role_search_preserves_registration_order() -> None:
    registry = AgentRegistry()
    backend = registry.register_agent(make_agent("backend"))
    registry.register_agent(
        make_agent("qa", role=AgentRole.QA_ENGINEER)
    )
    second_backend = registry.register_agent(make_agent("backend-2"))

    assert registry.find_agents_by_role(AgentRole.BACKEND_ENGINEER) == [
        backend,
        second_backend,
    ]


def test_capability_search_accepts_id_and_capability(
    python_capability: AgentCapability,
) -> None:
    registry = AgentRegistry()
    capable = registry.register_agent(
        make_agent("python-agent", capabilities=[python_capability])
    )
    registry.register_agent(make_agent("other"))

    assert registry.find_agents_by_capability("python") == [capable]
    assert registry.find_agents_by_capability(python_capability) == [capable]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AgentCapability("", "Python", "Description", "1"),
        lambda: AgentCapability("python", " ", "Description", "1"),
        lambda: AgentCapability("python", "Python", "", "1"),
        lambda: AgentCapability("python", "Python", "Description", " "),
        lambda: AgentCapability("python", "Python", "Description", "1", [""]),
        lambda: make_agent("", role=AgentRole.BACKEND_ENGINEER),
        lambda: AgentMetadata(
            "agent",
            "Agent",
            "BACKEND_ENGINEER",  # type: ignore[arg-type]
            description="Description",
        ),
        lambda: AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            state="AVAILABLE",  # type: ignore[arg-type]
            description="Description",
        ),
        lambda: AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            max_parallel_tasks=0,
            description="Description",
        ),
        lambda: AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            priority=True,
            description="Description",
        ),
        lambda: AgentMetadata(
            "agent",
            "Agent",
            AgentRole.BACKEND_ENGINEER,
            description=" ",
        ),
    ],
)
def test_invalid_values_are_rejected(factory: object) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_agent_state_updates_follow_policy() -> None:
    registry = AgentRegistry()
    agent = registry.register_agent(make_agent())

    assert registry.update_agent_state(
        agent.id, AgentState.AVAILABLE
    ).state == AgentState.AVAILABLE
    assert registry.update_agent_state(
        agent.id, AgentState.BUSY
    ).state == AgentState.BUSY
    assert registry.update_agent_state(
        agent.id, AgentState.AVAILABLE
    ).state == AgentState.AVAILABLE
    assert registry.update_agent_state(
        agent.id, AgentState.OFFLINE
    ).state == AgentState.OFFLINE


def test_invalid_and_same_state_updates_are_rejected() -> None:
    registry = AgentRegistry()
    agent = registry.register_agent(make_agent())

    with pytest.raises(InvalidAgentStateTransitionError):
        registry.update_agent_state(agent.id, AgentState.REGISTERED)
    with pytest.raises(ValidationError):
        registry.update_agent_state(
            agent.id,
            "AVAILABLE",  # type: ignore[arg-type]
        )


def test_disabled_agent_cannot_transition() -> None:
    registry = AgentRegistry()
    agent = registry.register_agent(make_agent())
    registry.update_agent_state(agent.id, AgentState.DISABLED)

    with pytest.raises(InvalidAgentStateTransitionError):
        registry.update_agent_state(agent.id, AgentState.AVAILABLE)


def test_agent_removal_and_missing_lookup() -> None:
    registry = AgentRegistry()
    agent = registry.register_agent(make_agent())

    assert registry.remove_agent(agent.id) is agent
    assert registry.list_agents() == []
    with pytest.raises(AgentNotFoundError):
        registry.get_agent(agent.id)
    with pytest.raises(AgentNotFoundError):
        registry.remove_agent(agent.id)


def test_registry_returns_defensive_agent_list() -> None:
    registry = AgentRegistry()
    registry.register_agent(make_agent())

    listed = registry.list_agents()
    listed.clear()

    assert len(registry.list_agents()) == 1


def test_agent_exceptions_use_runtime_domain_hierarchy() -> None:
    assert issubclass(DuplicateAgentError, RuntimeDomainError)
    assert issubclass(AgentNotFoundError, RuntimeDomainError)
    assert issubclass(InvalidAgentStateTransitionError, RuntimeDomainError)
