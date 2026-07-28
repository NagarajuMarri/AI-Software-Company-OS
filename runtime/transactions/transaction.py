"""Transaction lifecycle and coordination."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING

from runtime.exceptions import (
    NestedTransactionError,
    TransactionAlreadyCompletedError,
    TransactionCommitError,
    TransactionRollbackError,
)
from runtime.transactions.snapshot import MutableSnapshot

if TYPE_CHECKING:
    from runtime.events.event import RuntimeEvent
    from runtime.events.store import EventStore


def atomic_domain_operation(method):
    """Run a service mutation in its publisher's joinable transaction."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        publisher = getattr(self, "event_publisher", None)
        if publisher is None:
            return method(self, *args, **kwargs)
        from runtime.exceptions import ExecutionFailedError

        domain_failure = None
        with publisher.atomic():
            try:
                result = method(self, *args, **kwargs)
            except ExecutionFailedError as error:
                # A recorded FAILED execution is a committed terminal outcome.
                domain_failure = error
                result = None
        if domain_failure is not None:
            raise domain_failure
        return result

    return wrapped


class RuntimeTransaction:
    """One single-use in-memory state and event transaction."""

    def __init__(
        self,
        event_store: EventStore,
        targets: Iterable[object] = (),
    ) -> None:
        self._event_store = event_store
        self._snapshots: dict[int, MutableSnapshot] = {}
        self._events: list[RuntimeEvent] = []
        self._completed = False
        for target in targets:
            self.register(target)

    @property
    def staged_events(self) -> tuple[RuntimeEvent, ...]:
        return tuple(self._events)

    @property
    def completed(self) -> bool:
        return self._completed

    def register(self, target: object) -> None:
        self._ensure_active()
        if id(target) not in self._snapshots:
            self._snapshots[id(target)] = MutableSnapshot.capture(target)

    def stage(self, event: RuntimeEvent) -> RuntimeEvent:
        self._ensure_active()
        self._events.append(event)
        return event

    def commit(self) -> None:
        self._ensure_active()
        try:
            self._event_store.add_events(self._events)
        except Exception as error:
            try:
                self._restore()
            except TransactionRollbackError as rollback_error:
                self._completed = True
                self._events.clear()
                raise TransactionRollbackError(
                    "Commit failed and state rollback also failed"
                ) from rollback_error
            self._completed = True
            self._events.clear()
            raise TransactionCommitError(
                "Failed to commit domain state and staged events"
            ) from error
        self._completed = True
        self._events.clear()

    def rollback(self) -> None:
        self._ensure_active()
        self._restore()
        self._events.clear()
        self._completed = True

    def _restore(self) -> None:
        errors: list[Exception] = []
        for snapshot in reversed(tuple(self._snapshots.values())):
            try:
                snapshot.restore()
            except Exception as error:
                errors.append(error)
        if errors:
            raise TransactionRollbackError(
                f"Failed to restore {len(errors)} transaction snapshot(s)"
            ) from errors[0]

    def _ensure_active(self) -> None:
        if self._completed:
            raise TransactionAlreadyCompletedError(
                "Transaction has already committed or rolled back"
            )


class TransactionCoordinator:
    """Coordinate explicit transactions and joinable domain operations."""

    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store
        self.current: RuntimeTransaction | None = None
        self._providers: list[Callable[[], Iterable[object]]] = []

    def register_snapshot_provider(
        self,
        provider: Callable[[], Iterable[object]],
    ) -> None:
        self._providers.append(provider)

    def _targets(self) -> list[object]:
        return [
            target
            for provider in self._providers
            for target in provider()
        ]

    @contextmanager
    def transaction(self):
        if self.current is not None:
            raise NestedTransactionError("Nested transactions are not supported")
        transaction = RuntimeTransaction(self.event_store, self._targets())
        self.current = transaction
        try:
            yield transaction
        except Exception:
            if not transaction.completed:
                transaction.rollback()
            raise
        else:
            transaction.commit()
        finally:
            self.current = None

    @contextmanager
    def atomic(self):
        if self.current is not None:
            yield self.current
            return
        with self.transaction() as transaction:
            yield transaction
