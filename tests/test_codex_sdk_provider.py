import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.coding_providers import (
    CodexAuthenticationMode,
    CodexSdkExecutionConfiguration,
    CodexSdkExecutionProvider,
    CodingContextBuilder,
    CodingProviderRegistry,
    CodingProviderService,
    ContextLimits,
    ControlledPatchApplier,
    ProviderConfigurationError,
    ProviderOperationState,
    ProviderOperationStore,
    ProviderPolicyError,
    ProviderStateError,
)
from runtime.managed_execution import ChangePolicy


def _run_git(workspace, *arguments):
    result = subprocess.run(
        ("git", *arguments),
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def _workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _run_git(workspace, "init", "-b", "agent/pilot")
    _run_git(workspace, "config", "user.name", "ASCOS Test")
    _run_git(workspace, "config", "user.email", "ascos@example.invalid")
    (workspace / "base.py").write_text("VALUE = 1\n", encoding="utf-8")
    _run_git(workspace, "add", "--", "base.py")
    _run_git(workspace, "commit", "-m", "base")
    return workspace


def _response(path="feature.py", content="FEATURE = True\n"):
    return {
        "status": "SUCCEEDED",
        "summary": "Implemented the approved feature",
        "file_operations": [
            {"kind": "CREATE", "path": path, "content": content},
        ],
        "executed_activity": [],
        "artifacts": ["task-result"],
        "warnings": [],
        "unresolved_issues": [],
        "retryable": False,
    }


def _fake_sdk(response=None, *, account_type="chatgpt"):
    state = SimpleNamespace(
        response=response or _response(),
        configurations=[],
        thread_starts=[],
        turns=[],
        account_calls=0,
        account_type=account_type,
        login_keys=[],
    )

    class ApprovalMode:
        deny_all = "deny_all"

    class Sandbox:
        read_only = "read_only"

    class CodexConfig:
        def __init__(self, **values):
            self.values = values
            state.configurations.append(values)

    class Thread:
        id = "thread-governed-1"

        def run(self, prompt, **values):
            state.turns.append((prompt, values))
            return SimpleNamespace(
                final_response=json.dumps(state.response),
                usage=SimpleNamespace(
                    total=SimpleNamespace(input_tokens=101, output_tokens=23)
                ),
            )

    class Codex:
        def __init__(self, configuration):
            self.configuration = configuration

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def account(self):
            state.account_calls += 1
            return SimpleNamespace(
                account=SimpleNamespace(
                    root=SimpleNamespace(
                        type=state.account_type,
                        plan_type=SimpleNamespace(value="pro"),
                    )
                )
            )

        def login_api_key(self, api_key):
            state.login_keys.append(api_key)
            state.account_type = "apiKey"

        def thread_start(self, **values):
            state.thread_starts.append(values)
            return Thread()

    bindings = SimpleNamespace(
        ApprovalMode=ApprovalMode,
        Codex=Codex,
        CodexConfig=CodexConfig,
        Sandbox=Sandbox,
    )
    return bindings, state


class _GitProbe:
    def status(self, workspace):
        changed = tuple(
            line[3:]
            for line in _run_git(
                workspace, "status", "--porcelain=v1", "--untracked-files=all"
            ).splitlines()
        )
        return SimpleNamespace(
            clean=not changed,
            branch=_run_git(workspace, "branch", "--show-current").strip(),
            changed_paths=changed,
        )

    def current_commit(self, workspace):
        return _run_git(workspace, "rev-parse", "HEAD").strip()

    def diff(self, workspace):
        return _run_git(workspace, "diff", "--no-ext-diff")

    def diff_numstat(self, workspace):
        output = _run_git(workspace, "diff", "--numstat", "--no-ext-diff")
        additions = 0
        deletions = 0
        for line in output.splitlines():
            added, deleted, _ = line.split("\t", 2)
            additions += int(added)
            deletions += int(deleted)
        return additions, deletions


def _execution_values():
    plan = SimpleNamespace(
        project_id="product",
        execution_plan_id="plan-v1",
        version=1,
        workspace_identity="workspace-1",
        feature_branch="agent/pilot",
    )
    task = SimpleNamespace(
        project_task_id="task-1",
        objective="Add a bounded feature",
        acceptance_criteria=("feature module exists",),
        allowed_paths=("",),
        forbidden_paths=(".env", ".git/"),
        allowed_commands=(("python", "-m", "pytest"),),
        candidate_files=("base.py",),
    )
    coding_request = SimpleNamespace(
        external_task_id="plan-v1-task-1-attempt-1",
        timeout_seconds=60,
    )
    return plan, task, coding_request


def test_chatgpt_sdk_result_flows_through_controlled_patch_boundary(tmp_path):
    workspace = _workspace(tmp_path)
    bindings, sdk = _fake_sdk()
    store = ProviderOperationStore(tmp_path / "state")

    def response_sink(receipt, result):
        store.save_result(receipt.project_id, receipt.provider_operation_id, result)
        store.save_receipt(receipt)

    provider = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
            enabled=True,
            live_operation_confirmed=True,
        ),
        environment={
            "OPENAI_API_KEY": "must-not-be-used",
            "CODEX_API_KEY": "must-not-be-used",
            "CODEX_ACCESS_TOKEN": "must-not-be-used",
        },
        sdk_loader=lambda: bindings,
        response_sink=response_sink,
    )
    service = CodingProviderService(
        CodingProviderRegistry((provider,)),
        store,
        CodingContextBuilder(ContextLimits()),
        ControlledPatchApplier(),
        change_policies=(ChangePolicy("default", ("",), (".env", ".git/")),),
        git_provider_factory=lambda _: _GitProbe(),
    )
    plan, task, coding_request = _execution_values()
    operation, request = service.prepare(
        plan=plan,
        task=task,
        coding_request=coding_request,
        workspace_path=workspace,
        provider_id="openai-codex-sdk",
    )
    with pytest.raises(ProviderPolicyError, match="allow-live-provider"):
        service.submit("product", operation.provider_operation_id, request)
    with pytest.raises(ProviderPolicyError, match="confirm-usage-consumption"):
        service.submit(
            "product",
            operation.provider_operation_id,
            request,
            allow_live_provider=True,
        )
    submitted = service.submit(
        "product",
        operation.provider_operation_id,
        request,
        allow_live_provider=True,
        confirm_usage_consumption=True,
    )
    assert submitted.state == ProviderOperationState.SUBMITTED
    assert service.poll("product", operation.provider_operation_id).state == (
        ProviderOperationState.RESULT_AVAILABLE
    )
    result = service.result("product", operation.provider_operation_id)
    assert result.usage.authentication_mode == "chatgpt-subscription"
    assert result.usage.billing_source == "chatgpt-plan"
    assert result.usage.input_units == 101 and result.usage.output_units == 23
    assert not (workspace / "feature.py").exists()
    accepted, manifest = service.apply_and_accept(
        "product",
        operation.provider_operation_id,
        workspace_path=workspace,
        task=task,
        policy_id="default",
    )
    assert accepted.state == ProviderOperationState.RESULT_ACCEPTED
    assert manifest.changed_paths == ("feature.py",)
    assert (workspace / "feature.py").read_text(encoding="utf-8") == (
        "FEATURE = True\n"
    )
    assert sdk.account_calls == 1
    assert sdk.configurations[0]["env"] == {
        "CODEX_ACCESS_TOKEN": "",
        "CODEX_API_KEY": "",
        "OPENAI_API_KEY": "",
    }
    assert sdk.thread_starts[0]["sandbox"] == "read_only"
    assert sdk.thread_starts[0]["approval_mode"] == "deny_all"
    assert sdk.turns[0][1]["sandbox"] == "read_only"
    assert sdk.turns[0][1]["approval_mode"] == "deny_all"
    assert "must-not-be-used" not in json.dumps(sdk.turns)
    receipt = store.load_receipt("product", operation.provider_operation_id)
    assert receipt.usage.billing_source == "chatgpt-plan"


