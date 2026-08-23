"""Canonical write-once persistence for Day 36 product-pilot artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.end_to_end_product_pilot.errors import (
    ProductPilotConflict,
    ProductPilotCorrupt,
    ProductPilotNotFound,
)
from runtime.end_to_end_product_pilot.models import (
    EndToEndProductPilotArtifact,
    ProductPilotStageReceipt,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "end-to-end-product-pilot-v1.json"
_MAX_BYTES = 512_000
_ARTIFACT_FIELDS = {item.name for item in fields(EndToEndProductPilotArtifact)}
_RECEIPT_FIELDS = {item.name for item in fields(ProductPilotStageReceipt)}


class FileEndToEndProductPilotArtifactStore:
    """Tenant/execution-scoped closed store with mode-0600 immutable records."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Product-pilot artifact root must be a Path")
        self._root = root

    def save(self, artifact: EndToEndProductPilotArtifact) -> EndToEndProductPilotArtifact:
        if not isinstance(artifact, EndToEndProductPilotArtifact):
            raise TypeError("Product-pilot artifact is invalid")
        directory = self._execution_directory(artifact.tenant_id, artifact.execution_id)
        self._ensure_directory(directory)
        path = directory / _FILENAME
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "digest": artifact.digest,
            "record": _record(artifact),
        }
        content = canonical_json(envelope).encode()
        if len(content) > _MAX_BYTES:
            raise ProductPilotConflict("Product-pilot artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise ProductPilotConflict(
                    "Product-pilot execution already has a different artifact"
                )
            return existing
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return artifact

    def load(self, tenant_id: str, execution_id: str) -> EndToEndProductPilotArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise ProductPilotCorrupt("Product-pilot artifact file is unsafe")
        if not path.exists():
            raise ProductPilotNotFound("Product-pilot artifact was not found")
        self._validate_directory(directory)
        try:
            details = path.lstat()
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise ValueError("artifact permissions are unsafe")
            content = path.read_bytes()
            if len(content) > _MAX_BYTES:
                raise ValueError("artifact is too large")
            envelope = json.loads(content)
            record = envelope.get("record") if isinstance(envelope, dict) else None
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(record, dict)
                or set(record) != _ARTIFACT_FIELDS
                or not isinstance(record["stage_receipts"], list)
                or any(
                    not isinstance(item, dict) or set(item) != _RECEIPT_FIELDS
                    for item in record["stage_receipts"]
                )
            ):
                raise ValueError("product-pilot envelope is invalid")
            artifact = _artifact(record)
            if artifact.digest != envelope["digest"]:
                raise ValueError("artifact digest does not match")
            if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
                raise ValueError("artifact path identity does not match")
            if content != canonical_json(envelope).encode():
                raise ValueError("artifact is not canonical")
            return artifact
        except ProductPilotCorrupt:
            raise
        except Exception as error:
            raise ProductPilotCorrupt("Product-pilot artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str) or not value or value in {".", ".."}
                or "/" in value or "\\" in value
            ):
                raise ProductPilotCorrupt(f"Product-pilot {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ProductPilotCorrupt("Product-pilot path escaped its root") from error
        return target

    def _ensure_directory(self, directory: Path) -> None:
        current = self._root.absolute()
        current.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._require_directory(current)
        for component in directory.relative_to(current).parts:
            current = current / component
            current.mkdir(exist_ok=True, mode=0o700)
            self._require_directory(current)
        self._require_closed(directory, allow_missing=True)

    def _validate_directory(self, directory: Path) -> None:
        root = self._root.absolute()
        self._require_directory(root)
        current = root
        for component in directory.relative_to(root).parts:
            current = current / component
            self._require_directory(current)
        self._require_closed(directory, allow_missing=False)

    @staticmethod
    def _require_directory(path: Path) -> None:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise ProductPilotNotFound("Product-pilot directory was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise ProductPilotCorrupt("Product-pilot directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing and entries != {_FILENAME}):
            raise ProductPilotCorrupt("Product-pilot artifact directory is not closed")


def _record(artifact: EndToEndProductPilotArtifact) -> dict[str, object]:
    record = asdict(artifact)
    record["generated_at"] = artifact.generated_at.isoformat()
    record["expires_at"] = artifact.expires_at.isoformat()
    for target, receipt in zip(record["stage_receipts"], artifact.stage_receipts, strict=True):
        target["completed_at"] = receipt.completed_at.isoformat()
    return record


def _artifact(record: dict) -> EndToEndProductPilotArtifact:
    values = dict(record)
    values["stage_receipts"] = tuple(
        ProductPilotStageReceipt(
            stage_id=item["stage_id"],
            source_digest=item["source_digest"],
            state=item["state"],
            evidence_count=item["evidence_count"],
            completed_at=datetime.fromisoformat(item["completed_at"]),
        )
        for item in values["stage_receipts"]
    )
    for name in (
        "journey_ids", "governance_capability_ids", "action_ids", "tool_ids"
    ):
        values[name] = tuple(values[name])
    values["generated_at"] = datetime.fromisoformat(values["generated_at"])
    values["expires_at"] = datetime.fromisoformat(values["expires_at"])
    return EndToEndProductPilotArtifact(**values)
