"""Write-once, integrity-checked customer requirements approvals."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_requirements.approval_models import (
    CustomerRequirementsApproval,
    approval_id_for,
)
from runtime.customer_requirements.errors import (
    RequirementsApprovalConflict,
    RequirementsApprovalCorrupt,
    RequirementsApprovalNotFound,
)


_SCHEMA_VERSION = 1


class FileCustomerRequirementsApprovalStore:
    """Persist exactly one immutable approval receipt per customer request."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerRequirementsApproval) -> CustomerRequirementsApproval:
        path = self._path(value.customer_id, value.request_id)
        try:
            _exclusive_write(path, _encode(value))
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise RequirementsApprovalConflict("Requirements are already approved") from None
        return value

    def find(self, customer_id: str, request_id: str) -> CustomerRequirementsApproval | None:
        path = self._path(customer_id, request_id)
        if not path.exists():
            return None
        return self.load(customer_id, request_id)

    def is_locked(self, customer_id: str, request_id: str) -> bool:
        return self.find(customer_id, request_id) is not None

    def load(self, customer_id: str, request_id: str) -> CustomerRequirementsApproval:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RequirementsApprovalCorrupt("Requirements approval file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise RequirementsApprovalNotFound("Requirements are not approved") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid approval envelope")
            value = _from_record(envelope["record"])
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.approval_id != approval_id_for(request_id)
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Requirements approval authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RequirementsApprovalCorrupt("Requirements approval is corrupt") from error

    def _path(self, customer_id: str, request_id: str) -> Path:
        approval_id_for(customer_id)
        approval_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise RequirementsApprovalCorrupt("Requirements approval path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise RequirementsApprovalCorrupt("Requirements approval path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise RequirementsApprovalCorrupt("Requirements approval directory is unsafe")
            entries = tuple(directory.iterdir())
            if any(entry.name != "approval.json" for entry in entries):
                raise RequirementsApprovalCorrupt("Requirements approval directory is not closed")
        return directory / "approval.json"


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
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


def _record(value: CustomerRequirementsApproval) -> dict[str, object]:
    return {
        "approval_id": value.approval_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "draft_id": value.draft_id,
        "draft_revision": value.draft_revision,
        "source_request_digest": value.source_request_digest,
        "requirements_digest": value.requirements_digest,
        "confirmation_version": value.confirmation_version,
        "approved_at": value.approved_at.isoformat(),
    }


def _encode(value: CustomerRequirementsApproval) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerRequirementsApproval:
    if set(value) != {
        "approval_id",
        "customer_id",
        "request_id",
        "draft_id",
        "draft_revision",
        "source_request_digest",
        "requirements_digest",
        "confirmation_version",
        "approved_at",
    }:
        raise ValueError("Requirements approval fields are invalid")
    return CustomerRequirementsApproval(
        value["approval_id"],
        value["customer_id"],
        value["request_id"],
        value["draft_id"],
        value["draft_revision"],
        value["source_request_digest"],
        value["requirements_digest"],
        value["confirmation_version"],
        datetime.fromisoformat(value["approved_at"]),
    )
