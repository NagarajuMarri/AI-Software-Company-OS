from runtime.coding_agents import (
    CodingAgentProviderRegistry, CodingAgentResultStatus,
    CodingAgentService, CodingAgentTaskRequest,
    DeterministicCodingAgentProvider,
)


def request():
    return CodingAgentTaskRequest(
        "task", "project", "repo", "workspace", "agent/task", "Change",
        (), ("tests pass",), ("python",), ("src",), "corr", 30,
    )


def test_deterministic_provider_progress_success_and_cancel():
    registry = CodingAgentProviderRegistry()
    provider = registry.register_provider(DeterministicCodingAgentProvider())
    _, identifier, progress, result = CodingAgentService(registry).execute(
        request(), {"python"}
    )
    assert [item.sequence for item in progress] == [1, 2]
    assert result.status == CodingAgentResultStatus.SUCCEEDED
    provider.cancel_task(identifier)
    assert provider.get_result(identifier).status == CodingAgentResultStatus.CANCELLED


def test_retryable_and_permanent_results_are_structured():
    provider = DeterministicCodingAgentProvider(outcomes=(
        CodingAgentResultStatus.FAILED_RETRYABLE,
        CodingAgentResultStatus.FAILED_PERMANENT,
    ))
    first = provider.submit_task(request())
    second = provider.submit_task(request())
    assert provider.get_result(first).failure_code == "FAILED_RETRYABLE"
    assert provider.get_result(second).failure_code == "FAILED_PERMANENT"
