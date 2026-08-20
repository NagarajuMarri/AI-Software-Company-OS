"""Write-once canonical persistence for customer PRD drafts."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_prd.errors import CustomerPrdConflict, CustomerPrdCorrupt, CustomerPrdNotFound
from runtime.customer_prd.models import (
    CustomerPrdDraft,
    CustomerPrdRequirement,
    ids_for,
)
from runtime.customer_requirements import DataSensitivity, DeliveryPriority
from runtime.product_requirements import RequirementCategory, RequirementPriority


_SCHEMA_VERSION = 1


class FileCustomerPrdStore:
    """Persist exactly one immutable PRD draft per customer product request."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerPrdDraft) -> CustomerPrdDraft:
        path = self._path(value.customer_id, value.request_id)
        try:
            _exclusive_write(path, _encode(value))
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise CustomerPrdConflict("A different customer PRD draft already exists") from None
        return value

    def find(self, customer_id: str, request_id: str) -> CustomerPrdDraft | None:
        path = self._path(customer_id, request_id)
        if path.is_symlink():
            raise CustomerPrdCorrupt("Customer PRD file is unsafe")
        if not path.exists():
            return None
        return self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerPrdDraft:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerPrdCorrupt("Customer PRD file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerPrdNotFound("Customer PRD draft does not exist") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid customer PRD envelope")
            value = _from_record(envelope["record"])
            artifact_id, product_id, prd_id = ids_for(request_id)
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.artifact_id != artifact_id
                or value.product_id != product_id
                or value.prd_id != prd_id
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Customer PRD authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerPrdCorrupt("Customer PRD authority is corrupt") from error

    def _path(self, customer_id: str, request_id: str) -> Path:
        ids_for(customer_id)
        ids_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerPrdCorrupt("Customer PRD path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerPrdCorrupt("Customer PRD path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerPrdCorrupt("Customer PRD directory is unsafe")
            entries = tuple(directory.iterdir())
            if any(entry.name != "prd-v0.1.json" for entry in entries):
                raise CustomerPrdCorrupt("Customer PRD directory is not closed")
        return directory / "prd-v0.1.json"


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


def _record(value: CustomerPrdDraft) -> dict[str, object]:
    return {
        "artifact_id": value.artifact_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "product_id": value.product_id,
        "prd_id": value.prd_id,
        "version": value.version,
        "generation_profile": value.generation_profile,
        "source_request_digest": value.source_request_digest,
        "requirements_digest": value.requirements_digest,
        "approval_digest": value.approval_digest,
        "title": value.title,
        "problem_statement": value.problem_statement,
        "target_users": value.target_users,
        "primary_user_journey": value.primary_user_journey,
        "requirements": [
            {
                "requirement_id": item.requirement_id,
                "title": item.title,
                "description": item.description,
                "acceptance_criteria": list(item.acceptance_criteria),
                "category": item.category.value,
                "priority": item.priority.value,
                "source_reference": item.source_reference,
            }
            for item in value.requirements
        ],
        "success_metrics": list(value.success_metrics),
        "explicit_exclusions": list(value.explicit_exclusions),
        "platforms": list(value.platforms),
        "data_sensitivity": value.data_sensitivity.value,
        "delivery_priority": value.delivery_priority.value,
        "generated_at": value.generated_at.isoformat(),
    }


def _encode(value: CustomerPrdDraft) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerPrdDraft:
    if set(value) != {
        "artifact_id",
        "customer_id",
        "request_id",
        "product_id",
        "prd_id",
        "version",
        "generation_profile",
        "source_request_digest",
        "requirements_digest",
        "approval_digest",
        "title",
        "problem_statement",
        "target_users",
        "primary_user_journey",
        "requirements",
        "success_metrics",
        "explicit_exclusions",
        "platforms",
        "data_sensitivity",
        "delivery_priority",
        "generated_at",
    }:
        raise ValueError("Customer PRD fields are invalid")
    requirements = tuple(_requirement(item) for item in value["requirements"])
    return CustomerPrdDraft(
        value["artifact_id"],
        value["customer_id"],
        value["request_id"],
        value["product_id"],
        value["prd_id"],
        value["version"],
        value["generation_profile"],
        value["source_request_digest"],
        value["requirements_digest"],
        value["approval_digest"],
        value["title"],
        value["problem_statement"],
        value["target_users"],
        value["primary_user_journey"],
        requirements,
        tuple(value["success_metrics"]),
        tuple(value["explicit_exclusions"]),
        tuple(value["platforms"]),
        DataSensitivity(value["data_sensitivity"]),
        DeliveryPriority(value["delivery_priority"]),
        datetime.fromisoformat(value["generated_at"]),
    )


def _requirement(value: dict[str, Any]) -> CustomerPrdRequirement:
    if set(value) != {
        "requirement_id",
        "title",
        "description",
        "acceptance_criteria",
        "category",
        "priority",
        "source_reference",
    }:
        raise ValueError("Customer PRD requirement fields are invalid")
    return CustomerPrdRequirement(
        value["requirement_id"],
        value["title"],
        value["description"],
        tuple(value["acceptance_criteria"]),
        RequirementCategory(value["category"]),
        RequirementPriority(value["priority"]),
        value["source_reference"],
    )
