from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import threading

import pytest

from runtime.agents import AgentRole
from runtime.digital_twin import (
    ContextValue,
    DelegatedAuthority,
    DeterministicDigitalTwinProvider,
    DeterministicToolInvocation,
    DigitalTwinAssignment,
    DigitalTwinDefinition,
    DigitalTwinExecutionError,
    DigitalTwinExecutionStatus,
    DigitalTwinPolicyError,
    DigitalTwinProviderRegistry,
    DigitalTwinRegistryError,
    DigitalTwinRuntime,
    DigitalTwinStoreError,
    DigitalTwinToolRegistry,
    EXECUTE_ASSIGNED_WORK,
    FileDigitalTwinExecutionStore,
    PRODUCE_EXECUTION_EVIDENCE,
    ReadOnlyRecordTool,
    ToolCallOutcome,
    USE_ASSIGNED_TOOL,
)
from runtime.digital_twin.models import ProviderExecutionResult


NOW = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
OBJECTIVE = "Summarize one declared, non-product verification record."
TOOL_ID = "fixture.record.lookup"
CAPABILITY_ID = "structured-summary"


def _authority(**changes) -> DelegatedAuthority:
    values = {
        "authority_id": "authority-day22-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": "ascos-verification",
        "assignment_id": "assignment-day22-1",
        "twin_id": "twin-verification-1",
        "business_role": AgentRole.QA_ENGINEER,
        "objective_digest": hashlib.sha256(OBJECTIVE.encode()).hexdigest(),
        "allowed_action_ids": (
            EXECUTE_ASSIGNED_WORK,
            USE_ASSIGNED_TOOL,
            PRODUCE_EXECUTION_EVIDENCE,
        ),
        "allowed_tool_ids": (TOOL_ID,),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
        "max_tool_calls": 2,
        "max_output_bytes": 8_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _assignment(authority: DelegatedAuthority, **changes) -> DigitalTwinAssignment:
    values = {
        "assignment_id": authority.assignment_id,
        "tenant_id": authority.tenant_id,
        "twin_id": authority.twin_id,
        "business_role": authority.business_role,
        "objective": OBJECTIVE,
        "context": (
            ContextValue("record_key", "verification_scope"),
            ContextValue("fixture_contract", "No official pilot product is selected"),
        ),
        "required_capability_ids": (CAPABILITY_ID,),
        "requested_tool_ids": (TOOL_ID,),
        "authority_id": authority.authority_id,
        "authority_digest": authority.digest,
        "created_at": NOW + timedelta(minutes=1),
    }
    values.update(changes)
    return DigitalTwinAssignment(**values)


def _provider(*, tool_id: str = TOOL_ID) -> DeterministicDigitalTwinProvider:
    return DeterministicDigitalTwinProvider(
        "deterministic-day22",
        roles=(AgentRole.QA_ENGINEER,),
        capabilities=(CAPABILITY_ID,),
        tool_invocations=(
            DeterministicToolInvocation(
                tool_id,
                (("record_key", "verification_scope"),),
            ),
        ),
    )


def _definition(**changes) -> DigitalTwinDefinition:
    values = {
        "twin_id": "twin-verification-1",
        "display_name": "Digital Twin runtime verification",
        "business_role": AgentRole.QA_ENGINEER,
        "provider_id": "deterministic-day22",
        "capability_ids": (CAPABILITY_ID,),
        "approved_tool_ids": (TOOL_ID,),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _tool(tool_id: str = TOOL_ID) -> ReadOnlyRecordTool:
    return ReadOnlyRecordTool(
        tool_id,
        (("verification_scope", "Role, tool, and authority boundaries passed"),),
    )


def _runtime(
    tmp_path: Path,
    *,
    provider=None,
    tools=None,
    clock=lambda: NOW + timedelta(minutes=2),
    allow_live_providers: bool = False,
) -> tuple[DigitalTwinRuntime, object]:
    selected_provider = provider or _provider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected_provider,)),
        DigitalTwinToolRegistry(tuple(tools or (_tool(),))),
        FileDigitalTwinExecutionStore(tmp_path / "digital-twin-state"),
        clock=clock,
        allow_live_providers=allow_live_providers,
    )
    return runtime, selected_provider


