"""Write-once canonical persistence for locked PRD criteria refinements."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_prd.criteria_models import (
    CustomerPrdCriteriaEntry,
    CustomerPrdCriteriaRefinement,
    criteria_refinement_id_for,
)
from runtime.customer_prd.errors import (
    CustomerPrdCriteriaConflict,
    CustomerPrdCriteriaCorrupt,
    CustomerPrdCriteriaNotFound,
)


_SCHEMA_VERSION = 1


class FileCustomerPrdCriteriaStore:
    """Persist exactly one locked criteria baseline per customer request."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerPrdCriteriaRefinement) -> CustomerPrdCriteriaRefinement:
        path = self._path(value.customer_id, value.request_id)
        try:
            _exclusive_write(path, _encode(value))
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise CustomerPrdCriteriaConflict(
                "A different customer PRD criteria baseline already exists"
            ) from None
        return value

    def find(
        self,
        customer_id: str,
        request_id: str,
    ) -> CustomerPrdCriteriaRefinement | None:
        path = self._path(customer_id, request_id)
        if path.is_symlink():
            raise CustomerPrdCriteriaCorrupt("Customer PRD criteria file is unsafe")
        if not path.exists():
            return None
        return self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerPrdCriteriaRefinement:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerPrdCriteriaCorrupt("Customer PRD criteria file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerPrdCriteriaNotFound(
                "Customer PRD criteria baseline does not exist"
            ) from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid customer PRD criteria envelope")
            value = _from_record(envelope["record"])
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.refinement_id != criteria_refinement_id_for(request_id)
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Customer PRD criteria authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerPrdCriteriaCorrupt(
                "Customer PRD criteria authority is corrupt"
            ) from error

    def _path(self, customer_id: str, request_id: str) -> Path:
        criteria_refinement_id_for(customer_id)
        criteria_refinement_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerPrdCriteriaCorrupt("Customer PRD criteria path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerPrdCriteriaCorrupt("Customer PRD criteria path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerPrdCriteriaCorrupt("Customer PRD criteria directory is unsafe")
            if any(entry.name != "criteria-v0.1.json" for entry in directory.iterdir()):
                raise CustomerPrdCriteriaCorrupt("Customer PRD criteria directory is not closed")
        return directory / "criteria-v0.1.json"


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


def _encode(value: CustomerPrdCriteriaRefinement) -> bytes:
    record = {
        "refinement_id": value.refinement_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "source_prd_digest": value.source_prd_digest,
        "entries": [
            {
                "requirement_id": item.requirement_id,
                "acceptance_criteria": list(item.acceptance_criteria),
            }
            for item in value.entries
        ],
        "confirmation_version": value.confirmation_version,
        "locked_at": value.locked_at.isoformat(),
    }
    envelope = {"schema_version": _SCHEMA_VERSION, "digest": value.digest, "record": record}
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerPrdCriteriaRefinement:
    if set(value) != {
        "refinement_id",
        "customer_id",
        "request_id",
        "source_prd_digest",
        "entries",
        "confirmation_version",
        "locked_at",
    }:
        raise ValueError("Customer PRD criteria fields are invalid")
    entries = tuple(
        CustomerPrdCriteriaEntry(
            item["requirement_id"],
            tuple(item["acceptance_criteria"]),
        )
        for item in value["entries"]
    )
    return CustomerPrdCriteriaRefinement(
        value["refinement_id"],
        value["customer_id"],
        value["request_id"],
        value["source_prd_digest"],
        entries,
        value["confirmation_version"],
        datetime.fromisoformat(value["locked_at"]),
    )
