"""Explicit deterministic outbox worker."""

from contextlib import nullcontext

from runtime.outbox.models import FailureCategory


class OutboxWorker:
    def __init__(
        self,
        worker_id,
        repository,
        handlers,
        providers,
        result_application,
        retry_policy,
        *,
        clock,
        claim_ttl_seconds=30,
        event_publisher=None,
        result_guard=None,
    ):
        self.worker_id = worker_id
        self.repository = repository
        self.handlers = handlers
        self.providers = providers
        self.result_application = result_application
        self.retry_policy = retry_policy
        self.clock = clock
        self.claim_ttl_seconds = claim_ttl_seconds
        self.event_publisher = event_publisher
        self.result_guard = result_guard
        self.stopped = False
        self.dispatch_count = 0

    def run_one(self):
        if self.stopped: return None
        claim = self.repository.claim_next(
            self.worker_id, ttl_seconds=self.claim_ttl_seconds
        )
        if claim is None: return None
        operation = self.repository.get_operation(claim.operation_id)
        self._emit("OUTBOX_OPERATION_CLAIMED", operation)
        try:
            handler = self.handlers.get(operation.operation_type)
            provider = self.providers.get(operation.provider_id)
            if not provider.supports(handler.required_capability):
                raise ValueError("Provider capability is incompatible")
            self.repository.mark_dispatching(claim)
            self._emit("OUTBOX_DISPATCH_STARTED", operation)
            self.dispatch_count += 1
            result = handler.dispatch(provider, operation)
            try:
                if self.result_guard is not None:
                    self.result_guard(operation, claim)
                with (
                    self.event_publisher.atomic()
                    if self.event_publisher is not None
                    else nullcontext()
                ):
                    self.result_application.apply(operation, result)
                    completed = self.repository.mark_succeeded(
                        claim, result.result_reference
                    )
                    self._emit("OUTBOX_DISPATCH_SUCCEEDED", operation)
                return completed
            except Exception:
                return self.repository.mark_reconciliation_required(
                    claim, "LOCAL_RESULT_UNCONFIRMED"
                )
        except Exception as error:
            decision = self.retry_policy.classify(
                error, operation, self.clock()
            )
            if decision.category == FailureCategory.RECONCILIATION_REQUIRED:
                result = self.repository.mark_reconciliation_required(
                    claim, decision.code
                )
                self._emit("OUTBOX_RECONCILIATION_REQUIRED", operation)
                return result
            if decision.category in {
                FailureCategory.RETRYABLE_IMMEDIATE,
                FailureCategory.RETRYABLE_BACKOFF,
                FailureCategory.RATE_LIMITED,
            }:
                result = self.repository.mark_retry_wait(
                    claim, decision.category, decision.code,
                    decision.retry_at or self.clock(),
                )
                self._emit(
                    "OUTBOX_OPERATION_DEAD_LETTERED"
                    if result.status.value == "DEAD_LETTER"
                    else "OUTBOX_RETRY_SCHEDULED",
                    operation,
                )
                return result
            operation.failure_category = decision.category
            operation.failure_code = decision.code
            result = self.repository.mark_dead_letter(claim, decision.code)
            self._emit("OUTBOX_OPERATION_DEAD_LETTERED", operation)
            return result

    def run_batch(self, maximum):
        results = []
        for _ in range(maximum):
            result = self.run_one()
            if result is None: break
            results.append(result)
        return tuple(results)

    def stop(self): self.stopped = True

    def _emit(self, event_name, operation):
        if self.event_publisher is None:
            return
        from runtime.events.types import EventType
        self.event_publisher.publish(
            EventType(event_name),
            "outbox-operation",
            operation.operation_id,
            {
                "status": operation.status.value,
                "attempt_count": operation.attempt_count,
            },
            correlation_id=operation.correlation_id,
            causation_id=operation.causation_id,
        )
