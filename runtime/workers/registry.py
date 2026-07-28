"""Provider-neutral worker registration and liveness state."""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.workers.models import WorkerRegistration, WorkerStatus


class WorkerRegistryError(RuntimeError): pass
class DuplicateWorkerInstanceError(WorkerRegistryError): pass
class WorkerNotFoundError(WorkerRegistryError): pass
class WorkerVersionConflictError(WorkerRegistryError): pass


class InMemoryWorkerRegistry:
    def __init__(self, *, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._workers = {}
        self._history = {}

    def register(self, registration):
        if registration.worker_instance_id in self._workers:
            raise DuplicateWorkerInstanceError(registration.worker_instance_id)
        self._workers[registration.worker_instance_id] = registration
        self._record(registration, "REGISTERED")
        self._changed()
        return registration

    def get(self, instance_id):
        try: return self._workers[instance_id]
        except KeyError as error: raise WorkerNotFoundError(instance_id) from error

    def list(self): return tuple(sorted(self._workers.values(), key=lambda item: item.worker_instance_id))

    def update_status(self, instance_id, status, *, expected_version=None):
        worker = self.get(instance_id)
        self._version(worker, expected_version)
        worker.status = status
        worker.version += 1
        self._record(worker, f"STATUS:{status.value}")
        self._changed()
        return worker

    def heartbeat(self, instance_id, *, timeout_seconds, expected_version=None):
        worker = self.get(instance_id)
        self._version(worker, expected_version)
        now = self.clock()
        worker.last_heartbeat_at = now
        worker.heartbeat_expires_at = now + timedelta(seconds=timeout_seconds)
        worker.version += 1
        self._record(worker, "HEARTBEAT")
        self._changed()
        return worker

    def assign_operation(self, instance_id, operation_id):
        worker = self.get(instance_id)
        worker.current_operation_id = operation_id
        worker.version += 1
        self._changed()

    def clear_operation(self, instance_id):
        worker = self.get(instance_id)
        worker.current_operation_id = None
        worker.version += 1
        self._changed()

    def request_shutdown(self, instance_id):
        worker = self.get(instance_id)
        worker.shutdown_requested = True
        worker.status = WorkerStatus.STOPPING
        worker.version += 1
        self._record(worker, "SHUTDOWN_REQUESTED")
        self._changed()

    def mark_stopped(self, instance_id):
        worker = self.get(instance_id)
        worker.status = WorkerStatus.STOPPED
        worker.stopped_at = self.clock()
        worker.current_operation_id = None
        worker.version += 1
        self._record(worker, "STOPPED")
        self._changed()

    def mark_failed(self, instance_id):
        return self.update_status(instance_id, WorkerStatus.FAILED)

    def scan_stale(self):
        now = self.clock()
        stale = []
        for worker in self._workers.values():
            if (
                worker.status not in {
                    WorkerStatus.STOPPED, WorkerStatus.FAILED,
                    WorkerStatus.STALE,
                }
                and worker.heartbeat_expires_at <= now
            ):
                worker.status = WorkerStatus.STALE
                worker.version += 1
                stale.append(worker)
                self._record(worker, "STALE")
        if stale: self._changed()
        return tuple(stale)

    def history(self, instance_id):
        self.get(instance_id)
        return tuple(self._history.get(instance_id, ()))

    def snapshot(self):
        return {
            "workers": {
                key: _worker_dict(item) for key, item in self._workers.items()
            },
            "history": self._history,
        }

    def restore(self, value):
        self._workers = {
            key: _worker_from_dict(item)
            for key, item in value.get("workers", {}).items()
        }
        self._history = dict(value.get("history", {}))

    def _record(self, worker, action):
        self._history.setdefault(worker.worker_instance_id, []).append({
            "action": action, "timestamp": self.clock().isoformat(),
            "version": worker.version,
        })

    @staticmethod
    def _version(worker, expected):
        if expected is not None and worker.version != expected:
            raise WorkerVersionConflictError("Worker version conflict")

    def _changed(self): pass


class FileWorkerRegistry(InMemoryWorkerRegistry):
    def __init__(self, path, *, clock=None):
        self.path = Path(path).resolve()
        super().__init__(clock=clock)
        if self.path.exists():
            self.restore(json.loads(self.path.read_text(encoding="utf-8")))
    def _changed(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.snapshot(), sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)


class SQLiteWorkerRegistry(FileWorkerRegistry):
    """SQLite durable registry using one canonical versioned state row."""
    def __init__(self, path, *, clock=None):
        self.database_path = str(Path(path).resolve())
        InMemoryWorkerRegistry.__init__(self, clock=clock)
        connection = sqlite3.connect(self.database_path)
        try:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS worker_registry_schema("
                "singleton INTEGER PRIMARY KEY, version INTEGER NOT NULL);"
                "CREATE TABLE IF NOT EXISTS worker_registry_state("
                "singleton INTEGER PRIMARY KEY, canonical_state TEXT NOT NULL);"
                "CREATE INDEX IF NOT EXISTS idx_worker_heartbeat "
                "ON worker_registry_schema(version);"
            )
            row = connection.execute(
                "SELECT version FROM worker_registry_schema WHERE singleton=1"
            ).fetchone()
            if row and row[0] > 1: raise ValueError("Worker schema is newer")
            connection.execute(
                "INSERT OR IGNORE INTO worker_registry_schema VALUES(1,1)"
            )
            state = connection.execute(
                "SELECT canonical_state FROM worker_registry_state WHERE singleton=1"
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
        if state: self.restore(json.loads(state[0]))
    def _changed(self):
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "INSERT OR REPLACE INTO worker_registry_state VALUES(1,?)",
                (json.dumps(self.snapshot(), sort_keys=True),),
            )
            connection.commit()
        finally: connection.close()


def _worker_dict(worker):
    value = dict(vars(worker))
    value["status"] = worker.status.value
    for key in (
        "started_at", "registered_at", "last_heartbeat_at",
        "heartbeat_expires_at", "stopped_at",
    ):
        value[key] = value[key].isoformat() if value[key] else None
    return value


def _worker_from_dict(value):
    copied = dict(value)
    copied["status"] = WorkerStatus(copied["status"])
    copied["supported_operation_types"] = tuple(copied["supported_operation_types"])
    copied["supported_provider_capabilities"] = tuple(copied["supported_provider_capabilities"])
    for key in (
        "started_at", "registered_at", "last_heartbeat_at",
        "heartbeat_expires_at", "stopped_at",
    ):
        copied[key] = datetime.fromisoformat(copied[key]) if copied[key] else None
    return WorkerRegistration(**copied)
