from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import stat
import subprocess
from urllib.parse import urlencode

import pytest

from runtime.coding_providers import CodexAuthenticationMode
from runtime.customer_application import ProductRequestNotFound
from runtime.customer_execution import (
    CustomerExecutionApplication,
    CustomerExecutionConfiguration,
    CustomerExecutionConflict,
    CustomerExecutionCorrupt,
    CustomerExecutionOutcome,
    CustomerExecutionPlanStatus,
    CustomerExecutionPolicyError,
    CustomerExecutionReconciliationRequired,
    CustomerExecutionService,
    CustomerExecutionTaskStatus,
    FileCustomerExecutionStore,
    create_governed_codex_adapter,
    inspect_workspace,
)
from runtime.customer_progress import CustomerProjectProgressService
from tests.test_codex_sdk_provider import _fake_sdk
from tests.test_customer_estimate import _generate, _services
from tests.test_customer_prd_approval import CSRF, NOW, _call


def _git(workspace: Path, *arguments: str) -> str:
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


def _workspace(root: Path) -> Path:
    workspace = root / "product-workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "agent/customer-product")
    _git(workspace, "config", "user.name", "ASCOS Test")
    _git(workspace, "config", "user.email", "ascos@example.invalid")
    (workspace / "src").mkdir()
    (workspace / "src" / "base.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(workspace, "add", "--", "src/base.py")
    _git(workspace, "commit", "-m", "product baseline")
    return workspace


def _configuration(workspace: Path, *, enabled: bool = True):
    return CustomerExecutionConfiguration(
        workspace,
        "gpt-5.6-terra",
        CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
        ("src",),
        ("src/base.py",),
        enabled=enabled,
        live_operation_confirmed=enabled,
    )


class _Adapter:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.calls = []

    @staticmethod
    def operation_id(plan, task):
        return f"provider-{plan.plan_id}-{task.task_id}-1"

    def execute(self, plan, task):
        self.calls.append((plan, task))
        (self.workspace / "src" / "feature.py").write_text(
            "ASCOS_CUSTOMER_EXECUTION_READY = True\n", encoding="utf-8"
        )
        return CustomerExecutionOutcome(
            self.operation_id(plan, task),
            "provider-task-1",
            ("src/feature.py",),
            1,
            0,
            120,
            24,
            1,
            "chatgpt-subscription",
            "chatgpt-plan",
            "Implemented the exact approved requirement",
            "f" * 64,
        )


def _ready(root: Path, *, real_adapter: bool = False):
    values = _services(root / "customer")
    _generate(values[18], values[16])
    progress = CustomerProjectProgressService(values[18])
    workspace = _workspace(root)
    configuration = _configuration(workspace)
    if real_adapter:
        bindings, sdk = _fake_sdk(
            {
                "status": "SUCCEEDED",
                "summary": "Implemented the exact approved requirement",
                "file_operations": [
                    {
                        "kind": "CREATE",
                        "path": "src/feature.py",
                        "content": "ASCOS_CUSTOMER_EXECUTION_READY = True\n",
                    }
                ],
                "executed_activity": [],
                "artifacts": ["task-result"],
                "warnings": [],
                "unresolved_issues": [],
                "retryable": False,
            }
        )
        adapter = create_governed_codex_adapter(
            root / "execution",
            configuration,
            environment={"OPENAI_API_KEY": "must-not-be-used"},
            sdk_loader=lambda: bindings,
        )
    else:
        adapter = _Adapter(workspace)
        sdk = None
    store = FileCustomerExecutionStore(root / "execution" / "plans")
    service = CustomerExecutionService(
        store,
        progress,
        values[18],
        configuration,
        adapter,
        lambda: NOW,
    )
    return service, store, workspace, adapter, sdk


def test_execution_configuration_rejects_browser_scale_and_unsafe_paths(tmp_path):
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError, match="forbidden"):
        replace(_configuration(workspace), allowed_paths=(".git",))
    with pytest.raises(ValueError, match="inside"):
        replace(_configuration(workspace), candidate_files=("tests/test_app.py",))
    with pytest.raises(ValueError, match="required"):
        replace(_configuration(workspace), candidate_files=())


def test_customer_creates_exact_plan_without_calling_provider(tmp_path):
    service, store, workspace, adapter, _ = _ready(tmp_path)
    before = inspect_workspace(workspace)
    plan = service.plan("customer-1", "req-1")

    assert plan.status is CustomerExecutionPlanStatus.AWAITING_APPROVAL
    assert plan.workspace_branch == "agent/customer-product"
    assert plan.workspace_commit == before.commit
    assert len(plan.tasks) == 6
    assert all(value.status is CustomerExecutionTaskStatus.PENDING for value in plan.tasks)
    assert all(value.allowed_paths == ("src",) for value in plan.tasks)
    assert plan.authentication_mode == "chatgpt-subscription"
    assert plan.billing_source == "chatgpt-plan"
    assert adapter.calls == []
    assert inspect_workspace(workspace) == before
    assert store.load("customer-1", "req-1") == plan


