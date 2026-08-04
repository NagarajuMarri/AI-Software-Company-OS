"""Atomic JSON task persistence, including all resume evidence."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Protocol

from runtime.managed_product_implementation.models import *  # noqa: F403


class ManagedProductTaskStore(Protocol):
    def save(self, task: ManagedProductTask) -> None: ...
    def load(self, task_id: str) -> ManagedProductTask | None: ...


class InMemoryManagedProductTaskStore:
    def __init__(self) -> None:
        self.values: dict[str, ManagedProductTask] = {}

    def save(self, task: ManagedProductTask) -> None:
        current = self.values.get(task.task_id)
        _validate_replacement(current, task)
        self.values[task.task_id] = task

    def load(self, task_id: str) -> ManagedProductTask | None:
        return self.values.get(task_id)


class JsonManagedProductTaskStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(self, task: ManagedProductTask) -> None:
        current = self.load(task.task_id)
        _validate_replacement(current, task)
        self.root.mkdir(parents=True, exist_ok=True)
        target = self._target(task.task_id)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                asdict(task),
                default=lambda v: v.value
                if isinstance(v, Enum)
                else v.isoformat()
                if isinstance(v, datetime)
                else v,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(target)

    def load(self, task_id: str) -> ManagedProductTask | None:
        target = self._target(task_id)
        if not target.exists():
            return None
        return _task(json.loads(target.read_text(encoding="utf-8")))

    def _target(self, task_id: str) -> Path:
        if not task_id or Path(task_id).name != task_id:
            raise ValueError("Task ID must be filesystem safe")
        return self.root / f"{task_id}.json"


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _validate_replacement(
    current: ManagedProductTask | None, replacement: ManagedProductTask
) -> None:
    if current is None:
        return
    if current.state.terminal:
        raise ValueError("Completed tasks are immutable")
    immutable = (
        "task_id",
        "project_id",
        "repository",
        "branch",
        "base_branch",
        "expected_commit_sha",
        "milestone",
        "implementation_request",
        "provider",
        "allowed_paths",
        "implementation_actor",
        "created_at",
    )
    if any(getattr(current, name) != getattr(replacement, name) for name in immutable):
        raise ValueError("Managed product task identity and approved scope are immutable")
    if replacement.updated_at < current.updated_at:
        raise ValueError("Task timestamps cannot move backwards")


def _required_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _step(value: dict) -> VerificationStepResult:
    return VerificationStepResult(
        value["name"],
        VerificationStatus(value["status"]),
        tuple(value["command"]),
        value["exit_code"],
        value["output"],
        _required_dt(value["started_at"]),
        _required_dt(value["completed_at"]),
        value.get("workspace_commit_sha", ""),
        value.get("diff_digest", ""),
    )


def _task(data: dict) -> ManagedProductTask:
    data["state"] = ImplementationState(data["state"])
    data["verification_status"] = VerificationStatus(data["verification_status"])
    data["resume_from"] = (
        ImplementationState(data["resume_from"]) if data.get("resume_from") else None
    )
    for name in ("allowed_paths", "pending_actions", "requirement_ids"):
        data[name] = tuple(data.get(name, ()))
    for name in ("created_at", "updated_at", "completed_at"):
        data[name] = _dt(data.get(name))
    if data.get("workspace"):
        value = data["workspace"]
        value["created_at"] = _dt(value["created_at"])
        value["disposition"] = WorkspaceDisposition(
            value.get("disposition", WorkspaceDisposition.ACTIVE.value)
        )
        data["workspace"] = WorkspaceResult(**value)
    data["verification"] = tuple(_step(v) for v in data.get("verification", []))
    for name, kind in (
        ("provider_result", ProviderImplementationResult),
        ("commit_result", CommitResult),
        ("push_result", PushResult),
        ("pull_request", PullRequestResult),
    ):
        if data.get(name):
            value = data[name]
            for field_name in ("changed_files", "known_risks", "remaining_work", "metadata"):
                if field_name in value:
                    value[field_name] = tuple(
                        tuple(x) if isinstance(x, list) else x for x in value[field_name]
                    )
            data[name] = kind(**value)
    if data.get("review_package"):
        value = data["review_package"]
        value["verification_report"] = tuple(_step(v) for v in value["verification_report"])
        for name in ("changed_files", "known_risks", "remaining_work"):
            value[name] = tuple(value[name])
        data["review_package"] = ReviewPackage(**value)
    return ManagedProductTask(**data)
