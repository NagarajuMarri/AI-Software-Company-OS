"""Atomic integrity-checked persistence for customer execution plans."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from runtime.customer_execution.errors import (
    CustomerExecutionConflict,
    CustomerExecutionCorrupt,
)
from runtime.customer_execution.models import (
    CustomerExecutionPlan,
    CustomerExecutionPlanStatus,
    CustomerExecutionTask,
    CustomerExecutionTaskStatus,
    plan_id_for,
)


_SCHEMA_VERSION = 1


class FileCustomerExecutionStore:
    """Persist one monotonic execution plan per customer request."""

    def __init__(self, root: Path) -> None:
        path = Path(root).expanduser()
        if path.is_symlink():
            raise CustomerExecutionCorrupt("Customer execution store cannot be a symbolic link")
        self._root = path.resolve()
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self._root.chmod(0o700)

    def find(self, customer_id: str, request_id: str) -> CustomerExecutionPlan | None:
        path = self._path(customer_id, request_id)
        if not path.exists():
            return None
        return self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerExecutionPlan:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerExecutionCorrupt("Customer execution plan path is unsafe")
        if os.name != "nt" and path.exists() and path.stat().st_mode & 0o077:
            raise CustomerExecutionCorrupt("Customer execution plan permissions are too broad")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerExecutionConflict("Customer execution plan does not exist") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid execution envelope")
            value = _from_record(envelope["record"])
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.plan_id != plan_id_for(request_id)
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Execution plan authority mismatch")
            return value
        except CustomerExecutionCorrupt:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerExecutionCorrupt("Customer execution plan is corrupt") from error

    def create(self, value: CustomerExecutionPlan) -> CustomerExecutionPlan:
        path = self._path(value.customer_id, value.request_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing.scope_digest == value.scope_digest:
                return existing
            raise CustomerExecutionConflict("A different execution plan already exists") from None
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_encode(value))
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise
        return value

    def replace(
        self,
        value: CustomerExecutionPlan,
        *,
        expected_digest: str,
    ) -> CustomerExecutionPlan:
        current = self.load(value.customer_id, value.request_id)
        if current.digest != expected_digest:
            raise CustomerExecutionConflict("Customer execution plan changed")
        if current.scope_digest != value.scope_digest:
            raise CustomerExecutionConflict("Approved execution scope cannot change")
        path = self._path(value.customer_id, value.request_id)
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{value.plan_id}.", suffix=".tmp"
        )
        try:
            if os.name != "nt":
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_encode(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return value

    def _path(self, customer_id: str, request_id: str) -> Path:
        plan_id_for(customer_id)
        plan_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerExecutionCorrupt("Customer execution path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerExecutionCorrupt("Customer execution path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerExecutionCorrupt("Customer execution directory is unsafe")
            if any(value.name != "execution-plan-v1.json" for value in directory.iterdir()):
                raise CustomerExecutionCorrupt("Customer execution directory is not closed")
        return directory / "execution-plan-v1.json"


def _record(value: CustomerExecutionPlan) -> dict[str, object]:
    record = asdict(value)
    record["status"] = value.status.value
    record["created_at"] = value.created_at.isoformat()
    record["updated_at"] = value.updated_at.isoformat()
    record["approved_at"] = value.approved_at.isoformat() if value.approved_at else None
    record["tasks"] = [
        {
            **asdict(task),
            "status": task.status.value,
            "acceptance_criteria": list(task.acceptance_criteria),
            "candidate_files": list(task.candidate_files),
            "allowed_paths": list(task.allowed_paths),
            "forbidden_paths": list(task.forbidden_paths),
            "changed_paths": list(task.changed_paths),
        }
        for task in value.tasks
    ]
    return record


def _encode(value: CustomerExecutionPlan) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _from_record(value: dict[str, object]) -> CustomerExecutionPlan:
    expected = {
        "plan_id",
        "customer_id",
        "request_id",
        "product_id",
        "progress_digest",
        "requirements_digest",
        "prd_digest",
        "roadmap_digest",
        "roadmap_approval_digest",
        "estimate_digest",
        "workspace_id",
        "workspace_branch",
        "workspace_commit",
        "provider_id",
        "model",
        "authentication_mode",
        "billing_source",
        "tasks",
        "created_at",
        "updated_at",
        "status",
        "approved_at",
        "approved_by",
        "failure_classification",
    }
    if set(value) != expected:
        raise ValueError("Execution plan fields are invalid")
    tasks = value["tasks"]
    if not isinstance(tasks, list):
        raise ValueError("Execution task records are invalid")
    return CustomerExecutionPlan(
        value["plan_id"],  # type: ignore[arg-type]
        value["customer_id"],  # type: ignore[arg-type]
        value["request_id"],  # type: ignore[arg-type]
        value["product_id"],  # type: ignore[arg-type]
        value["progress_digest"],  # type: ignore[arg-type]
        value["requirements_digest"],  # type: ignore[arg-type]
        value["prd_digest"],  # type: ignore[arg-type]
        value["roadmap_digest"],  # type: ignore[arg-type]
        value["roadmap_approval_digest"],  # type: ignore[arg-type]
        value["estimate_digest"],  # type: ignore[arg-type]
        value["workspace_id"],  # type: ignore[arg-type]
        value["workspace_branch"],  # type: ignore[arg-type]
        value["workspace_commit"],  # type: ignore[arg-type]
        value["provider_id"],  # type: ignore[arg-type]
        value["model"],  # type: ignore[arg-type]
        value["authentication_mode"],  # type: ignore[arg-type]
        value["billing_source"],  # type: ignore[arg-type]
        tuple(_task(item) for item in tasks),
        datetime.fromisoformat(value["created_at"]),  # type: ignore[arg-type]
        datetime.fromisoformat(value["updated_at"]),  # type: ignore[arg-type]
        CustomerExecutionPlanStatus(value["status"]),
        datetime.fromisoformat(value["approved_at"]) if value["approved_at"] else None,  # type: ignore[arg-type]
        value["approved_by"],  # type: ignore[arg-type]
        value["failure_classification"],  # type: ignore[arg-type]
    )


def _task(value: object) -> CustomerExecutionTask:
    if not isinstance(value, dict):
        raise ValueError("Execution task record is invalid")
    expected = {
        "task_id",
        "requirement_id",
        "title",
        "objective",
        "acceptance_criteria",
        "candidate_files",
        "allowed_paths",
        "forbidden_paths",
        "status",
        "provider_operation_id",
        "provider_task_id",
        "changed_paths",
        "additions",
        "deletions",
        "input_units",
        "output_units",
        "request_count",
        "result_summary",
        "manifest_digest",
    }
    if set(value) != expected:
        raise ValueError("Execution task fields are invalid")
    return CustomerExecutionTask(
        value["task_id"],
        value["requirement_id"],
        value["title"],
        value["objective"],
        tuple(value["acceptance_criteria"]),
        tuple(value["candidate_files"]),
        tuple(value["allowed_paths"]),
        tuple(value["forbidden_paths"]),
        CustomerExecutionTaskStatus(value["status"]),
        value["provider_operation_id"],
        value["provider_task_id"],
        tuple(value["changed_paths"]),
        value["additions"],
        value["deletions"],
        value["input_units"],
        value["output_units"],
        value["request_count"],
        value["result_summary"],
        value["manifest_digest"],
    )