def test_platform_mode_isolates_personal_auth_and_records_platform_billing(tmp_path):
    workspace = _workspace(tmp_path)
    bindings, sdk = _fake_sdk()
    captured = []
    provider = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.PLATFORM_API_KEY,
            enabled=True,
            live_operation_confirmed=True,
        ),
        environment={"OPENAI_API_KEY": "platform-secret"},
        sdk_loader=lambda: bindings,
        response_sink=lambda receipt, result: captured.append((receipt, result)),
    )
    plan, task, coding_request = _execution_values()
    context = CodingContextBuilder(ContextLimits()).build(
        plan=plan,
        task=task,
        request=coding_request,
        workspace_path=workspace,
        evidence=(),
    )
    request = SimpleNamespace(
        provider_operation_id="provider-operation-1",
        provider_idempotency_key="idempotency-1",
        external_task_id=coding_request.external_task_id,
        project_id=plan.project_id,
        execution_plan_id=plan.execution_plan_id,
        plan_version=plan.version,
        managed_task_id=task.project_task_id,
        workspace_id=plan.workspace_identity,
        branch=plan.feature_branch,
        request_digest="request-digest",
        context_digest=context.context_digest,
        context=context,
        maximum_output_bytes=128_000,
    )
    provider.submit_task(request)
    environment = sdk.configurations[0]["env"]
    assert environment["OPENAI_API_KEY"] == ""
    assert environment["CODEX_ACCESS_TOKEN"] == ""
    assert environment["CODEX_API_KEY"] == ""
    assert environment["CODEX_HOME"]
    assert sdk.login_keys == ["platform-secret"]
    assert sdk.account_calls == 1
    receipt, result = captured[0]
    assert result.usage.authentication_mode == "platform-api-key"
    assert result.usage.billing_source == "openai-platform"
    assert receipt.usage.billing_source == "openai-platform"
    assert "platform-secret" not in json.dumps(receipt, default=str)
    assert "platform-secret" not in json.dumps(result, default=str)


