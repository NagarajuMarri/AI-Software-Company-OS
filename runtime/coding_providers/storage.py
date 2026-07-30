"""Atomic schema-versioned provider operation, result, and progress store."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from runtime.coding_providers.errors import ProviderStateError
from runtime.coding_providers.models import (
    FileOperation,
    FileOperationKind,
    ProviderOperation,
    ProviderOperationState,
    ProviderProgressEvent,
    ProviderResultStatus,
    ProviderTaskResult,
    ProviderUsage,
)


class ProviderOperationStore:
    SCHEMA_VERSION = 1

    def __init__(self, state_root):
        self.root = Path(state_root) / "coding-providers"

    def save_operation(self, operation):
        self._save(operation.project_id, "operations",
                   operation.provider_operation_id, operation)

    def load_operation(self, project_id, operation_id):
        value = self._load(project_id, "operations", operation_id)
        return ProviderOperation(**{
            **value,
            "state": ProviderOperationState(value["state"]),
            "created_at": datetime.fromisoformat(value["created_at"]),
            "updated_at": datetime.fromisoformat(value["updated_at"]),
            "usage": ProviderUsage(**value["usage"]),
        })

    def list_operations(self, project_id):
        return tuple(
            self.load_operation(project_id, path.stem)
            for path in self._files(project_id, "operations"))

    def save_result(self, project_id, operation_id, result):
        self._save(project_id, "results", operation_id, result)

    def load_result(self, project_id, operation_id):
        value = self._load(project_id, "results", operation_id)
        return ProviderTaskResult(**{
            **value,
            "status": ProviderResultStatus(value["status"]),
            "file_operations": tuple(FileOperation(
                FileOperationKind(item["kind"]), item["path"], item["content"])
                for item in value["file_operations"]),
            "executed_activity": tuple(value["executed_activity"]),
            "artifacts": tuple(value["artifacts"]),
            "warnings": tuple(value["warnings"]),
            "unresolved_issues": tuple(value["unresolved_issues"]),
            "progress_sequences": tuple(value["progress_sequences"]),
            "usage": ProviderUsage(**value["usage"]),
        })

    def append_progress(self, project_id, event):
        events = self.load_progress(project_id, event.provider_operation_id)
        existing = next((item for item in events if item.sequence == event.sequence), None)
        if existing is not None:
            if existing != event:
                raise ProviderStateError("Conflicting provider progress sequence")
            return events
        if event.sequence != len(events) + 1:
            raise ProviderStateError("Provider progress sequence regressed or skipped")
        values = events + (event,)
        self._save(project_id, "progress", event.provider_operation_id, values)
        return values

    def load_progress(self, project_id, operation_id):
        try:
            values = self._load(project_id, "progress", operation_id)
        except ProviderStateError as error:
            if "not found" in str(error):
                return ()
            raise
        return tuple(ProviderProgressEvent(**{
            **item,
            "timestamp": datetime.fromisoformat(item["timestamp"]),
            "metadata": tuple(tuple(pair) for pair in item["metadata"]),
        }) for item in values)

    def _save(self, project_id, kind, identifier, value):
        path = self._path(project_id, kind, identifier)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": self.SCHEMA_VERSION, "kind": kind,
                   "value": _encode(asdict(value) if hasattr(value, "__dataclass_fields__")
                                    else value)}
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{identifier}.", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception as error:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise ProviderStateError("Could not persist provider state") from error

    def _load(self, project_id, kind, identifier):
        path = self._path(project_id, kind, identifier)
        if not path.is_file():
            raise ProviderStateError("Provider state not found")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (payload["schema_version"] != self.SCHEMA_VERSION
                    or payload["kind"] != kind):
                raise ValueError("Invalid provider schema")
            return payload["value"]
        except ProviderStateError:
            raise
        except Exception as error:
            raise ProviderStateError("Provider state is corrupt") from error

    def _path(self, project_id, kind, identifier):
        for value in (project_id, identifier):
            if not value or not all(c.isalnum() or c in "._-" for c in value):
                raise ProviderStateError("Unsafe provider state identifier")
        return self.root / project_id / kind / f"{identifier}.json"

    def _files(self, project_id, kind):
        directory = self.root / project_id / kind
        return sorted(directory.glob("*.json")) if directory.is_dir() else ()


def _encode(value):
    if is_dataclass(value):
        return _encode(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    return value