def test_exact_plan_approval_is_idempotent_and_stale_safe(tmp_path):
    service, _, _, _, _ = _ready(tmp_path)
    plan = service.plan("customer-1", "req-1")
    with pytest.raises(CustomerExecutionConflict, match="stale"):
        service.approve(
            "customer-1", "req-1", expected_scope_digest="0" * 64
        )
    approved = service.approve(
        "customer-1", "req-1", expected_scope_digest=plan.scope_digest
    )
    repeated = service.approve(
        "customer-1", "req-1", expected_scope_digest=plan.scope_digest
    )
    assert repeated == approved
    assert approved.status is CustomerExecutionPlanStatus.APPROVED
    assert approved.approved_by == "customer-1"


def test_execution_requires_both_confirmations_and_runs_only_one_task(tmp_path):
    service, store, workspace, adapter, _ = _ready(tmp_path)
    plan = service.plan("customer-1", "req-1")
    plan = service.approve(
        "customer-1", "req-1", expected_scope_digest=plan.scope_digest
    )
    with pytest.raises(CustomerExecutionPolicyError, match="both"):
        service.execute_next(
            "customer-1",
            "req-1",
            expected_scope_digest=plan.scope_digest,
            confirm_scope=True,
            confirm_usage_consumption=False,
        )
    completed = service.execute_next(
        "customer-1",
        "req-1",
        expected_scope_digest=plan.scope_digest,
        confirm_scope=True,
        confirm_usage_consumption=True,
    )

    assert completed.status is CustomerExecutionPlanStatus.REVIEW_REQUIRED
    assert completed.tasks[0].status is CustomerExecutionTaskStatus.REVIEW_REQUIRED
    assert all(
        value.status is CustomerExecutionTaskStatus.PENDING for value in completed.tasks[1:]
    )
    assert completed.tasks[0].changed_paths == ("src/feature.py",)
    assert completed.tasks[0].input_units == 120
    assert len(adapter.calls) == 1
    assert (workspace / "src" / "feature.py").is_file()
    assert _git(workspace, "status", "--porcelain").strip()
    assert _git(workspace, "rev-parse", "HEAD").strip() == completed.workspace_commit
    assert store.load("customer-1", "req-1") == completed
    with pytest.raises(CustomerExecutionConflict, match="not approved"):
        service.execute_next(
            "customer-1",
            "req-1",
            expected_scope_digest=completed.scope_digest,
            confirm_scope=True,
            confirm_usage_consumption=True,
        )


