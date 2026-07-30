"""Durable provider orchestration outside approval and repository effects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone

from runtime.coding_providers.errors import (
    ProviderPolicyError,
    ProviderReconciliationError,
    ProviderStateError,
)
from runtime.coding_providers.models import (
    ProviderCapability,
    ProviderOperation,
    ProviderOperationState,
    ProviderProgressEvent,
    ProviderResultStatus,
    ProviderTaskRequest,
)
from runtime.coding_providers.redaction import redact


class CodingProviderService:
    def __init__(
        self, registry, store, context_builder, patch_applier,
        *, change_policies=(), git_provider_factory=None,
    ):
        self.registry = registry
        self.store = store
        self.context_builder = context_builder
        self.patch_applier = patch_applier
        self.change_policies = {item.policy_id: item for item in change_policies}
        self.git_provider_factory = git_provider_factory

    def prepare(
        self, *, plan, task, coding_request, workspace_path, provider_id,
        attempt=1, evidence=(), maximum_output_bytes=128_000,
        maximum_attempts=1,
    ):
        if not 1 <= attempt <= maximum_attempts:
            raise ProviderPolicyError("Provider attempt limit exceeded")
        provider = self.registry.get(
            provider_id,
            (ProviderCapability.CODE_MODIFICATION,
             ProviderCapability.IDEMPOTENT_SUBMISSION))
        context = self.context_builder.build(
            plan=plan, task=task, request=coding_request,
            workspace_path=workspace_path, evidence=evidence)
        request_payload = {
            "external_task_id": coding_request.external_task_id,
            "project_id": plan.project_id,
            "execution_plan_id": plan.execution_plan_id,
            "plan_version": plan.version,
            "managed_task_id": task.project_task_id,
            "workspace_id": plan.workspace_identity,
            "branch": plan.feature_branch,
            "context_digest": context.context_digest,
            "attempt": attempt,
        }
        digest = _digest(request_payload)
        key = _digest({
            "project": plan.project_id, "plan": plan.execution_plan_id,
            "version": plan.version, "task": task.project_task_id,
            "attempt": attempt, "request_digest": digest})
        operation_id = (
            f"provider-{plan.execution_plan_id}-{task.project_task_id}-{attempt}")
        request = ProviderTaskRequest(
            coding_request.external_task_id, operation_id, key, plan.project_id,
            plan.execution_plan_id, plan.version, task.project_task_id,
            plan.workspace_identity, plan.feature_branch, digest,
            context.context_digest, context, coding_request.timeout_seconds,
            maximum_output_bytes)
        try:
            existing = self.store.load_operation(plan.project_id, operation_id)
            if (
                existing.request_digest != digest
                or existing.context_digest != context.context_digest
                or existing.provider_id != provider_id
                or existing.workspace_id != plan.workspace_identity
                or existing.branch != plan.feature_branch
                or existing.plan_version != plan.version
            ):
                raise ProviderReconciliationError(
                    "Prepared provider identity differs from durable operation")
            return existing, request
        except ProviderStateError as error:
            if "not found" not in str(error):
                raise
        now = datetime.now(timezone.utc)
        operation = ProviderOperation(
            operation_id, plan.execution_plan_id, plan.version, plan.project_id,
            task.project_task_id, coding_request.external_task_id, provider_id,
            key, attempt, plan.workspace_identity, plan.feature_branch, digest,
            context.context_digest, ProviderOperationState.PREPARED,
            created_at=now, updated_at=now)
        self.store.save_operation(operation)
        return operation, request

    def submit(self, project_id, operation_id, request, *, allow_live_provider=False):
        operation = self.store.load_operation(project_id, operation_id)
        self._require_state(operation, {
            ProviderOperationState.PREPARED,
            ProviderOperationState.UNCERTAIN,
            ProviderOperationState.SUBMITTED})
        provider = self.registry.get(operation.provider_id)
        if operation.provider_id != "deterministic" and not allow_live_provider:
            raise ProviderPolicyError("--allow-live-provider is required")
        if operation.state in {
            ProviderOperationState.UNCERTAIN, ProviderOperationState.SUBMITTED
        }:
            return self.reconcile(project_id, operation_id)
        in_progress = replace(
            operation, state=ProviderOperationState.SUBMISSION_IN_PROGRESS,
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(in_progress)
        try:
            task_id = provider.submit_task(request)
        except Exception as error:
            self.store.save_operation(replace(
                in_progress, state=ProviderOperationState.UNCERTAIN,
                failure_classification=type(error).__name__,
                reconciliation_details=redact(str(error)),
                updated_at=datetime.now(timezone.utc)))
            raise
        matches = provider.reconcile_task(
            operation.provider_idempotency_key, task_id)
        if tuple(matches) != (task_id,):
            self._reconciliation(
                in_progress, "Submitted provider task cannot be exactly verified")
        submitted = replace(
            in_progress, provider_task_id=task_id,
            state=ProviderOperationState.SUBMITTED,
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(submitted)
        return submitted

    def poll(self, project_id, operation_id):
        operation = self.store.load_operation(project_id, operation_id)
        self._require_state(operation, {
            ProviderOperationState.SUBMITTED, ProviderOperationState.RUNNING,
            ProviderOperationState.RESULT_AVAILABLE})
        provider = self.registry.get(operation.provider_id)
        if not operation.provider_task_id:
            raise ProviderReconciliationError("Provider task ID is unknown")
        for event in provider.get_task_progress(operation.provider_task_id):
            if event.provider_operation_id != operation_id:
                self._reconciliation(operation, "Progress belongs to another operation")
            sanitized = replace(
                event, message=redact(event.message),
                metadata=tuple((key[:100], redact(value, limit=500))
                               for key, value in event.metadata[:20]))
            self.store.append_progress(project_id, sanitized)
        events = self.store.load_progress(project_id, operation_id)
        status = provider.get_task_status(operation.provider_task_id)
        state = {
            ProviderResultStatus.SUCCEEDED: ProviderOperationState.RESULT_AVAILABLE,
            ProviderResultStatus.FAILED_RETRYABLE: ProviderOperationState.FAILED_RETRYABLE,
            ProviderResultStatus.FAILED_PERMANENT: ProviderOperationState.FAILED_PERMANENT,
            ProviderResultStatus.TIMED_OUT: ProviderOperationState.TIMED_OUT,
            ProviderResultStatus.CANCELLED: ProviderOperationState.CANCELLED,
        }[status]
        updated = replace(
            operation, state=state, progress_cursor=len(events),
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(updated)
        return updated

    def result(
        self, project_id, operation_id, *, token_budget=None, cost_budget=None,
    ):
        operation = self.store.load_operation(project_id, operation_id)
        self._require_state(operation, {ProviderOperationState.RESULT_AVAILABLE})
        provider = self.registry.get(operation.provider_id)
        result = provider.get_task_result(operation.provider_task_id)
        if (
            result.provider_task_id != operation.provider_task_id
            or result.external_task_id != operation.external_task_id
            or result.workspace_id != operation.workspace_id
            or result.branch != operation.branch
            or result.status != ProviderResultStatus.SUCCEEDED
            or len(json.dumps(asdict(result), default=str).encode()) > 128_000
        ):
            self._reconciliation(operation, "Provider result identity or size is invalid")
        total_units = (
            (result.usage.input_units or 0) + (result.usage.output_units or 0))
        if token_budget is not None and total_units > token_budget:
            raise ProviderPolicyError("Provider token budget exceeded")
        if (
            cost_budget is not None
            and result.usage.reported_cost is not None
            and result.usage.reported_cost > cost_budget
        ):
            raise ProviderPolicyError("Provider cost budget exceeded")
        self.store.save_result(project_id, operation_id, result)
        self.store.save_operation(replace(
            operation, result_reference=operation_id, usage=result.usage,
            updated_at=datetime.now(timezone.utc)))
        return result

    def apply_and_accept(
        self, project_id, operation_id, *, workspace_path, task, policy_id,
    ):
        operation = self.store.load_operation(project_id, operation_id)
        result = self.store.load_result(project_id, operation_id)
        policy = self.change_policies[policy_id]
        if self.git_provider_factory is None:
            raise ProviderStateError("Git inspection is not configured")
        git = self.git_provider_factory(operation.workspace_id)
        before = git.status(workspace_path)
        if not before.clean or before.branch != operation.branch:
            raise ProviderPolicyError("Workspace changed before patch application")
        applied = self.patch_applier.apply(
            workspace_path, result.file_operations, task=task, policy=policy)
        observed = git.status(workspace_path)
        if set(observed.changed_paths) != set(applied):
            self._reconciliation(
                operation, "Observed Git changes differ from validated patches")
        accepted = replace(
            operation, state=ProviderOperationState.RESULT_ACCEPTED,
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(accepted)
        return accepted, observed

    def cancel(self, project_id, operation_id, *, actor, reason):
        if not actor or not reason:
            raise ProviderPolicyError("Cancellation requires actor and reason")
        operation = self.store.load_operation(project_id, operation_id)
        self._require_state(operation, {
            ProviderOperationState.SUBMITTED, ProviderOperationState.RUNNING})
        requested = replace(
            operation, state=ProviderOperationState.CANCELLATION_REQUESTED,
            reconciliation_details=redact(f"{actor}: {reason}"),
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(requested)
        self.registry.get(operation.provider_id).cancel_task(
            operation.provider_task_id)
        cancelled = replace(
            requested, state=ProviderOperationState.CANCELLED,
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(cancelled)
        return cancelled

    def reconcile(self, project_id, operation_id):
        operation = self.store.load_operation(project_id, operation_id)
        provider = self.registry.get(operation.provider_id)
        matches = tuple(provider.reconcile_task(
            operation.provider_idempotency_key, operation.provider_task_id))
        if len(matches) != 1:
            self._reconciliation(
                operation, "Provider reconciliation is missing or ambiguous")
        task_id = matches[0]
        reconciled = replace(
            operation, provider_task_id=task_id,
            state=ProviderOperationState.SUBMITTED,
            reconciliation_details="Exact provider task reconciled",
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(reconciled)
        return reconciled

    def _reconciliation(self, operation, details):
        self.store.save_operation(replace(
            operation, state=ProviderOperationState.RECONCILIATION_REQUIRED,
            reconciliation_details=redact(details),
            updated_at=datetime.now(timezone.utc)))
        raise ProviderReconciliationError(details)

    @staticmethod
    def _require_state(operation, states):
        if operation.state not in states:
            raise ProviderStateError(
                f"Provider operation cannot continue from {operation.state.value}")


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