def test_real_provider_receives_exact_role_tool_and_authority(tmp_path: Path) -> None:
    authority = _authority()
    assignment = _assignment(authority)
    twin = _definition()
    runtime, provider = _runtime(tmp_path)

    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=twin,
        assignment=assignment,
        authority=authority,
    )

    assert receipt.status is DigitalTwinExecutionStatus.SUCCEEDED
    assert receipt.twin_digest == twin.digest
    assert receipt.assignment_digest == assignment.digest
    assert receipt.authority_digest == authority.digest
    assert receipt.provider_id == "deterministic-day22"
    assert len(receipt.tool_calls) == 1
    assert receipt.tool_calls[0].tool_id == TOOL_ID
    assert receipt.tool_calls[0].outcome is ToolCallOutcome.SUCCEEDED
    assert provider.execution_count == 1
    assert len(receipt.digest) == 64


def test_exact_retry_and_restart_reopen_receipt_without_provider_effect(tmp_path: Path) -> None:
    authority = _authority()
    assignment = _assignment(authority)
    twin = _definition()
    runtime, provider = _runtime(tmp_path)
    first = runtime.execute(
        execution_id="execution-day22-1",
        twin=twin,
        assignment=assignment,
        authority=authority,
    )
    assert runtime.execute(
        execution_id="execution-day22-1",
        twin=twin,
        assignment=assignment,
        authority=authority,
    ) == first
    assert provider.execution_count == 1

    restarted, restarted_provider = _runtime(tmp_path)
    assert restarted.execute(
        execution_id="execution-day22-1",
        twin=twin,
        assignment=assignment,
        authority=authority,
    ) == first
    assert restarted_provider.execution_count == 0


def test_concurrent_store_instances_serialize_one_provider_effect(tmp_path: Path) -> None:
    authority = _authority()
    assignment = _assignment(authority)
    twin = _definition()
    entered = threading.Event()
    release = threading.Event()
    first_provider = _provider()
    first_execute = first_provider.execute

    def held_execute(request, tools):
        entered.set()
        assert release.wait(timeout=2)
        return first_execute(request, tools)

    first_provider.execute = held_execute
    first_runtime, _ = _runtime(tmp_path, provider=first_provider)
    second_runtime, second_provider = _runtime(tmp_path)

    def execute(runtime):
        return runtime.execute(
            execution_id="execution-day22-concurrent",
            twin=twin,
            assignment=assignment,
            authority=authority,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(execute, first_runtime)
        assert entered.wait(timeout=2)
        second_future = pool.submit(execute, second_runtime)
        release.set()
        first = first_future.result(timeout=3)
        second = second_future.result(timeout=3)

    assert first == second
    assert first_provider.execution_count == 1
    assert second_provider.execution_count == 0


@pytest.mark.parametrize(
    ("twin_change", "assignment_change", "authority_change"),
    [
        ({"twin_id": "another-twin"}, {}, {}),
        ({"business_role": AgentRole.SECURITY_ENGINEER}, {}, {}),
        ({}, {"tenant_id": "another-tenant"}, {}),
        ({}, {"business_role": AgentRole.SECURITY_ENGINEER}, {}),
        ({}, {"objective": "A different objective"}, {}),
        (
            {},
            {"assignment_id": "assignment-day22-1"},
            {"assignment_id": "another-assignment"},
        ),
    ],
)
def test_identity_role_and_objective_mismatches_fail_before_effect(
    tmp_path: Path,
    twin_change,
    assignment_change,
    authority_change,
) -> None:
    authority = _authority(**authority_change)
    assignment = _assignment(authority, **assignment_change)
    twin = _definition(**twin_change)
    runtime, provider = _runtime(tmp_path)

    with pytest.raises(DigitalTwinPolicyError):
        runtime.execute(
            execution_id="execution-day22-1",
            twin=twin,
            assignment=assignment,
            authority=authority,
        )
    assert provider.execution_count == 0
    assert not (tmp_path / "digital-twin-state" / assignment.tenant_id).exists()


def test_expired_future_and_overlong_authority_are_rejected(tmp_path: Path) -> None:
    expired = _authority(
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1),
    )
    runtime, provider = _runtime(tmp_path)
    with pytest.raises(DigitalTwinPolicyError, match="not current"):
        runtime.execute(
            execution_id="execution-day22-1",
            twin=_definition(),
            assignment=_assignment(
                expired,
                created_at=NOW - timedelta(hours=1, minutes=30),
            ),
            authority=expired,
        )
    assert provider.execution_count == 0

    with pytest.raises(ValueError, match="24 hours"):
        _authority(expires_at=NOW + timedelta(hours=25))


