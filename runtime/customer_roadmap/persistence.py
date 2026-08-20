"""Write-once canonical persistence for customer roadmap drafts."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_prd import ids_for, prd_approval_id_for
from runtime.customer_roadmap.errors import (
    CustomerRoadmapConflict,
    CustomerRoadmapCorrupt,
    CustomerRoadmapNotFound,
)
from runtime.customer_roadmap.models import (
    CustomerRoadmapDraft,
    CustomerRoadmapMilestone,
    roadmap_id_for,
)
from runtime.product_requirements import RequirementPriority


_SCHEMA_VERSION = 1


class FileCustomerRoadmapStore:
    """Persist exactly one immutable roadmap draft per customer product request."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerRoadmapDraft) -> CustomerRoadmapDraft:
        path = self._path(value.customer_id, value.request_id)
        try:
            _exclusive_write(path, _encode(value))
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise CustomerRoadmapConflict(
                "A different customer roadmap draft already exists"
            ) from None
        return value

    def find(self, customer_id: str, request_id: str) -> CustomerRoadmapDraft | None:
        path = self._path(customer_id, request_id)
        if path.is_symlink():
            raise CustomerRoadmapCorrupt("Customer roadmap file is unsafe")
        if not path.exists():
            return None
        return self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerRoadmapDraft:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerRoadmapCorrupt("Customer roadmap file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerRoadmapNotFound("Customer roadmap draft does not exist") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid customer roadmap envelope")
            value = _from_record(envelope["record"])
            _, product_id, prd_id = ids_for(request_id)
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.roadmap_id != roadmap_id_for(request_id)
                or value.product_id != product_id
                or value.prd_id != prd_id
                or value.prd_approval_id != prd_approval_id_for(request_id)
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Customer roadmap authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerRoadmapCorrupt("Customer roadmap authority is corrupt") from error

    def _path(self, customer_id: str, request_id: str) -> Path:
        roadmap_id_for(customer_id)
        roadmap_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerRoadmapCorrupt("Customer roadmap path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerRoadmapCorrupt("Customer roadmap path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerRoadmapCorrupt("Customer roadmap directory is unsafe")
            if any(entry.name != "roadmap-v0.1.json" for entry in directory.iterdir()):
                raise CustomerRoadmapCorrupt("Customer roadmap directory is not closed")
        return directory / "roadmap-v0.1.json"


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


def _record(value: CustomerRoadmapDraft) -> dict[str, object]:
    return {
        "roadmap_id": value.roadmap_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "product_id": value.product_id,
        "prd_id": value.prd_id,
        "prd_version": value.prd_version,
        "source_request_digest": value.source_request_digest,
        "requirements_digest": value.requirements_digest,
        "requirements_approval_digest": value.requirements_approval_digest,
        "prd_digest": value.prd_digest,
        "prd_approval_id": value.prd_approval_id,
        "prd_approval_digest": value.prd_approval_digest,
        "generation_profile": value.generation_profile,
        "title": value.title,
        "milestones": [
            {
                "roadmap_item_id": item.roadmap_item_id,
                "milestone": item.milestone,
                "sequence": item.sequence,
                "requirement_ids": list(item.requirement_ids),
                "priorities": [priority.value for priority in item.priorities],
                "status": item.status,
            }
            for item in value.milestones
        ],
        "generated_at": value.generated_at.isoformat(),
        "status": value.status,
    }


def _encode(value: CustomerRoadmapDraft) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerRoadmapDraft:
    if set(value) != {
        "roadmap_id",
        "customer_id",
        "request_id",
        "product_id",
        "prd_id",
        "prd_version",
        "source_request_digest",
        "requirements_digest",
        "requirements_approval_digest",
        "prd_digest",
        "prd_approval_id",
        "prd_approval_digest",
        "generation_profile",
        "title",
        "milestones",
        "generated_at",
        "status",
    }:
        raise ValueError("Customer roadmap fields are invalid")
    return CustomerRoadmapDraft(
        value["roadmap_id"],
        value["customer_id"],
        value["request_id"],
        value["product_id"],
        value["prd_id"],
        value["prd_version"],
        value["source_request_digest"],
        value["requirements_digest"],
        value["requirements_approval_digest"],
        value["prd_digest"],
        value["prd_approval_id"],
        value["prd_approval_digest"],
        value["generation_profile"],
        value["title"],
        tuple(_milestone(item) for item in value["milestones"]),
        datetime.fromisoformat(value["generated_at"]),
        value["status"],
    )


def _milestone(value: dict[str, Any]) -> CustomerRoadmapMilestone:
    if set(value) != {
        "roadmap_item_id",
        "milestone",
        "sequence",
        "requirement_ids",
        "priorities",
        "status",
    }:
        raise ValueError("Customer roadmap milestone fields are invalid")
    return CustomerRoadmapMilestone(
        value["roadmap_item_id"],
        value["milestone"],
        value["sequence"],
        tuple(value["requirement_ids"]),
        tuple(RequirementPriority(priority) for priority in value["priorities"]),
        value["status"],
    )