def test_workspace_branch_commit_and_cleanliness_are_approval_authority(tmp_path):
    service, _, workspace, _, _ = _ready(tmp_path)
    plan = service.plan("customer-1", "req-1")
    (workspace / "src" / "base.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(CustomerExecutionConflict, match="workspace"):
        service.approve(
            "customer-1", "req-1", expected_scope_digest=plan.scope_digest
        )


def test_plan_requires_existing_operator_selected_context_file(tmp_path):
    service, _, workspace, _, _ = _ready(tmp_path)
    configuration = replace(
        service._configuration, candidate_files=("src/missing.py",)
    )
    invalid = CustomerExecutionService(
        service._store,
        service._progress,
        service._estimates,
        configuration,
        _Adapter(workspace),
        lambda: NOW,
    )
    with pytest.raises(CustomerExecutionPolicyError, match="does not exist"):
        invalid.plan("customer-1", "req-1")


def test_uncertain_post_intent_failure_is_persisted_and_never_retried(tmp_path):
    service, store, _, adapter, _ = _ready(tmp_path)
    plan = service.plan("customer-1", "req-1")
    plan = service.approve(
        "customer-1", "req-1", expected_scope_digest=plan.scope_digest
    )

    def wrong_billing(current_plan, task):
        outcome = _Adapter.execute(adapter, current_plan, task)
        return replace(outcome, billing_source="openai-platform")

    adapter.execute = wrong_billing
    with pytest.raises(CustomerExecutionReconciliationRequired):
        service.execute_next(
            "customer-1",
            "req-1",
            expected_scope_digest=plan.scope_digest,
            confirm_scope=True,
            confirm_usage_consumption=True,
        )
    failed = store.load("customer-1", "req-1")
    assert failed.status is CustomerExecutionPlanStatus.RECONCILIATION_REQUIRED
    assert failed.tasks[0].status is CustomerExecutionTaskStatus.RECONCILIATION_REQUIRED
    assert failed.failure_classification == "CustomerExecutionPolicyError"
    with pytest.raises(CustomerExecutionConflict, match="not approved"):
        service.execute_next(
            "customer-1",
            "req-1",
            expected_scope_digest=failed.scope_digest,
            confirm_scope=True,
            confirm_usage_consumption=True,
        )


def test_execution_is_customer_scoped_and_store_detects_tamper(tmp_path):
    service, store, _, _, _ = _ready(tmp_path)
    plan = service.plan("customer-1", "req-1")
    with pytest.raises(ProductRequestNotFound):
        service.find("customer-2", "req-1")
    path = next((tmp_path / "execution" / "plans").rglob("execution-plan-v1.json"))
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["record"]["billing_source"] = "unknown"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(CustomerExecutionCorrupt, match="corrupt"):
        store.load(plan.customer_id, plan.request_id)


def test_execution_store_rejects_unknown_entries_permissions_and_symlink(tmp_path):
    service, store, _, _, _ = _ready(tmp_path / "closed")
    service.plan("customer-1", "req-1")
    plan_path = next(
        (tmp_path / "closed" / "execution" / "plans").rglob("execution-plan-v1.json")
    )
    (plan_path.parent / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CustomerExecutionCorrupt, match="not closed"):
        store.load("customer-1", "req-1")
    (plan_path.parent / "unknown.json").unlink()
    if os.name != "nt":
        plan_path.chmod(0o644)
        with pytest.raises(CustomerExecutionCorrupt, match="permissions"):
            store.load("customer-1", "req-1")

    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "execution-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(CustomerExecutionCorrupt, match="symbolic link"):
        FileCustomerExecutionStore(link)


def test_real_module2_adapter_is_reached_from_customer_service_and_stops_dirty(tmp_path):
    service, store, workspace, _, sdk = _ready(tmp_path, real_adapter=True)
    plan = service.plan("customer-1", "req-1")
    plan = service.approve(
        "customer-1", "req-1", expected_scope_digest=plan.scope_digest
    )
    completed = service.execute_next(
        "customer-1",
        "req-1",
        expected_scope_digest=plan.scope_digest,
        confirm_scope=True,
        confirm_usage_consumption=True,
    )

    task = completed.tasks[0]
    assert completed.status is CustomerExecutionPlanStatus.REVIEW_REQUIRED
    assert task.provider_task_id == "thread-governed-1"
    assert task.changed_paths == ("src/feature.py",)
    assert task.input_units == 101 and task.output_units == 23
    assert sdk.account_calls == 1
    assert sdk.thread_starts[0]["sandbox"] == "read_only"
    assert sdk.thread_starts[0]["approval_mode"] == "deny_all"
    assert sdk.configurations[0]["env"]["OPENAI_API_KEY"] == ""
    assert "must-not-be-used" not in json.dumps(sdk.turns)
    assert (workspace / "src" / "feature.py").read_text() == (
        "ASCOS_CUSTOMER_EXECUTION_READY = True\n"
    )
    assert _git(workspace, "status", "--porcelain").strip()
    assert not _git(workspace, "log", "-1", "--format=%s").startswith("ASCOS")
    receipt_files = tuple((tmp_path / "execution").rglob("response-receipts/*.json"))
    assert len(receipt_files) == 1
    assert store.load("customer-1", "req-1") == completed


def test_execution_dashboard_hides_operator_inputs_and_enforces_csrf(tmp_path):
    service, _, _, _, _ = _ready(tmp_path)
    application = CustomerExecutionApplication(service)
    path = "/customer/requests/req-1/execution"
    status, headers, content = _call(application, path=path)
    assert status == "200 OK"
    assert b"Create governed execution plan" in content
    assert b'name="workspace"' not in content
    assert b'name="model"' not in content
    assert b'name="api_key"' not in content
    assert b"commit, push, open a pull request" in content
    assert headers["Cache-Control"] == "no-store"
    assert _call(application, path=path, customer="customer-2")[0] == "404 Not Found"
    assert _call(application, path=path, customer=None)[0] == "401 Unauthorized"

    plan_path = f"{path}/plan"
    assert _call(
        application,
        path=plan_path,
        method="POST",
        body=urlencode({"csrf_token": "wrong"}),
    )[0] == "400 Bad Request"
    status, redirected, _ = _call(
        application,
        path=plan_path,
        method="POST",
        body=urlencode({"csrf_token": CSRF}),
    )
    assert status == "303 See Other" and redirected["Location"] == path
    plan = service.find("customer-1", "req-1")
    assert plan is not None

    status, _, content = _call(application, path=path)
    assert status == "200 OK"
    assert plan.scope_digest.encode() in content
    assert b"ChatGPT plan" in content
    assert b"Approve exact execution plan" in content
    assert str(workspace_path := service._configuration.workspace_root).encode() not in content

    approve = urlencode(
        {
            "csrf_token": CSRF,
            "scope_digest": plan.scope_digest,
            "confirm_plan": "yes",
        }
    )
    assert _call(
        application, path=f"{path}/approve", method="POST", body=approve
    )[0] == "303 See Other"
    approved = service.find("customer-1", "req-1")
    assert approved is not None
    execute = urlencode(
        {
            "csrf_token": CSRF,
            "scope_digest": approved.scope_digest,
            "confirm_scope": "yes",
            "confirm_usage": "yes",
        }
    )
    assert _call(
        application, path=f"{path}/execute", method="POST", body=execute
    )[0] == "303 See Other"
    status, _, content = _call(application, path=path)
    assert status == "200 OK"
    assert b"Durable Codex receipt" in content
    assert b"Human review required" in content
    assert str(workspace_path).encode() not in content


def test_execution_plan_file_is_private(tmp_path):
    service, _, _, _, _ = _ready(tmp_path)
    service.plan("customer-1", "req-1")
    path = next((tmp_path / "execution" / "plans").rglob("execution-plan-v1.json"))
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