@pytest.mark.parametrize(
    "allowed_action_ids",
    [
        (USE_ASSIGNED_TOOL,),
        (EXECUTE_ASSIGNED_WORK, USE_ASSIGNED_TOOL),
        (EXECUTE_ASSIGNED_WORK, USE_ASSIGNED_TOOL, "MERGE"),
        (EXECUTE_ASSIGNED_WORK, USE_ASSIGNED_TOOL, "DEPLOY"),
        (EXECUTE_ASSIGNED_WORK, USE_ASSIGNED_TOOL, "WRITE_PRODUCT_REPOSITORY"),
        (EXECUTE_ASSIGNED_WORK, USE_ASSIGNED_TOOL, "SELECT_PILOT_PRODUCT"),
    ],
)
def test_missing_or_prohibited_authority_never_becomes_executable(
    allowed_action_ids,
) -> None:
    with pytest.raises(ValueError):
        _authority(allowed_action_ids=allowed_action_ids)


def test_unapproved_and_unregistered_tools_fail_before_provider(tmp_path: Path) -> None:
    authority = _authority(allowed_tool_ids=(TOOL_ID, "fixture.other"))
    assignment = _assignment(authority, requested_tool_ids=("fixture.other",))
    runtime, provider = _runtime(tmp_path)
    with pytest.raises(DigitalTwinPolicyError):
        runtime.execute(
            execution_id="execution-day22-1",
            twin=_definition(),
            assignment=assignment,
            authority=authority,
        )
    assert provider.execution_count == 0


def test_provider_cannot_invoke_a_tool_omitted_from_assignment(tmp_path: Path) -> None:
    extra_tool_id = "fixture.unassigned.lookup"
    provider = _provider(tool_id=extra_tool_id)
    authority = _authority()
    assignment = _assignment(authority, requested_tool_ids=())
    twin = _definition(approved_tool_ids=(TOOL_ID, extra_tool_id))
    runtime, _ = _runtime(
        tmp_path,
        provider=provider,
        tools=(_tool(), _tool(extra_tool_id)),
    )

    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=twin,
        assignment=assignment,
        authority=authority,
    )

    assert receipt.status is DigitalTwinExecutionStatus.FAILED
    assert receipt.failure_code == "TOOL_POLICY_FAILURE"
    assert receipt.tool_calls == ()
    assert provider.execution_count == 1


def test_tool_call_budget_is_enforced_and_recorded(tmp_path: Path) -> None:
    invocation = DeterministicToolInvocation(
        TOOL_ID,
        (("record_key", "verification_scope"),),
    )
    provider = DeterministicDigitalTwinProvider(
        "deterministic-day22",
        roles=(AgentRole.QA_ENGINEER,),
        capabilities=(CAPABILITY_ID,),
        tool_invocations=(invocation, invocation),
    )
    authority = _authority(max_tool_calls=1)
    runtime, _ = _runtime(tmp_path, provider=provider)

    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=_definition(),
        assignment=_assignment(authority),
        authority=authority,
    )

    assert receipt.status is DigitalTwinExecutionStatus.FAILED
    assert receipt.failure_code == "TOOL_POLICY_FAILURE"
    assert len(receipt.tool_calls) == 1
    assert receipt.tool_calls[0].outcome is ToolCallOutcome.SUCCEEDED


def test_provider_result_identity_and_output_budget_fail_closed(tmp_path: Path) -> None:
    provider = _provider()
    original = provider.execute

    def wrong_identity(request, tools):
        result = original(request, tools)
        return replace(result, execution_id="other-execution")

    provider.execute = wrong_identity
    authority = _authority()
    runtime, _ = _runtime(tmp_path, provider=provider)
    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=_definition(),
        assignment=_assignment(authority),
        authority=authority,
    )
    assert receipt.status is DigitalTwinExecutionStatus.FAILED
    assert receipt.failure_code == "BOUNDED_EXECUTION_FAILURE"
    assert "other-execution" not in json.dumps(receipt.__dict__, default=str)


def test_provider_failure_is_sanitized_and_terminal(tmp_path: Path) -> None:
    provider = _provider()

    def explode(_request, _tools):
        raise RuntimeError("password=hunter2 token=secret-value")

    provider.execute = explode
    authority = _authority()
    runtime, _ = _runtime(tmp_path, provider=provider)
    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=_definition(),
        assignment=_assignment(authority),
        authority=authority,
    )
    serialized = json.dumps(receipt.__dict__, default=str)
    assert receipt.status is DigitalTwinExecutionStatus.FAILED
    assert receipt.failure_code == "INVALID_PROVIDER_RESULT"
    assert "hunter2" not in serialized
    assert "secret-value" not in serialized


