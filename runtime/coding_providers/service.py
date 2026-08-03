"""Durable provider orchestration outside approval and repository effects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from runtime.coding_providers.errors import (
    ProviderPolicyError,
    ProviderReconciliationError,
    ProviderStateError,
)
from runtime.coding_providers.models import (
    ProviderCapability,
    CancellationEffect,
    CancellationEffectState,
    ObservedFile,
    ProviderOperation,
    ProviderOperationState,
    ProviderResponseReceipt,
    PatchEffect,
    PatchEffectState,
    PatchManifest,
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
            context.context_digest, maximum_output_bytes,
            ProviderOperationState.PREPARED,
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
        if operation.provider_id in {"openai-codex", "codex-cli"}:
            try:
                receipt = self.store.load_receipt(project_id, operation_id)
                result = self.store.load_result(project_id, operation_id)
            except ProviderStateError:
                self._reconciliation(
                    in_progress,
                    "Live provider returned without a durable response receipt")
            self._verify_receipt(
                in_progress, receipt, result,
                hashlib.sha256(_serialized_result(result)).hexdigest())
            if receipt.provider_task_id != task_id:
                self._reconciliation(
                    in_progress, "Live response receipt task ID differs")
        else:
            matches = provider.reconcile_task(
                operation.provider_idempotency_key, task_id)
            if tuple(matches) != (task_id,):
                self._reconciliation(
                    in_progress, "Submitted provider task cannot be exactly verified")
            self._verify_provider_request(
                in_progress, provider.get_task_identity(task_id))
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
                event, message=redact(
                    event.message, limit=min(2_000, operation.maximum_output_bytes)),
                metadata=tuple((key[:100], redact(value, limit=500))
                               for key, value in event.metadata[:20]))
            if len(json.dumps(
                    asdict(sanitized), default=str).encode()
                   ) > operation.maximum_output_bytes:
                self._reconciliation(
                    operation, "Provider progress exceeds approved output limit")
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
        serialized = _serialized_result(result)
        content_bytes = sum(
            len((item.content or "").encode("utf-8"))
            for item in result.file_operations)
        if (
            result.provider_task_id != operation.provider_task_id
            or result.external_task_id != operation.external_task_id
            or result.workspace_id != operation.workspace_id
            or result.branch != operation.branch
            or result.status != ProviderResultStatus.SUCCEEDED
            or len(serialized) > operation.maximum_output_bytes
            or content_bytes > operation.maximum_output_bytes
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
        response_digest = hashlib.sha256(serialized).hexdigest()
        if operation.provider_id in {"openai-codex", "codex-cli"}:
            receipt = self.store.load_receipt(project_id, operation_id)
            self._verify_receipt(operation, receipt, result, response_digest)
        else:
            receipt = ProviderResponseReceipt(
                operation.provider_operation_id, result.provider_task_id,
                result.external_task_id, operation.provider_id, operation.project_id,
                operation.execution_plan_id, operation.plan_version,
                operation.managed_task_id, operation.workspace_id, operation.branch,
                operation.request_digest, operation.context_digest,
                operation.provider_idempotency_key, response_digest,
                datetime.now(timezone.utc), result.usage)
            self.store.save_result(project_id, operation_id, result)
            self.store.save_receipt(receipt)
        self.store.save_operation(replace(
            operation, result_reference=operation_id, usage=result.usage,
            updated_at=datetime.now(timezone.utc)))
        return result

    def apply_and_accept(
        self, project_id, operation_id, *, workspace_path, task, policy_id,
    ):
        operation = self.store.load_operation(project_id, operation_id)
        self._require_state(operation, {ProviderOperationState.RESULT_AVAILABLE})
        result = self.store.load_result(project_id, operation_id)
        receipt = self.store.load_receipt(project_id, operation_id)
        result_digest = hashlib.sha256(_serialized_result(result)).hexdigest()
        if operation.result_reference != operation_id:
            self._reconciliation(
                operation, "Stored provider result reference is invalid")
        self._verify_receipt(operation, receipt, result, result_digest)
        if any(
            effect.provider_operation_id != operation_id
            and effect.provider_result_digest == result_digest
            and effect.state == PatchEffectState.ACCEPTED
            for effect in self.store.list_patch_effects(project_id)
        ):
            raise ProviderPolicyError(
                "Provider result was already accepted under another operation")
        policy = self.change_policies[policy_id]
        if self.git_provider_factory is None:
            raise ProviderStateError("Git inspection is not configured")
        git = self.git_provider_factory(operation.workspace_id)
        before = git.status(workspace_path)
        pre_commit = git.current_commit(workspace_path)
        if before.branch != operation.branch:
            raise ProviderPolicyError("Workspace branch changed before patch application")
        operations_digest = _digest(
            tuple(asdict(item) for item in result.file_operations))
        effect_id = f"patch-{operation.provider_operation_id}"
        expected_paths = tuple(item.path for item in result.file_operations)
        try:
            effect = self.store.load_patch_effect(project_id, effect_id)
            if (
                effect.provider_operation_id != operation_id
                or effect.execution_plan_id != operation.execution_plan_id
                or effect.plan_version != operation.plan_version
                or effect.workspace_id != operation.workspace_id
                or effect.branch != operation.branch
                or effect.request_digest != operation.request_digest
                or effect.context_digest != operation.context_digest
                or effect.provider_result_digest != result_digest
                or effect.file_operations_digest != operations_digest
                or effect.expected_changed_paths != expected_paths
                or effect.pre_application_commit_sha != pre_commit
                or not effect.pre_application_clean
            ):
                self._patch_reconciliation(
                    effect, "Patch effect identity differs from accepted result")
        except ProviderStateError as error:
            if "not found" not in str(error):
                raise
            if not before.clean:
                raise ProviderPolicyError(
                    "Workspace changed before patch application")
            now = datetime.now(timezone.utc)
            effect = PatchEffect(
                effect_id, project_id, operation_id, operation.execution_plan_id,
                operation.plan_version, operation.workspace_id, operation.branch,
                operation.request_digest, operation.context_digest, result_digest,
                operations_digest, expected_paths, pre_commit, before.clean,
                PatchEffectState.PREPARED, created_at=now, updated_at=now)
            self.store.save_patch_effect(effect)
        if effect.state != PatchEffectState.PREPARED:
            return self._reconcile_patch(
                operation, effect, result, workspace_path, git)
        if not before.clean:
            raise ProviderPolicyError("Workspace changed after patch intent preparation")
        effect = replace(
            effect, state=PatchEffectState.STAGING,
            updated_at=datetime.now(timezone.utc))
        self.store.save_patch_effect(effect)

        def completed(path):
            current = self.store.load_patch_effect(project_id, effect_id)
            self.store.save_patch_effect(replace(
                current, state=PatchEffectState.APPLYING,
                completed_paths=current.completed_paths + (path,),
                updated_at=datetime.now(timezone.utc)))

        try:
            applied = self.patch_applier.apply_staged(
                workspace_path, result.file_operations, task=task, policy=policy,
                effect_id=effect_id, completed_callback=completed)
        except Exception as error:
            current = self.store.load_patch_effect(project_id, effect_id)
            self.store.save_patch_effect(replace(
                current, state=PatchEffectState.UNCERTAIN,
                failure_details=redact(str(error)),
                updated_at=datetime.now(timezone.utc)))
            raise
        effect = self.store.load_patch_effect(project_id, effect_id)
        effect = replace(
            effect, state=PatchEffectState.APPLIED,
            updated_at=datetime.now(timezone.utc))
        self.store.save_patch_effect(effect)
        observed = git.status(workspace_path)
        if set(observed.changed_paths) != set(applied):
            self._patch_reconciliation(
                effect, "Observed Git changes differ from validated patches")
        manifest = self._manifest(
            operation, workspace_path, observed, git, result)
        verified = replace(
            effect, state=PatchEffectState.VERIFIED, manifest=manifest,
            updated_at=datetime.now(timezone.utc))
        self.store.save_patch_effect(verified)
        self.store.save_patch_effect(replace(
            verified, state=PatchEffectState.ACCEPTED,
            updated_at=datetime.now(timezone.utc)))
        accepted = replace(
            operation, state=ProviderOperationState.RESULT_ACCEPTED,
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(accepted)
        return accepted, manifest

    def cancel(self, project_id, operation_id, *, actor, reason):
        if not actor or not reason:
            raise ProviderPolicyError("Cancellation requires actor and reason")
        operation = self.store.load_operation(project_id, operation_id)
        self._require_state(operation, {
            ProviderOperationState.SUBMITTED, ProviderOperationState.RUNNING})
        provider = self.registry.get(operation.provider_id)
        if ProviderCapability.CANCELLATION not in provider.capabilities():
            raise ProviderPolicyError("Provider does not support cancellation")
        now = datetime.now(timezone.utc)
        cancellation = CancellationEffect(
            f"cancel-{operation_id}", project_id, operation_id,
            operation.provider_id, operation.provider_task_id, actor,
            redact(reason), CancellationEffectState.CANCELLATION_PREPARED,
            now, now)
        self.store.save_cancellation(cancellation)
        requested = replace(
            operation, state=ProviderOperationState.CANCELLATION_REQUESTED,
            reconciliation_details=redact(f"{actor}: {reason}"),
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(requested)
        in_progress = replace(
            cancellation, state=CancellationEffectState.CANCELLATION_IN_PROGRESS,
            updated_at=datetime.now(timezone.utc))
        self.store.save_cancellation(in_progress)
        try:
            provider.cancel_task(operation.provider_task_id)
        except Exception as error:
            self.store.save_cancellation(replace(
                in_progress,
                state=CancellationEffectState.CANCELLATION_UNCERTAIN,
                details=redact(str(error)), updated_at=datetime.now(timezone.utc)))
            raise
        return self.reconcile_cancellation(project_id, operation_id)

    def reconcile(self, project_id, operation_id):
        operation = self.store.load_operation(project_id, operation_id)
        try:
            receipt = self.store.load_receipt(project_id, operation_id)
            result = self.store.load_result(project_id, operation_id)
            digest = hashlib.sha256(_serialized_result(result)).hexdigest()
            self._verify_receipt(operation, receipt, result, digest)
            reconciled = replace(
                operation, provider_task_id=receipt.provider_task_id,
                result_reference=operation_id,
                state=ProviderOperationState.RESULT_AVAILABLE,
                reconciliation_details="Durable response receipt reconciled",
                updated_at=datetime.now(timezone.utc))
            self.store.save_operation(reconciled)
            return reconciled
        except ProviderStateError as error:
            if "not found" not in str(error):
                raise
        if operation.provider_id == "openai-codex":
            self._reconciliation(
                operation,
                "Synchronous live response has no durable receipt or remote lookup")
        provider = self.registry.get(operation.provider_id)
        matches = tuple(provider.reconcile_task(
            operation.provider_idempotency_key, operation.provider_task_id))
        if len(matches) != 1:
            self._reconciliation(
                operation, "Provider reconciliation is missing or ambiguous")
        task_id = matches[0]
        self._verify_provider_request(
            operation, provider.get_task_identity(task_id))
        reconciled = replace(
            operation, provider_task_id=task_id,
            state=ProviderOperationState.SUBMITTED,
            reconciliation_details="Exact provider task reconciled",
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(reconciled)
        return reconciled

    def reconcile_cancellation(self, project_id, operation_id):
        operation = self.store.load_operation(project_id, operation_id)
        effect = self.store.load_cancellation(
            project_id, f"cancel-{operation_id}")
        provider = self.registry.get(operation.provider_id)
        try:
            status = provider.get_task_status(effect.provider_task_id)
        except Exception as error:
            self.store.save_cancellation(replace(
                effect,
                state=CancellationEffectState.CANCELLATION_RECONCILIATION_REQUIRED,
                details=redact(str(error)), updated_at=datetime.now(timezone.utc)))
            raise ProviderReconciliationError(
                "Cancellation status cannot be determined") from error
        if status == ProviderResultStatus.CANCELLED:
            self.store.save_cancellation(replace(
                effect, state=CancellationEffectState.CANCELLATION_CONFIRMED,
                updated_at=datetime.now(timezone.utc)))
            cancelled = replace(
                operation, state=ProviderOperationState.CANCELLED,
                updated_at=datetime.now(timezone.utc))
            self.store.save_operation(cancelled)
            return cancelled
        if status == ProviderResultStatus.SUCCEEDED:
            actual = replace(
                operation, state=ProviderOperationState.RESULT_AVAILABLE,
                reconciliation_details="Provider completed before cancellation",
                updated_at=datetime.now(timezone.utc))
            self.store.save_operation(actual)
            return actual
        self.store.save_cancellation(replace(
            effect,
            state=CancellationEffectState.CANCELLATION_RECONCILIATION_REQUIRED,
            details=f"Provider status is {status.value}",
            updated_at=datetime.now(timezone.utc)))
        raise ProviderReconciliationError("Cancellation is not confirmed")

    def _reconciliation(self, operation, details):
        self.store.save_operation(replace(
            operation, state=ProviderOperationState.RECONCILIATION_REQUIRED,
            reconciliation_details=redact(details),
            updated_at=datetime.now(timezone.utc)))
        raise ProviderReconciliationError(details)

    def _verify_receipt(self, operation, receipt, result, result_digest):
        if (
            receipt.provider_id != operation.provider_id
            or receipt.provider_operation_id != operation.provider_operation_id
            or receipt.project_id != operation.project_id
            or receipt.execution_plan_id != operation.execution_plan_id
            or receipt.plan_version != operation.plan_version
            or receipt.managed_task_id != operation.managed_task_id
            or receipt.external_task_id != operation.external_task_id
            or receipt.workspace_id != operation.workspace_id
            or receipt.branch != operation.branch
            or receipt.request_digest != operation.request_digest
            or receipt.context_digest != operation.context_digest
            or receipt.idempotency_key != operation.provider_idempotency_key
            or receipt.provider_task_id != result.provider_task_id
            or receipt.response_digest != result_digest
        ):
            self._reconciliation(
                operation, "Durable provider receipt identity is invalid")

    def _verify_provider_request(self, operation, request):
        if (
            request.provider_operation_id != operation.provider_operation_id
            or request.project_id != operation.project_id
            or request.execution_plan_id != operation.execution_plan_id
            or request.plan_version != operation.plan_version
            or request.managed_task_id != operation.managed_task_id
            or request.external_task_id != operation.external_task_id
            or request.workspace_id != operation.workspace_id
            or request.branch != operation.branch
            or request.request_digest != operation.request_digest
            or request.context_digest != operation.context_digest
            or request.provider_idempotency_key
            != operation.provider_idempotency_key
        ):
            self._reconciliation(
                operation, "Recovered provider task identity is invalid")

    def _manifest(self, operation, workspace_path, observed, git, result):
        root = Path(workspace_path)
        files = tuple(ObservedFile(
            path, hashlib.sha256((root / path).read_bytes()).hexdigest())
            for path in sorted(observed.changed_paths) if (root / path).is_file())
        diff = git.diff(workspace_path)
        if hasattr(git, "diff_numstat"):
            additions, deletions = git.diff_numstat(workspace_path)
        else:
            additions = sum(
                (item.content or "").count("\n") + 1
                for item in result.file_operations if item.content is not None)
            deletions = 0
        payload = {
            "provider_operation_id": operation.provider_operation_id,
            "changed_paths": tuple(sorted(observed.changed_paths)),
            "files": tuple((item.path, item.content_digest) for item in files),
            "additions": additions, "deletions": deletions,
            "git_diff_digest": hashlib.sha256(diff.encode()).hexdigest(),
            "workspace_status": "DIRTY",
        }
        return PatchManifest(
            operation.provider_operation_id, payload["changed_paths"], files,
            additions, deletions, payload["git_diff_digest"], "DIRTY",
            _digest(payload), datetime.now(timezone.utc))

    def _reconcile_patch(self, operation, effect, result, workspace_path, git):
        root = Path(workspace_path)
        expected = {
            item.path: hashlib.sha256((item.content or "").encode()).hexdigest()
            for item in result.file_operations if item.content is not None}
        matching = {
            path for path, digest in expected.items()
            if (root / path).is_file()
            and hashlib.sha256((root / path).read_bytes()).hexdigest() == digest}
        if not matching:
            if effect.completed_paths:
                self._patch_reconciliation(
                    effect, "Recorded patch replacements are missing")
            reset = replace(
                effect, state=PatchEffectState.PREPARED, completed_paths=(),
                updated_at=datetime.now(timezone.utc))
            self.store.save_patch_effect(reset)
            raise ProviderReconciliationError(
                "No patch operations applied; explicit retry is required")
        if matching != set(expected):
            self._patch_reconciliation(
                effect, "Patch application is partial or divergent")
        observed = git.status(workspace_path)
        if set(observed.changed_paths) != set(effect.expected_changed_paths):
            self._patch_reconciliation(
                effect, "Fully applied patch has divergent Git state")
        manifest = self._manifest(
            operation, workspace_path, observed, git, result)
        if (
            effect.manifest is not None
            and (
                _manifest_digest(effect.manifest)
                != effect.manifest.manifest_digest
                or effect.manifest.manifest_digest != manifest.manifest_digest
            )
        ):
            self._patch_reconciliation(
                effect, "Accepted patch manifest is corrupted or divergent")
        self.store.save_patch_effect(replace(
            effect, state=PatchEffectState.ACCEPTED, manifest=manifest,
            completed_paths=effect.expected_changed_paths,
            updated_at=datetime.now(timezone.utc)))
        accepted = replace(
            operation, state=ProviderOperationState.RESULT_ACCEPTED,
            updated_at=datetime.now(timezone.utc))
        self.store.save_operation(accepted)
        return accepted, manifest

    def _patch_reconciliation(self, effect, details):
        self.store.save_patch_effect(replace(
            effect, state=PatchEffectState.RECONCILIATION_REQUIRED,
            failure_details=redact(details),
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


def _serialized_result(result):
    return json.dumps(
        asdict(result), sort_keys=True, separators=(",", ":"),
        default=str).encode("utf-8")


def _manifest_digest(manifest):
    return _digest({
        "provider_operation_id": manifest.provider_operation_id,
        "changed_paths": manifest.changed_paths,
        "files": tuple((item.path, item.content_digest) for item in manifest.files),
        "additions": manifest.additions,
        "deletions": manifest.deletions,
        "git_diff_digest": manifest.git_diff_digest,
        "workspace_status": manifest.workspace_status,
    })
