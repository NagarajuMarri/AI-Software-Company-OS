"""Revisioned, integrity-checked customer requirements persistence."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any

from runtime.customer_requirements.errors import (
    RequirementsDraftConflict,
    RequirementsDraftCorrupt,
    RequirementsDraftNotFound,
)
from runtime.customer_requirements.models import (
    CustomerRequirementsDraft,
    DataSensitivity,
    DeliveryPriority,
    draft_id_for,
)


_SCHEMA_VERSION = 1
_REVISION_FILE = re.compile(r"^revision-([0-9]{6})\.json$")
_MAX_REVISIONS = 1_000


class FileCustomerRequirementsStore:
    """Append immutable draft revisions with optimistic concurrency."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerRequirementsDraft) -> CustomerRequirementsDraft:
        history = self.history(value.customer_id, value.request_id)
        expected = len(history) + 1
        if value.revision != expected:
            raise RequirementsDraftConflict("Requirements revision is stale")
        path = self._path(value.customer_id, value.request_id, value.revision)
        content = _encode(value)
        try:
            _exclusive_write(path, content)
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id, value.revision)
            if existing == value:
                return existing
            raise RequirementsDraftConflict("Requirements revision already exists") from None
        return value

    def load(
        self,
        customer_id: str,
        request_id: str,
        revision: int,
    ) -> CustomerRequirementsDraft:
        path = self._path(customer_id, request_id, revision)
        if path.is_symlink():
            raise RequirementsDraftCorrupt("Requirements revision file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise RequirementsDraftNotFound("Unknown requirements revision") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid requirements envelope")
            value = _from_record(envelope["record"])
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.revision != revision
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Requirements authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RequirementsDraftCorrupt("Requirements draft authority is corrupt") from error

    def latest(self, customer_id: str, request_id: str) -> CustomerRequirementsDraft | None:
        history = self.history(customer_id, request_id)
        return history[-1] if history else None

    def history(
        self,
        customer_id: str,
        request_id: str,
    ) -> tuple[CustomerRequirementsDraft, ...]:
        directory = self._directory(customer_id, request_id)
        if not directory.exists():
            return ()
        if directory.is_symlink():
            raise RequirementsDraftCorrupt("Requirements draft directory is unsafe")
        candidates = sorted(directory.iterdir())
        if len(candidates) > _MAX_REVISIONS:
            raise RequirementsDraftCorrupt("Requirements history exceeds policy")
        revisions: list[int] = []
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                raise RequirementsDraftCorrupt("Requirements history entry is unsafe")
            match = _REVISION_FILE.fullmatch(path.name)
            if match is None:
                raise RequirementsDraftCorrupt("Requirements history entry is unknown")
            revisions.append(int(match.group(1)))
        if revisions != list(range(1, len(revisions) + 1)):
            raise RequirementsDraftCorrupt("Requirements history is non-contiguous")
        return tuple(self.load(customer_id, request_id, revision) for revision in revisions)

    def _directory(self, customer_id: str, request_id: str) -> Path:
        # Reuse the complete model identifier policy without maintaining a second regex.
        _validation_value(customer_id, request_id)
        path = self._root / customer_id / request_id
        parent = path.parent.resolve()
        if self._root not in (parent, *parent.parents):
            raise RequirementsDraftCorrupt("Requirements path escaped its store")
        return path

    def _path(self, customer_id: str, request_id: str, revision: int) -> Path:
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("Requirements revision is invalid")
        return self._directory(customer_id, request_id) / f"revision-{revision:06d}.json"


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


def _record(value: CustomerRequirementsDraft) -> dict[str, object]:
    return {
        "draft_id": value.draft_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "revision": value.revision,
        "source_request_digest": value.source_request_digest,
        "primary_user_journey": value.primary_user_journey,
        "desired_outcomes": list(value.desired_outcomes),
        "must_have_features": list(value.must_have_features),
        "success_metrics": list(value.success_metrics),
        "non_goals": list(value.non_goals),
        "platforms": list(value.platforms),
        "data_sensitivity": value.data_sensitivity.value,
        "delivery_priority": value.delivery_priority.value,
        "updated_at": value.updated_at.isoformat(),
    }


def _encode(value: CustomerRequirementsDraft) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerRequirementsDraft:
    if set(value) != {
        "draft_id",
        "customer_id",
        "request_id",
        "revision",
        "source_request_digest",
        "primary_user_journey",
        "desired_outcomes",
        "must_have_features",
        "success_metrics",
        "non_goals",
        "platforms",
        "data_sensitivity",
        "delivery_priority",
        "updated_at",
    }:
        raise ValueError("Requirements draft fields are invalid")
    return CustomerRequirementsDraft(
        value["draft_id"],
        value["customer_id"],
        value["request_id"],
        value["revision"],
        value["source_request_digest"],
        value["primary_user_journey"],
        tuple(value["desired_outcomes"]),
        tuple(value["must_have_features"]),
        tuple(value["success_metrics"]),
        tuple(value["non_goals"]),
        tuple(value["platforms"]),
        DataSensitivity(value["data_sensitivity"]),
        DeliveryPriority(value["delivery_priority"]),
        datetime.fromisoformat(value["updated_at"]),
    )


def _validation_value(customer_id: str, request_id: str) -> CustomerRequirementsDraft:
    return CustomerRequirementsDraft(
        draft_id_for(request_id),
        customer_id,
        request_id,
        1,
        "0" * 64,
        "A complete primary journey used to validate safe identifiers.",
        ("Validate identifiers",),
        ("Validate identifiers",),
        ("Identifiers remain contained",),
        (),
        ("WEB",),
        DataSensitivity.NO_PERSONAL_DATA,
        DeliveryPriority.STANDARD,
        datetime.fromisoformat("2000-01-01T00:00:00+00:00"),
    )
