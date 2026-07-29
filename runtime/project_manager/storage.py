"""Atomic JSON persistence outside managed product repositories."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from runtime.project_manager.errors import (ManagerStateCorruptError,
    ManagerStateNotFoundError, ManagerStorageError, UnsupportedManagerSchemaError)
from runtime.project_manager.models import *


class ManagerStateStore:
    SCHEMA_VERSION = 1

    def __init__(self, state_root: str | Path):
        self.state_root = Path(state_root)

    def path_for(self, project_id: str) -> Path:
        return self.state_root / "projects" / project_id / "manager.json"

    def exists(self, project_id: str) -> bool:
        return self.path_for(project_id).is_file()

    def save(self, state: ProjectManagerState) -> None:
        path = self.path_for(state.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _encode(asdict(state))
        descriptor, temporary = tempfile.mkstemp(prefix=".manager.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception as error:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
            raise ManagerStorageError(f"Could not save manager state for {state.project_id!r}") from error

    def load(self, project_id: str) -> ProjectManagerState:
        path = self.path_for(project_id)
        if not path.exists():
            raise ManagerStateNotFoundError(f"Manager state for {project_id!r} is not initialised")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") != self.SCHEMA_VERSION:
                raise UnsupportedManagerSchemaError(
                    f"Unsupported manager schema {data.get('schema_version')!r}")
            return _state(data)
        except UnsupportedManagerSchemaError:
            raise
        except Exception as error:
            raise ManagerStateCorruptError(f"Manager state {path} cannot be safely loaded") from error


def _encode(value):
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Enum): return value.value
    if isinstance(value, dict): return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_encode(v) for v in value]
    return value


def _dt(value): return datetime.fromisoformat(value) if value else None


def _state(d):
    def task(x): return Task(**{**x, "status": TaskStatus(x["status"]),
        "dependencies": tuple(x["dependencies"]), "created_at": _dt(x["created_at"]),
        "updated_at": _dt(x["updated_at"]), "started_at": _dt(x["started_at"]),
        "completed_at": _dt(x["completed_at"])})
    def milestone(x): return Milestone(**{**x, "status": MilestoneStatus(x["status"]),
        "task_ids": tuple(x["task_ids"]), "dependencies": tuple(x["dependencies"]),
        "created_at": _dt(x["created_at"]), "updated_at": _dt(x["updated_at"]),
        "started_at": _dt(x["started_at"]), "completed_at": _dt(x["completed_at"])})
    return ProjectManagerState(project_id=d["project_id"], schema_version=d["schema_version"],
        status=ProjectManagementStatus(d["status"]), milestones=tuple(milestone(x) for x in d["milestones"]),
        tasks=tuple(task(x) for x in d["tasks"]), active_milestone_id=d["active_milestone_id"],
        decisions=tuple(Decision(**{**x, "timestamp": _dt(x["timestamp"])}) for x in d["decisions"]),
        notes=tuple(Note(**{**x, "timestamp": _dt(x["timestamp"])}) for x in d["notes"]),
        risks=tuple(Risk(**{**x, "severity": RiskSeverity(x["severity"]),
            "status": RiskStatus(x["status"]), "timestamp": _dt(x["timestamp"])}) for x in d["risks"]),
        created_at=_dt(d["created_at"]), updated_at=_dt(d["updated_at"]), metadata=d["metadata"])
