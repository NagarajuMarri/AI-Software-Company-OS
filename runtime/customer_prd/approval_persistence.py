"""Write-once canonical persistence for customer PRD approval receipts."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_prd.approval_models import (
    CustomerPrdApproval,
    prd_approval_id_for,
)
from runtime.customer_prd.errors import (
    CustomerPrdApprovalConflict,
    CustomerPrdApprovalCorrupt,
    CustomerPrdApprovalNotFound,
)
from runtime.customer_prd.models import ids_for


_SCHEMA_VERSION = 1


class FileCustomerPrdApprovalStore:
    """Persist exactly one locked-PRD receipt per customer product request."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerPrdApproval) -> CustomerPrdApproval:
        path = self._path(value.customer_id, value.request_id)
        try:
            _exclusive_write(path, _encode(value))
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise CustomerPrdApprovalConflict(
                "A different customer PRD approval already exists"
            ) from None
        return value

    def find(self, customer_id: str, request_id: str) -> CustomerPrdApproval | None:
        path = self._path(customer_id, request_id)
        if path.is_symlink():
            raise CustomerPrdApprovalCorrupt("Customer PRD approval file is unsafe")
        if not path.exists():
            return None
        return self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerPrdApproval:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerPrdApprovalCorrupt("Customer PRD approval file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerPrdApprovalNotFound(
                "Customer PRD approval does not exist"
            ) from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid customer PRD approval envelope")
            value = _from_record(envelope["record"])
            artifact_id, product_id, prd_id = ids_for(request_id)
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.approval_id != prd_approval_id_for(request_id)
                or value.artifact_id != artifact_id
                or value.product_id != product_id
                or value.prd_id != prd_id
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Customer PRD approval authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerPrdApprovalCorrupt(
                "Customer PRD approval authority is corrupt"
            ) from error

    def is_locked(self, customer_id: str, request_id: str) -> bool:
        return self.find(customer_id, request_id) is not None

    def _path(self, customer_id: str, request_id: str) -> Path:
        prd_approval_id_for(customer_id)
        prd_approval_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerPrdApprovalCorrupt("Customer PRD approval path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerPrdApprovalCorrupt(
                "Customer PRD approval path escaped its store"
            )
        if directory.exists():
            if not directory.is_dir():
                raise CustomerPrdApprovalCorrupt("Customer PRD approval directory is unsafe")
            entries = tuple(directory.iterdir())
            if any(entry.name != "prd-approval-v0.1.json" for entry in entries):
                raise CustomerPrdApprovalCorrupt(
                    "Customer PRD approval directory is not closed"
                )
        return directory / "prd-approval-v0.1.json"


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


def _record(value: CustomerPrdApproval) -> dict[str, object]:
    return {
        "approval_id": value.approval_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "artifact_id": value.artifact_id,
        "product_id": value.product_id,
        "prd_id": value.prd_id,
        "prd_version": value.prd_version,
        "source_request_digest": value.source_request_digest,
        "requirements_digest": value.requirements_digest,
        "requirements_approval_digest": value.requirements_approval_digest,
        "prd_digest": value.prd_digest,
        "confirmation_version": value.confirmation_version,
        "approved_at": value.approved_at.isoformat(),
    }


def _encode(value: CustomerPrdApproval) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerPrdApproval:
    if set(value) != {
        "approval_id",
        "customer_id",
        "request_id",
        "artifact_id",
        "product_id",
        "prd_id",
        "prd_version",
        "source_request_digest",
        "requirements_digest",
        "requirements_approval_digest",
        "prd_digest",
        "confirmation_version",
        "approved_at",
    }:
        raise ValueError("Customer PRD approval fields are invalid")
    return CustomerPrdApproval(
        value["approval_id"],
        value["customer_id"],
        value["request_id"],
        value["artifact_id"],
        value["product_id"],
        value["prd_id"],
        value["prd_version"],
        value["source_request_digest"],
        value["requirements_digest"],
        value["requirements_approval_digest"],
        value["prd_digest"],
        value["confirmation_version"],
        datetime.fromisoformat(value["approved_at"]),
    )
