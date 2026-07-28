"""Resolve uncertain provider outcomes idempotently."""

from runtime.outbox.models import OutboxStatus, ReconciliationState


class ReconciliationWorker:
    def __init__(
        self, worker_id, repository, providers,
        result_application, *, clock, event_publisher=None,
    ):
        self.worker_id = worker_id
        self.repository = repository
        self.providers = providers
        self.result_application = result_application
        self.clock = clock
        self.event_publisher = event_publisher

    def run_one(self):
        claim = self.repository.claim_reconciliation(self.worker_id)
        if claim is None: return None
        operation = self.repository.get_operation(claim.operation_id)
        self._emit("OUTBOX_RECONCILIATION_STARTED", operation)
        provider = self.providers.get(operation.provider_id)
        result = provider.reconcile(operation.idempotency_key)
        from runtime.operations.handlers import (
            ProviderDispatchResult,
            ProviderReconciliationStatus,
        )
        if isinstance(result, ProviderDispatchResult):
            dispatch_result = result
            status = ProviderReconciliationStatus.SUCCEEDED
        else:
            status = result.status
            dispatch_result = result.dispatch_result
        if status == ProviderReconciliationStatus.NOT_EXECUTED:
            operation.reconciliation_state = ReconciliationState.RESOLVED
            self.repository.release_claim(claim)
            return operation
        if status == ProviderReconciliationStatus.IN_PROGRESS:
            return self.repository.mark_reconciliation_required(
                claim, "PROVIDER_IN_PROGRESS"
            )
        if status in {
            ProviderReconciliationStatus.FAILED,
            ProviderReconciliationStatus.UNVERIFIABLE,
        }:
            operation.reconciliation_state = ReconciliationState.UNVERIFIABLE
            result = self.repository.mark_dead_letter(
                claim,
                (
                    "Provider confirmed failure"
                    if status == ProviderReconciliationStatus.FAILED
                    else "Provider outcome unverifiable"
                ),
            )
            self._emit("OUTBOX_RECONCILIATION_FAILED", operation)
            return result
        self.result_application.apply(operation, dispatch_result)
        completed = self.repository.mark_succeeded(
            claim, dispatch_result.result_reference
        )
        self._emit("OUTBOX_RECONCILIATION_SUCCEEDED", operation)
        return completed

    def _emit(self, event_name, operation):
        if self.event_publisher:
            from runtime.events.types import EventType
            self.event_publisher.publish(
                EventType(event_name), "outbox-operation",
                operation.operation_id, {"status": operation.status.value},
                correlation_id=operation.correlation_id,
                causation_id=operation.causation_id,
            )
