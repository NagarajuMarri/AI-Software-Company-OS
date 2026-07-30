"""Offline idempotent provider used by tests and the managed pilot."""

from dataclasses import replace
from datetime import datetime, timezone

from runtime.coding_providers.errors import ProviderStateError
from runtime.coding_providers.models import (
    FileOperation,
    FileOperationKind,
    ProviderCapability,
    ProviderProgressEvent,
    ProviderResultStatus,
    ProviderTaskResult,
)


class DeterministicCodingProvider:
    provider_id = "deterministic"

    def __init__(self, *, file_operations=(), enabled=True):
        self.enabled = enabled
        self.file_operations = tuple(file_operations)
        self._tasks = {}
        self._keys = {}

    def validate_configuration(self):
        if not self.enabled:
            raise ProviderStateError("Deterministic provider is disabled")

    def capabilities(self):
        return tuple(ProviderCapability)

    def submit_task(self, request):
        if request.provider_idempotency_key in self._keys:
            return self._keys[request.provider_idempotency_key]
        identifier = f"deterministic-{len(self._tasks)+1}"
        now = datetime.now(timezone.utc)
        progress = (
            ProviderProgressEvent(request.provider_operation_id, 1, "ACCEPTED",
                                  "Bounded task accepted", now),
            ProviderProgressEvent(request.provider_operation_id, 2, "COMPLETED",
                                  "Structured result available", now),
        )
        operations = self.file_operations or (
            FileOperation(FileOperationKind.CREATE, "provider-result.txt",
                          "deterministic provider result\n"),)
        result = ProviderTaskResult(
            identifier, request.external_task_id, request.workspace_id,
            request.branch, ProviderResultStatus.SUCCEEDED,
            "Deterministic provider completed", operations,
            ("generated bounded patches",), ("provider-result",), (), (),
            (1, 2), False)
        self._tasks[identifier] = (request, progress, result)
        self._keys[request.provider_idempotency_key] = identifier
        return identifier

    def get_task_status(self, provider_task_id):
        return self.get_task_result(provider_task_id).status

    def get_task_progress(self, provider_task_id):
        return self._require(provider_task_id)[1]

    def get_task_result(self, provider_task_id):
        return self._require(provider_task_id)[2]

    def cancel_task(self, provider_task_id):
        request, progress, result = self._require(provider_task_id)
        self._tasks[provider_task_id] = (
            request, progress, replace(
                result, status=ProviderResultStatus.CANCELLED,
                summary="Cancelled", file_operations=(), retryable=False))

    def reconcile_task(self, idempotency_key, provider_task_id=None):
        match = self._keys.get(idempotency_key)
        if provider_task_id is not None and match != provider_task_id:
            return ()
        return (match,) if match else ()

    def _require(self, identifier):
        try:
            return self._tasks[identifier]
        except KeyError as error:
            raise ProviderStateError("Provider task was not found") from error
