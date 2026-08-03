import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.coding_providers import (
    CodexCliCodingProvider, CodexCliProviderConfiguration, ProviderCapability,
    ProviderConfigurationError, ProviderStateError,
)
from runtime.tools.exceptions import CommandCancelledError, CommandTimeoutError
from runtime.tools.exceptions import InvalidCommandError
from runtime.tools.models import CommandResult


def command(arguments, stdout="", stderr="", exit_code=0, truncated=False):
    now = datetime.now(timezone.utc)
    return CommandResult("codex.cmd", tuple(arguments), exit_code, stdout, stderr,
                         now, now, 0.01, truncated)


class FakeRunner:
    def __init__(self, *, version="codex-cli 0.146.0", result=None, failure=None,
                 exit_code=0, stderr="", truncated=False):
        self.version = version
        self.result = result or valid_result()
        self.failure = failure
        self.exit_code = exit_code
        self.stderr = stderr
        self.truncated = truncated
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if self.failure:
            raise self.failure
        if request.arguments == ("--version",):
            return command(request.arguments, self.version)
        if request.arguments == ("exec", "--help"):
            return command(request.arguments, "Run Codex non-interactively")
        if "Reply with exactly: HELLO_ASCOS" in request.arguments:
            return command(request.arguments, "HELLO_ASCOS")
        output = Path(request.arguments[request.arguments.index("--output-last-message") + 1])
        output.write_text(self.result if isinstance(self.result, str)
                          else json.dumps(self.result), encoding="utf-8")
        return command(request.arguments, "bounded", self.stderr,
                       self.exit_code, self.truncated)


def valid_result(path="docs/ascos-codex-smoke.txt", content="OK\n"):
    return {
        "status": "SUCCEEDED", "summary": "Created the requested file.",
        "file_operations": [{"operation_type": "CREATE", "path": path,
                             "content": content, "expected_prior_digest": None}],
        "progress": ["proposal prepared"], "diagnostics": [],
    }


def request(tmp_path):
    context = SimpleNamespace(
        byte_count=100, objective="Create a fixture file", acceptance_criteria=("exact",),
        allowed_paths=("docs/ascos-codex-smoke.txt",), forbidden_paths=(".git", ".env"),
        files=(),
    )
    return SimpleNamespace(
        provider_operation_id="operation-1", provider_idempotency_key="key-1",
        external_task_id="external-1", project_id="fixture", execution_plan_id="plan-1",
        plan_version=1, managed_task_id="task-1", workspace_id="workspace-1",
        branch="agent/smoke", request_digest="request-digest",
        context_digest="context-digest", context=context, timeout_seconds=60,
        maximum_output_bytes=96_000,
    )


def configured(tmp_path, **changes):
    values = dict(enabled=True, allowed_workspace_root=str(tmp_path), health_smoke_test=False)
    values.update(changes)
    return CodexCliProviderConfiguration(**values)


def provider(tmp_path, runner=None, config=None, sink=None):
    receipts = []
    sink = sink or (lambda receipt, result: receipts.append((receipt, result)))
    item = CodexCliCodingProvider(config or configured(tmp_path),
                                  runner=runner or FakeRunner(), response_sink=sink)
    return item, receipts


def test_configuration_validates_version_exec_and_bounded_health(tmp_path):
    item, _ = provider(tmp_path, config=configured(tmp_path, health_smoke_test=True))
    item.validate_configuration()
    assert item.cli_version == "0.146.0"
    assert len(item.runner.requests) == 3
    assert all(call.environment == {} for call in item.runner.requests)


@pytest.mark.parametrize("runner, message", [
    (FakeRunner(version="missing"), "version"),
    (FakeRunner(version="codex-cli 0.145.0"), "unsupported"),
])
def test_missing_or_unsupported_executable_version_is_rejected(tmp_path, runner, message):
    item, _ = provider(tmp_path, runner=runner)
    with pytest.raises(ProviderConfigurationError, match=message):
        item.validate_configuration()


def test_codex_exec_unavailable_is_rejected(tmp_path):
    runner = FakeRunner()
    original = runner.execute
    runner.execute = lambda req: command(req.arguments, "", exit_code=1) \
        if req.arguments == ("exec", "--help") else original(req)
    item, _ = provider(tmp_path, runner=runner)
    with pytest.raises(ProviderConfigurationError, match="exec is unavailable"):
        item.validate_configuration()


