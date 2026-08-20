"""Write-once, integrity-checked customer product-request persistence."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_application.errors import (
    ProductRequestConflict,
    ProductRequestCorrupt,
    ProductRequestNotFound,
)
from runtime.customer_application.models import CustomerProductRequest, ProductRequestStage


_SCHEMA_VERSION = 1


class FileCustomerProductRequestStore:
    """Persist customer-scoped requests without mutable drafts or overwrite."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerProductRequest) -> CustomerProductRequest:
        path = self._path(value.customer_id, value.request_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        content = _encode(value)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise ProductRequestConflict(
                "Product request identity already has different immutable content"
            ) from None
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
        return value

    def load(self, customer_id: str, request_id: str) -> CustomerProductRequest:
        path = self._path(customer_id, request_id)
        if path.is_symlink():
            raise ProductRequestCorrupt("Product request file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise ProductRequestNotFound("Unknown customer product request") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid envelope")
            value = _from_record(envelope["record"])
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProductRequestCorrupt("Product request authority is corrupt") from error

    def list_for_customer(self, customer_id: str) -> tuple[CustomerProductRequest, ...]:
        directory = self._path(customer_id, "placeholder").parent
        if not directory.exists():
            return ()
        if directory.is_symlink():
            raise ProductRequestCorrupt("Customer request directory is unsafe")
        values = []
        for path in sorted(directory.glob("*.json")):
            if path.is_symlink():
                raise ProductRequestCorrupt("Customer request file is unsafe")
            values.append(self.load(customer_id, path.stem))
        return tuple(sorted(values, key=lambda item: (item.submitted_at, item.request_id)))

    def _path(self, customer_id: str, request_id: str) -> Path:
        # Domain validation is reused here so path authority cannot bypass the model.
        CustomerProductRequest(
            request_id,
            customer_id,
            "Validation",
            "Validation request used only to verify safe identifiers.",
            "Validation users",
            ("Validate identifiers",),
            (),
            ProductRequestStage.SUBMITTED,
            datetime.fromisoformat("2000-01-01T00:00:00+00:00"),
        )
        path = self._root / customer_id / f"{request_id}.json"
        resolved_parent = path.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise ValueError("Product request path escaped its store")
        return path


def _record(value: CustomerProductRequest) -> dict[str, object]:
    return {
        "request_id": value.request_id,
        "customer_id": value.customer_id,
        "product_name": value.product_name,
        "product_summary": value.product_summary,
        "target_users": value.target_users,
        "features": list(value.features),
        "constraints": list(value.constraints),
        "stage": value.stage.value,
        "submitted_at": value.submitted_at.isoformat(),
    }


def _encode(value: CustomerProductRequest) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerProductRequest:
    if set(value) != {
        "request_id",
        "customer_id",
        "product_name",
        "product_summary",
        "target_users",
        "features",
        "constraints",
        "stage",
        "submitted_at",
    }:
        raise ValueError("Product request fields are invalid")
    return CustomerProductRequest(
        value["request_id"],
        value["customer_id"],
        value["product_name"],
        value["product_summary"],
        value["target_users"],
        tuple(value["features"]),
        tuple(value["constraints"]),
        ProductRequestStage(value["stage"]),
        datetime.fromisoformat(value["submitted_at"]),
    )