def test_authority_expiry_during_provider_execution_fails_closed(tmp_path: Path) -> None:
    before_expiry = NOW + timedelta(minutes=2)
    after_expiry = NOW + timedelta(hours=2)
    observed_times = iter(
        (
            before_expiry,
            before_expiry,
            before_expiry,
            before_expiry,
            after_expiry,
            after_expiry,
        )
    )
    authority = _authority()
    runtime, provider = _runtime(tmp_path, clock=lambda: next(observed_times))
    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=_definition(),
        assignment=_assignment(authority),
        authority=authority,
    )
    assert provider.execution_count == 1
    assert receipt.status is DigitalTwinExecutionStatus.FAILED
    assert receipt.failure_code == "AUTHORITY_POLICY_FAILURE"
    assert len(receipt.tool_calls) == 1
    assert receipt.tool_calls[0].outcome is ToolCallOutcome.SUCCEEDED


def test_receipt_cannot_reopen_without_its_exact_intent(tmp_path: Path) -> None:
    authority = _authority()
    assignment = _assignment(authority)
    runtime, provider = _runtime(tmp_path)
    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=_definition(),
        assignment=assignment,
        authority=authority,
    )
    intent_path = (
        tmp_path
        / "digital-twin-state"
        / assignment.tenant_id
        / receipt.execution_id
        / "execution-intent-v1.json"
    )
    intent_path.unlink()
    with pytest.raises(DigitalTwinExecutionError, match="without its execution intent"):
        runtime.execute(
            execution_id="execution-day22-1",
            twin=_definition(),
            assignment=assignment,
            authority=authority,
        )
    assert provider.execution_count == 1


def test_live_provider_requires_both_grant_and_operator_enablement(tmp_path: Path) -> None:
    provider = _provider()
    provider.requires_live_authorization = True
    authority = _authority()
    runtime, _ = _runtime(tmp_path, provider=provider)
    with pytest.raises(DigitalTwinPolicyError, match="authority and operator"):
        runtime.execute(
            execution_id="execution-day22-1",
            twin=_definition(),
            assignment=_assignment(authority),
            authority=authority,
        )
    assert provider.execution_count == 0

    granted = _authority(live_provider_allowed=True)
    runtime, _ = _runtime(
        tmp_path,
        provider=provider,
        allow_live_providers=True,
    )
    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=_definition(),
        assignment=_assignment(granted),
        authority=granted,
    )
    assert receipt.status is DigitalTwinExecutionStatus.SUCCEEDED


def test_sensitive_context_and_mutating_tool_registration_are_rejected() -> None:
    with pytest.raises(ValueError, match="secret-bearing"):
        ContextValue("api_token", "do-not-store")
    with pytest.raises(ValueError, match="secret-bearing"):
        ContextValue("password", "do-not-store")

    tool = _tool()
    object.__setattr__(tool, "read_only", False)
    with pytest.raises(DigitalTwinRegistryError, match="tool is invalid"):
        DigitalTwinToolRegistry((tool,))


def test_store_uses_mode_0600_and_rejects_tamper_symlink_and_unknown_entry(
    tmp_path: Path,
) -> None:
    authority = _authority()
    assignment = _assignment(authority)
    runtime, _ = _runtime(tmp_path)
    receipt = runtime.execute(
        execution_id="execution-day22-1",
        twin=_definition(),
        assignment=assignment,
        authority=authority,
    )
    directory = (
        tmp_path
        / "digital-twin-state"
        / assignment.tenant_id
        / receipt.execution_id
    )
    intent_path = directory / "execution-intent-v1.json"
    receipt_path = directory / "execution-receipt-v1.json"
    assert stat.S_IMODE(intent_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    store = FileDigitalTwinExecutionStore(tmp_path / "digital-twin-state")

    original = receipt_path.read_text(encoding="utf-8")
    receipt_path.write_text(original.replace("SUCCEEDED", "FAILED"), encoding="utf-8")
    os.chmod(receipt_path, 0o600)
    with pytest.raises(DigitalTwinStoreError, match="corrupt"):
        store.load_receipt(assignment.tenant_id, receipt.execution_id)

    receipt_path.unlink()
    receipt_path.symlink_to(intent_path)
    with pytest.raises(DigitalTwinStoreError, match="unsafe"):
        store.load_receipt(assignment.tenant_id, receipt.execution_id)

    receipt_path.unlink()
    (directory / "unknown.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DigitalTwinStoreError, match="not closed"):
        store.load_intent(assignment.tenant_id, receipt.execution_id)


def test_provider_result_model_rejects_failed_result_without_code() -> None:
    with pytest.raises(ValueError, match="failure code"):
        ProviderExecutionResult(
            "execution-day22-1",
            "deterministic-day22",
            "a" * 64,
            DigitalTwinExecutionStatus.FAILED,
            "failed",
            (),
        )
