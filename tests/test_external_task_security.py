from runtime.coding_agents import DeterministicCodingAgentProvider
from runtime.composition import create_runtime_container
from runtime.persistence import FilePersistenceProvider
from tests.test_external_task_lifecycle import create


def test_checkpoint_and_events_do_not_contain_provider_credentials(tmp_path):
    provider = FilePersistenceProvider(tmp_path)
    container = create_runtime_container(
        persistence_enabled=True, persistence_provider=provider,
        runtime_id="security",
    )
    container.coding_agent_provider_registry.register_provider(
        DeterministicCodingAgentProvider()
    )
    create(container.external_task_service)
    checkpoint = container.persistence_service.save_checkpoint("security")
    text = repr(dict(checkpoint.payload))
    events = repr(container.event_store.list_events())
    assert "github_token" not in text.lower()
    assert "api_key" not in text.lower()
    assert "secret-value" not in text and "secret-value" not in events


def test_callable_github_adapter_redacts_underlying_exception():
    from runtime.integrations.github.provider import CallableGitHubProvider
    from runtime.integrations.github.exceptions import ExternalProviderUnavailableError
    import pytest

    def client(operation, request):
        raise RuntimeError("token=secret-value")

    with pytest.raises(ExternalProviderUnavailableError) as captured:
        CallableGitHubProvider(client).invoke("get", {})
    assert "secret-value" not in str(captured.value)