def test_missing_executable_is_not_reported_healthy(tmp_path):
    item, _ = provider(tmp_path, runner=FakeRunner(failure=InvalidCommandError("missing")))
    with pytest.raises(InvalidCommandError, match="missing"):
        item.validate_configuration()


def test_success_is_structured_durable_and_idempotent(tmp_path):
    item, receipts = provider(tmp_path)
    task = request(tmp_path)
    first = item.submit_task(task)
    second = item.submit_task(task)
    assert first == second
    assert len(receipts) == 1
    receipt, result = receipts[0]
    assert receipt.provider_mechanism == "CODEX_CLI"
    assert receipt.terminal_status == "SUCCEEDED"
    assert receipt.changed_paths == ("docs/ascos-codex-smoke.txt",)
    assert result.file_operations[0].content == "OK\n"
    assert not (tmp_path / ".ascos-codex").exists()


@pytest.mark.parametrize("result", [
    "not-json",
    {**valid_result(), "commands": ["git push"]},
    valid_result("../escape.txt"),
    valid_result("C:/absolute.txt"),
    valid_result("outside.txt"),
    valid_result(content="binary\x00data"),
    valid_result(content="api_key=secret-shaped"),
    {**valid_result(), "file_operations": []},
    {**valid_result(), "file_operations": [{"operation_type": "DELETE",
      "path": "docs/ascos-codex-smoke.txt", "content": "", "expected_prior_digest": None}]},
])
def test_untrusted_results_are_rejected(tmp_path, result):
    item, receipts = provider(tmp_path, runner=FakeRunner(result=result))
    with pytest.raises(ProviderStateError):
        item.submit_task(request(tmp_path))
    assert receipts == []


@pytest.mark.parametrize("failure", [CommandTimeoutError("timeout"),
                                      CommandCancelledError("cancelled")])
def test_timeout_and_cancellation_have_no_receipt(tmp_path, failure):
    item, receipts = provider(tmp_path, runner=FakeRunner(failure=failure))
    with pytest.raises(type(failure)):
        item.submit_task(request(tmp_path))
    assert receipts == []


def test_nonzero_and_truncated_execution_are_rejected(tmp_path):
    for index, runner in enumerate((FakeRunner(exit_code=1, stderr="authentication failed"),
                                    FakeRunner(truncated=True))):
        workspace = tmp_path / str(index)
        workspace.mkdir()
        item, receipts = provider(workspace, runner=runner)
        with pytest.raises(ProviderStateError):
            item.submit_task(request(workspace))
        assert receipts == []


def test_oversized_result_and_request_limit_are_enforced(tmp_path):
    oversized = tmp_path / "oversized"
    oversized.mkdir()
    item, _ = provider(oversized, runner=FakeRunner(result=valid_result(content="x" * 200)),
                       config=configured(oversized, maximum_result_bytes=100))
    with pytest.raises(ProviderStateError, match="structured result"):
        item.submit_task(request(oversized))
    limited_root = tmp_path / "limited"
    limited_root.mkdir()
    limited, _ = provider(limited_root,
                          config=configured(limited_root, maximum_requests_per_pilot=1))
    limited.submit_task(request(limited_root))
    another = request(limited_root)
    another.provider_idempotency_key = "key-2"
    another.provider_operation_id = "operation-2"
    with pytest.raises(ProviderStateError, match="request limit"):
        limited.submit_task(another)


def test_capability_routing_is_explicit_and_excludes_privileged_effects(tmp_path):
    item, _ = provider(tmp_path)
    capabilities = set(item.capabilities())
    assert {ProviderCapability.CODE_GENERATION, ProviderCapability.TEST_GENERATION,
            ProviderCapability.DOCUMENTATION, ProviderCapability.REFACTORING,
            ProviderCapability.FRONTEND_IMPLEMENTATION} <= capabilities
    assert not capabilities.intersection({"COMMIT", "PUSH", "PR", "APPROVE", "MERGE", "DEPLOY"})


def test_receipt_failure_never_reports_success_and_leaves_reconciliation_artifacts(tmp_path):
    def unavailable(receipt, result):
        raise OSError("receipt store unavailable")

    item, _ = provider(tmp_path, sink=unavailable)
    with pytest.raises(OSError, match="receipt store unavailable"):
        item.submit_task(request(tmp_path))
    assert (tmp_path / ".ascos-codex" / "operation-1" / "result.json").is_file()


def test_symlink_or_reparse_escape_is_rejected(tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / "docs"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    item, _ = provider(tmp_path)
    with pytest.raises(Exception, match="link|reparse"):
        item.submit_task(request(tmp_path))
