"""Deterministic in-memory outbox repository."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from runtime.outbox.exceptions import (
    DuplicateOutboxOperationError, IdempotencyConflictError,
    InvalidOutboxTransitionError, OutboxClaimError,
    OutboxClaimExpiredError, OutboxOperationNotFoundError,
    StaleOutboxFencingError,
)
from runtime.outbox.models import (
    FailureCategory, OutboxAttempt, OutboxClaim, OutboxOperation,
    OutboxStatus, ReconciliationState,
)


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class InMemoryOutboxRepository:
    def __init__(self, *, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._operations = {}
        self._attempts = {}
        self._idempotency = {}
        self._provider_pauses = {}
        self._audit = []

    def snapshot_targets(self):
        return [
            self._operations,
            self._attempts,
            self._idempotency,
            self._provider_pauses,
            self._audit,
            *self._operations.values(),
        ]

    def add_operation(self, operation: OutboxOperation):
        if operation.operation_id in self._operations:
            raise DuplicateOutboxOperationError(operation.operation_id)
        existing = self._idempotency.get(operation.idempotency_key)
        fingerprint = operation.request_fingerprint()
        if existing and existing != fingerprint:
            raise IdempotencyConflictError("Idempotency key payload changed")
        if existing:
            raise DuplicateOutboxOperationError("Idempotent operation exists")
        self._operations[operation.operation_id] = operation
        self._idempotency[operation.idempotency_key] = fingerprint
        return operation

    def get_operation(self, operation_id):
        try: return self._operations[operation_id]
        except KeyError as error:
            raise OutboxOperationNotFoundError(operation_id) from error

    def list_operations(self, *, status=None):
        values = self._operations.values()
        if status is not None:
            values = (item for item in values if item.status == status)
        return tuple(sorted(values, key=lambda item: (item.created_at, item.operation_id)))

    def list_pending_operations(self):
        now = self.clock()
        return tuple(item for item in self._eligible(now))

    def list_by_task(self, task_id):
        return tuple(item for item in self.list_operations() if item.task_id == task_id)

    def list_by_aggregate(self, aggregate_id):
        return tuple(item for item in self.list_operations() if item.aggregate_id == aggregate_id)

    def get_by_idempotency_key(self, key):
        return next(
            (item for item in self._operations.values() if item.idempotency_key == key),
            None,
        )

    def claim_next(self, owner_id, *, ttl_seconds=30):
        now = self.clock()
        InMemoryOutboxRepository.recover_expired(self, now)
        eligible = list(self._eligible(now))
        if not eligible: return None
        operation = eligible[0]
        return self._claim(operation, owner_id, now, ttl_seconds)

    def claim_reconciliation(self, owner_id, *, ttl_seconds=30):
        now = self.clock()
        candidates = sorted(
            (
                item for item in self._operations.values()
                if item.status == OutboxStatus.RECONCILIATION_REQUIRED
            ),
            key=lambda item: (
                item.priority, item.available_at, item.created_at,
                item.operation_id,
            ),
        )
        if not candidates: return None
        operation = candidates[0]
        operation.reconciliation_state = ReconciliationState.IN_PROGRESS
        return self._claim(operation, owner_id, now, ttl_seconds)

    def _claim(self, operation, owner_id, now, ttl_seconds):
        token = secrets.token_urlsafe(32)
        operation.status = OutboxStatus.CLAIMED
        operation.claim_owner = owner_id
        operation.claim_token_hash = _hash(token)
        operation.claimed_at = now
        operation.claim_expires_at = now + timedelta(seconds=ttl_seconds)
        operation.fencing_token += 1
        return OutboxClaim(
            operation.operation_id, owner_id, token, now,
            operation.claim_expires_at, operation.fencing_token,
        )

    def renew_claim(self, claim, *, ttl_seconds=30):
        operation = self._validate_claim(claim)
        now = self.clock()
        operation.claim_expires_at = now + timedelta(seconds=ttl_seconds)
        return OutboxClaim(
            claim.operation_id, claim.owner_id, claim.token,
            operation.claimed_at, operation.claim_expires_at,
            claim.fencing_token,
        )

    def release_claim(self, claim):
        operation = self._validate_claim(claim)
        if operation.status != OutboxStatus.CLAIMED:
            raise InvalidOutboxTransitionError("Only claimed operation can release")
        self._clear_claim(operation)
        operation.status = OutboxStatus.PENDING

    def mark_dispatching(self, claim):
        operation = self._validate_claim(claim)
        if operation.status != OutboxStatus.CLAIMED:
            raise InvalidOutboxTransitionError("Operation is not claimed")
        now = self.clock()
        operation.status = OutboxStatus.DISPATCHING
        operation.attempt_count += 1
        operation.first_attempted_at = operation.first_attempted_at or now
        operation.last_attempted_at = now
        self._attempts.setdefault(operation.operation_id, []).append(
            OutboxAttempt(operation.operation_id, operation.attempt_count, now, None, "STARTED")
        )
        return operation

    def mark_succeeded(self, claim, result_reference):
        operation = self._validate_claim(claim)
        if operation.status == OutboxStatus.SUCCEEDED:
            return operation
        if operation.status != OutboxStatus.DISPATCHING and not (
            operation.status == OutboxStatus.CLAIMED
            and operation.reconciliation_state
            == ReconciliationState.IN_PROGRESS
        ):
            raise InvalidOutboxTransitionError("Operation is not dispatching")
        now = self.clock()
        operation.status = OutboxStatus.SUCCEEDED
        operation.completed_at = now
        operation.result_reference = result_reference
        operation.reconciliation_state = ReconciliationState.RESOLVED
        self._finish_attempt(operation, now, "SUCCEEDED")
        self._clear_claim(operation)
        return operation

    def mark_retry_wait(self, claim, category, code, available_at):
        operation = self._validate_claim(claim)
        now = self.clock()
        operation.failure_category = category
        operation.failure_code = code
        if operation.attempt_count >= operation.maximum_attempts:
            return self._dead_letter(
                operation, now, f"Maximum attempts exhausted: {code}"
            )
        operation.status = OutboxStatus.RETRY_WAIT
        operation.available_at = available_at
        operation.retry_after = available_at
        self._finish_attempt(operation, now, "RETRY", code, category)
        self._clear_claim(operation)
        return operation

    def mark_reconciliation_required(self, claim, code):
        operation = self._validate_claim(claim)
        now = self.clock()
        operation.status = OutboxStatus.RECONCILIATION_REQUIRED
        operation.failure_code = code
        operation.failure_category = FailureCategory.RECONCILIATION_REQUIRED
        operation.reconciliation_state = ReconciliationState.REQUIRED
        self._finish_attempt(operation, now, "UNCERTAIN", code, operation.failure_category)
        self._clear_claim(operation)
        return operation

    def mark_dead_letter(self, claim, reason):
        operation = self._validate_claim(claim)
        now = self.clock()
        return self._dead_letter(operation, now, reason)

    def _dead_letter(self, operation, now, reason):
        operation.status = OutboxStatus.DEAD_LETTER
        operation.dead_letter_reason = reason
        operation.completed_at = now
        self._finish_attempt(operation, now, "DEAD_LETTER", operation.failure_code, operation.failure_category)
        self._clear_claim(operation)
        return operation

    def cancel_operation(self, operation_id):
        operation = self.get_operation(operation_id)
        if operation.status not in {OutboxStatus.PENDING, OutboxStatus.RETRY_WAIT}:
            raise InvalidOutboxTransitionError("Operation cannot be cancelled")
        operation.status = OutboxStatus.CANCELLED
        operation.completed_at = self.clock()
        return operation

    def abandon_operation(self, operation_id, reason):
        operation = self.get_operation(operation_id)
        if operation.status in {
            OutboxStatus.CLAIMED, OutboxStatus.DISPATCHING,
            OutboxStatus.SUCCEEDED,
        }:
            raise InvalidOutboxTransitionError(
                "Operation cannot be abandoned"
            )
        operation.status = OutboxStatus.DEAD_LETTER
        operation.dead_letter_reason = reason
        operation.completed_at = self.clock()
        return operation

    def list_attempts(self, operation_id):
        self.get_operation(operation_id)
        return tuple(self._attempts.get(operation_id, ()))

    def recover_expired(self, now=None):
        now = now or self.clock()
        count = 0
        for operation in self._operations.values():
            if (
                operation.status in {OutboxStatus.CLAIMED, OutboxStatus.DISPATCHING}
                and operation.claim_expires_at is not None
                and operation.claim_expires_at <= now
            ):
                if operation.status == OutboxStatus.DISPATCHING:
                    operation.status = OutboxStatus.RECONCILIATION_REQUIRED
                    operation.reconciliation_state = ReconciliationState.REQUIRED
                else:
                    operation.status = OutboxStatus.PENDING
                self._clear_claim(operation)
                count += 1
        return count

    def retry_dead_letter(self, operation_id):
        operation = self.get_operation(operation_id)
        if operation.status != OutboxStatus.DEAD_LETTER:
            raise InvalidOutboxTransitionError("Operation is not dead-lettered")
        operation.status = OutboxStatus.PENDING
        operation.available_at = self.clock()
        operation.completed_at = None
        operation.dead_letter_reason = None
        return operation

    def pause_provider(self, provider_id): self._provider_pauses[provider_id] = True
    def resume_provider(self, provider_id): self._provider_pauses[provider_id] = False
    def is_provider_paused(self, provider_id): return self._provider_pauses.get(provider_id, False)

    def export_state(self):
        return {
            "operations": dict(self._operations),
            "attempts": {
                key: list(values) for key, values in self._attempts.items()
            },
            "idempotency": self._idempotency,
            "provider_pauses": self._provider_pauses,
            "audit": self._audit,
        }

    def import_state(self, state, *, recover=True):
        self._operations = state.get("operations", {})
        self._attempts = state.get("attempts", {})
        self._idempotency = state.get("idempotency", {})
        self._provider_pauses = state.get("provider_pauses", {})
        self._audit = state.get("audit", [])
        if recover: self.recover_expired()

    def _eligible(self, now):
        values = (
            item for item in self._operations.values()
            if item.status in {OutboxStatus.PENDING, OutboxStatus.RETRY_WAIT}
            and item.available_at <= now
            and not self.is_provider_paused(item.provider_id)
        )
        return sorted(values, key=lambda item: (
            item.priority, item.available_at, item.created_at, item.operation_id
        ))

    def _validate_claim(self, claim):
        operation = self.get_operation(claim.operation_id)
        now = self.clock()
        if operation.claim_expires_at is None or operation.claim_expires_at <= now:
            raise OutboxClaimExpiredError("Outbox claim expired")
        if operation.fencing_token != claim.fencing_token:
            raise StaleOutboxFencingError("Outbox fencing token is stale")
        if (
            operation.claim_owner != claim.owner_id
            or operation.claim_token_hash != _hash(claim.token)
        ):
            raise OutboxClaimError("Outbox claim identity is stale")
        return operation

    @staticmethod
    def _clear_claim(operation):
        operation.claim_owner = None
        operation.claim_token_hash = None
        operation.claimed_at = None
        operation.claim_expires_at = None

    def _finish_attempt(self, operation, now, outcome, code=None, category=None):
        attempts = self._attempts.get(operation.operation_id, [])
        if attempts and attempts[-1].completed_at is None:
            prior = attempts[-1]
            attempts[-1] = OutboxAttempt(
                prior.operation_id, prior.attempt_number, prior.started_at,
                now, outcome, code, category, outcome,
            )
