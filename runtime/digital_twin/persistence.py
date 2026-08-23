"""Canonical, tamper-evident persistence for Digital Twin executions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterator

from runtime.digital_twin.errors import (
    DigitalTwinConflictError,
    DigitalTwinStoreError,
)
from runtime.digital_twin.models import (
    DigitalTwinExecutionIntent,
    DigitalTwinExecutionReceipt,
    DigitalTwinExecutionStatus,
    ToolCallEvidence,
    ToolCallOutcome,
    validate_identifier,
)


_SCHEMA_VERSION = 1
_INTENT_FILE = "execution-intent-v1.json"
_RECEIPT_FILE = "execution-receipt-v1.json"
_LOCK_FILE = ".execution.lock"
_KNOWN_ENTRIES = {_INTENT_FILE, _RECEIPT_FILE, _LOCK_FILE}
_MAX_RECORD_BYTES = 1_000_000


class FileDigitalTwinExecutionStore:
    """Write-once intent and receipt storage scoped by tenant and execution."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._root = root.resolve()

    @contextmanager
    def execution_lock(self, tenant_id: str, execution_id: str) -> Iterator[None]:
        """Serialize one exact execution across threads and local processes."""

        directory = self._directory(tenant_id, execution_id, create=True)
        lock_path = directory / _LOCK_FILE
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as error:
            raise DigitalTwinStoreError("Digital Twin execution lock is unsafe") from error
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def save_intent(
        self,
        value: DigitalTwinExecutionIntent,
    ) -> DigitalTwinExecutionIntent:
        path = self._directory(
            value.tenant_id,
            value.execution_id,
            create=True,
        ) / _INTENT_FILE
        try:
            _exclusive_write(path, _encode("INTENT", value.digest, _intent_record(value)))
        except FileExistsError:
            existing = self.load_intent(value.tenant_id, value.execution_id)
            if existing == value:
                return existing
            raise DigitalTwinConflictError(
                "A different Digital Twin execution intent already exists"
            ) from None
        return value

    def find_intent(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> DigitalTwinExecutionIntent | None:
        path = self._directory(tenant_id, execution_id) / _INTENT_FILE
        if not path.exists():
            return None
        return self.load_intent(tenant_id, execution_id)

    def load_intent(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> DigitalTwinExecutionIntent:
        path = self._directory(tenant_id, execution_id) / _INTENT_FILE
        kind, digest, record, content = _read(path)
        try:
            value = _intent_from_record(record)
            if (
                kind != "INTENT"
                or value.tenant_id != tenant_id
                or value.execution_id != execution_id
                or value.digest != digest
                or _encode("INTENT", value.digest, _intent_record(value)) != content
            ):
                raise ValueError("Digital Twin intent identity mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise DigitalTwinStoreError("Digital Twin execution intent is corrupt") from error

    def save_receipt(
        self,
        value: DigitalTwinExecutionReceipt,
    ) -> DigitalTwinExecutionReceipt:
        path = self._directory(
            value.tenant_id,
            value.execution_id,
            create=True,
        ) / _RECEIPT_FILE
        try:
            _exclusive_write(path, _encode("RECEIPT", value.digest, _receipt_record(value)))
        except FileExistsError:
            existing = self.load_receipt(value.tenant_id, value.execution_id)
            if existing == value:
                return existing
            raise DigitalTwinConflictError(
                "A different Digital Twin execution receipt already exists"
            ) from None
        return value

    def find_receipt(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> DigitalTwinExecutionReceipt | None:
        path = self._directory(tenant_id, execution_id) / _RECEIPT_FILE
        if not path.exists():
            return None
        return self.load_receipt(tenant_id, execution_id)

    def load_receipt(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> DigitalTwinExecutionReceipt:
        path = self._directory(tenant_id, execution_id) / _RECEIPT_FILE
        kind, digest, record, content = _read(path)
        try:
            value = _receipt_from_record(record)
            if (
                kind != "RECEIPT"
                or value.tenant_id != tenant_id
                or value.execution_id != execution_id
                or value.digest != digest
                or _encode("RECEIPT", value.digest, _receipt_record(value)) != content
            ):
                raise ValueError("Digital Twin receipt identity mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise DigitalTwinStoreError("Digital Twin execution receipt is corrupt") from error

    def _directory(
        self,
        tenant_id: str,
        execution_id: str,
        *,
        create: bool = False,
    ) -> Path:
        try:
            validate_identifier(tenant_id, "Digital Twin store tenant ID")
            validate_identifier(execution_id, "Digital Twin store execution ID")
        except ValueError as error:
            raise DigitalTwinStoreError("Digital Twin store identity is invalid") from error
        tenant = self._root / tenant_id
        directory = tenant / execution_id
        for candidate in (tenant, directory):
            if candidate.is_symlink():
                raise DigitalTwinStoreError("Digital Twin execution path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise DigitalTwinStoreError("Digital Twin execution path escaped its store")
        if create:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.exists():
            if directory.is_symlink() or not directory.is_dir():
                raise DigitalTwinStoreError("Digital Twin execution directory is unsafe")
            if any(entry.name not in _KNOWN_ENTRIES for entry in directory.iterdir()):
                raise DigitalTwinStoreError("Digital Twin execution directory is not closed")
        return directory


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def _read(path: Path) -> tuple[str, str, dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise DigitalTwinStoreError("Digital Twin execution record is missing or unsafe")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise DigitalTwinStoreError("Digital Twin execution record permissions are unsafe")
    content = path.read_bytes()
    if len(content) > _MAX_RECORD_BYTES:
        raise DigitalTwinStoreError("Digital Twin execution record exceeds its byte limit")
    try:
        envelope = json.loads(content)
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"schema_version", "kind", "digest", "record"}
            or envelope["schema_version"] != _SCHEMA_VERSION
            or not isinstance(envelope["kind"], str)
            or not isinstance(envelope["digest"], str)
            or not isinstance(envelope["record"], dict)
        ):
            raise ValueError("Digital Twin execution envelope is invalid")
        return envelope["kind"], envelope["digest"], envelope["record"], content
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise DigitalTwinStoreError("Digital Twin execution envelope is corrupt") from error


def _encode(kind: str, digest: str, record: dict[str, object]) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": _SCHEMA_VERSION,
                "kind": kind,
                "digest": digest,
                "record": record,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _intent_record(value: DigitalTwinExecutionIntent) -> dict[str, object]:
    return {
        "execution_id": value.execution_id,
        "tenant_id": value.tenant_id,
        "twin_id": value.twin_id,
        "twin_digest": value.twin_digest,
        "assignment_id": value.assignment_id,
        "assignment_digest": value.assignment_digest,
        "authority_id": value.authority_id,
        "authority_digest": value.authority_digest,
        "provider_id": value.provider_id,
        "request_digest": value.request_digest,
        "prepared_at": value.prepared_at.isoformat(),
    }


def _receipt_record(value: DigitalTwinExecutionReceipt) -> dict[str, object]:
    return {
        "receipt_id": value.receipt_id,
        "execution_id": value.execution_id,
        "tenant_id": value.tenant_id,
        "twin_id": value.twin_id,
        "twin_digest": value.twin_digest,
        "assignment_id": value.assignment_id,
        "assignment_digest": value.assignment_digest,
        "authority_id": value.authority_id,
        "authority_digest": value.authority_digest,
        "provider_id": value.provider_id,
        "request_digest": value.request_digest,
        "intent_digest": value.intent_digest,
        "status": value.status.value,
        "summary": value.summary,
        "output_digest": value.output_digest,
        "tool_calls": [
            {
                "sequence": item.sequence,
                "tool_id": item.tool_id,
                "request_digest": item.request_digest,
                "outcome": item.outcome.value,
                "response_digest": item.response_digest,
                "failure_code": item.failure_code,
            }
            for item in value.tool_calls
        ],
        "failure_code": value.failure_code,
        "started_at": value.started_at.isoformat(),
        "completed_at": value.completed_at.isoformat(),
    }


def _intent_from_record(value: dict[str, Any]) -> DigitalTwinExecutionIntent:
    if set(value) != {
        "execution_id",
        "tenant_id",
        "twin_id",
        "twin_digest",
        "assignment_id",
        "assignment_digest",
        "authority_id",
        "authority_digest",
        "provider_id",
        "request_digest",
        "prepared_at",
    }:
        raise ValueError("Digital Twin intent fields are invalid")
    return DigitalTwinExecutionIntent(
        value["execution_id"],
        value["tenant_id"],
        value["twin_id"],
        value["twin_digest"],
        value["assignment_id"],
        value["assignment_digest"],
        value["authority_id"],
        value["authority_digest"],
        value["provider_id"],
        value["request_digest"],
        datetime.fromisoformat(value["prepared_at"]),
    )


def _receipt_from_record(value: dict[str, Any]) -> DigitalTwinExecutionReceipt:
    if set(value) != {
        "receipt_id",
        "execution_id",
        "tenant_id",
        "twin_id",
        "twin_digest",
        "assignment_id",
        "assignment_digest",
        "authority_id",
        "authority_digest",
        "provider_id",
        "request_digest",
        "intent_digest",
        "status",
        "summary",
        "output_digest",
        "tool_calls",
        "failure_code",
        "started_at",
        "completed_at",
    }:
        raise ValueError("Digital Twin receipt fields are invalid")
    return DigitalTwinExecutionReceipt(
        value["receipt_id"],
        value["execution_id"],
        value["tenant_id"],
        value["twin_id"],
        value["twin_digest"],
        value["assignment_id"],
        value["assignment_digest"],
        value["authority_id"],
        value["authority_digest"],
        value["provider_id"],
        value["request_digest"],
        value["intent_digest"],
        DigitalTwinExecutionStatus(value["status"]),
        value["summary"],
        value["output_digest"],
        tuple(_tool_call_from_record(item) for item in value["tool_calls"]),
        value["failure_code"],
        datetime.fromisoformat(value["started_at"]),
        datetime.fromisoformat(value["completed_at"]),
    )


def _tool_call_from_record(value: dict[str, Any]) -> ToolCallEvidence:
    if set(value) != {
        "sequence",
        "tool_id",
        "request_digest",
        "outcome",
        "response_digest",
        "failure_code",
    }:
        raise ValueError("Digital Twin tool-call fields are invalid")
    return ToolCallEvidence(
        value["sequence"],
        value["tool_id"],
        value["request_digest"],
        ToolCallOutcome(value["outcome"]),
        value["response_digest"],
        value["failure_code"],
    )
