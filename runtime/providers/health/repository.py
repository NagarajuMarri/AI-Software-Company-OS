import json
import os
import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from runtime.providers.health.exceptions import (
    ProviderHealthNotFoundError, ProviderHealthVersionConflictError,
)
from runtime.providers.health.models import ProviderHealthState, ProviderHealthStatus


class InMemoryProviderHealthRepository:
    def __init__(self):
        self._states = {}

    def add(self, state):
        key = (state.provider_id, state.capability)
        if key in self._states:
            raise ProviderHealthVersionConflictError("Provider health already exists")
        self._states[key] = deepcopy(state)
        self._changed()
        return deepcopy(state)

    def get(self, provider_id, capability):
        try: return deepcopy(self._states[(provider_id, capability)])
        except KeyError as error:
            raise ProviderHealthNotFoundError("Provider health not found") from error

    def list(self): return tuple(deepcopy(self._states[key]) for key in sorted(self._states))

    def save(self, state, *, expected_version):
        current = self.get(state.provider_id, state.capability)
        if current.version != expected_version:
            raise ProviderHealthVersionConflictError("Provider health version conflict")
        state.version = expected_version + 1
        self._states[(state.provider_id, state.capability)] = deepcopy(state)
        self._changed()
        return deepcopy(state)

    def snapshot(self):
        return [_encode(item) for item in self.list()]

    def restore(self, values):
        restored = {}
        for value in values:
            state = _decode(value)
            restored[(state.provider_id, state.capability)] = state
        self._states = restored

    def _changed(self): pass


class FileProviderHealthRepository(InMemoryProviderHealthRepository):
    def __init__(self, path):
        self.path = Path(path).resolve()
        super().__init__()
        if self.path.exists():
            self.restore(json.loads(self.path.read_text(encoding="utf-8")))

    def _changed(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.snapshot(), sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)


class SQLiteProviderHealthRepository(FileProviderHealthRepository):
    def __init__(self, path):
        self.database_path = str(Path(path).resolve())
        InMemoryProviderHealthRepository.__init__(self)
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS provider_health_state "
                "(singleton INTEGER PRIMARY KEY, schema_version INTEGER NOT NULL, "
                "canonical_state TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT schema_version, canonical_state FROM provider_health_state "
                "WHERE singleton=1"
            ).fetchone()
            if row and row[0] > 1: raise ValueError("Provider health schema is newer")
        finally: connection.close()
        self._persisted_state = row[1] if row else None
        if row: self.restore(json.loads(row[1]))

    def _changed(self):
        encoded = json.dumps(self.snapshot(), sort_keys=True)
        connection = sqlite3.connect(self.database_path)
        try:
            if self._persisted_state is None:
                try:
                    connection.execute(
                        "INSERT INTO provider_health_state VALUES(1,1,?)", (encoded,)
                    )
                except sqlite3.IntegrityError as error:
                    raise ProviderHealthVersionConflictError(
                        "Concurrent provider health update"
                    ) from error
            else:
                cursor = connection.execute(
                    "UPDATE provider_health_state SET canonical_state=? "
                    "WHERE singleton=1 AND canonical_state=?",
                    (encoded, self._persisted_state),
                )
                if cursor.rowcount != 1:
                    raise ProviderHealthVersionConflictError(
                        "Concurrent provider health update"
                    )
            connection.commit()
            self._persisted_state = encoded
        finally: connection.close()


def _encode(state):
    value = dict(vars(state))
    value["status"] = state.status.value
    for key in ("last_success_at", "last_failure_at", "open_until", "updated_at"):
        value[key] = value[key].isoformat() if value[key] else None
    return value


def _decode(value):
    copied = dict(value)
    copied["status"] = ProviderHealthStatus(copied["status"])
    for key in ("last_success_at", "last_failure_at", "open_until", "updated_at"):
        copied[key] = datetime.fromisoformat(copied[key]) if copied[key] else None
    return ProviderHealthState(**copied)