def test_chatgpt_mode_rejects_a_different_active_account(tmp_path):
    workspace = _workspace(tmp_path)
    bindings, _ = _fake_sdk(account_type="apiKey")
    provider = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
            enabled=True,
            live_operation_confirmed=True,
        ),
        sdk_loader=lambda: bindings,
        response_sink=lambda receipt, result: None,
    )
    plan, task, coding_request = _execution_values()
    context = CodingContextBuilder().build(
        plan=plan,
        task=task,
        request=coding_request,
        workspace_path=workspace,
    )
    request = SimpleNamespace(
        provider_operation_id="provider-operation-1",
        provider_idempotency_key="idempotency-1",
        external_task_id=coding_request.external_task_id,
        project_id=plan.project_id,
        execution_plan_id=plan.execution_plan_id,
        plan_version=plan.version,
        managed_task_id=task.project_task_id,
        workspace_id=plan.workspace_identity,
        branch=plan.feature_branch,
        request_digest="request-digest",
        context_digest=context.context_digest,
        context=context,
        maximum_output_bytes=128_000,
    )
    with pytest.raises(ProviderConfigurationError, match="billing mode"):
        provider.submit_task(request)


def test_provider_rejects_branch_drift_and_invalid_structured_output(tmp_path):
    workspace = _workspace(tmp_path)
    bindings, sdk = _fake_sdk(response={"status": "SUCCEEDED"})
    provider = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
            enabled=True,
            live_operation_confirmed=True,
        ),
        sdk_loader=lambda: bindings,
        response_sink=lambda receipt, result: None,
    )
    plan, task, coding_request = _execution_values()
    context = CodingContextBuilder().build(
        plan=plan,
        task=task,
        request=coding_request,
        workspace_path=workspace,
    )
    request = SimpleNamespace(
        provider_operation_id="provider-operation-1",
        provider_idempotency_key="idempotency-1",
        external_task_id=coding_request.external_task_id,
        project_id=plan.project_id,
        execution_plan_id=plan.execution_plan_id,
        plan_version=plan.version,
        managed_task_id=task.project_task_id,
        workspace_id=plan.workspace_identity,
        branch="agent/wrong",
        request_digest="request-digest",
        context_digest=context.context_digest,
        context=context,
        maximum_output_bytes=128_000,
    )
    with pytest.raises(ProviderPolicyError, match="branch"):
        provider.submit_task(request)
    assert not sdk.thread_starts
    request.branch = "agent/pilot"
    with pytest.raises(ProviderStateError, match="invalid structured result"):
        provider.submit_task(request)
    sdk.response = _response()
    (workspace / "unexpected.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ProviderPolicyError, match="must be clean"):
        provider.submit_task(request)
    assert len(sdk.thread_starts) == 1


def test_provider_requires_live_enablement_key_sink_and_safe_sdk(tmp_path):
    workspace = _workspace(tmp_path)
    bindings, _ = _fake_sdk()
    disabled = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
        ),
        sdk_loader=lambda: bindings,
        response_sink=lambda receipt, result: None,
    )
    with pytest.raises(ProviderConfigurationError, match="not authorized"):
        disabled.validate_configuration()
    no_key = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.PLATFORM_API_KEY,
            enabled=True,
            live_operation_confirmed=True,
        ),
        environment={},
        sdk_loader=lambda: bindings,
        response_sink=lambda receipt, result: None,
    )
    with pytest.raises(ProviderConfigurationError, match="credential"):
        no_key.validate_configuration()
    no_sink = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
            enabled=True,
            live_operation_confirmed=True,
        ),
        sdk_loader=lambda: bindings,
    )
    with pytest.raises(ProviderConfigurationError, match="response sink"):
        no_sink.validate_configuration()
    unsafe = CodexSdkExecutionProvider(
        CodexSdkExecutionConfiguration(
            workspace,
            "gpt-5.6-terra",
            CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
            enabled=True,
            live_operation_confirmed=True,
        ),
        sdk_loader=lambda: SimpleNamespace(),
        response_sink=lambda receipt, result: None,
    )
    with pytest.raises(ProviderConfigurationError, match="bindings"):
        unsafe.validate_configuration()
