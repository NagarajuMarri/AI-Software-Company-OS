"""Canonical write-once persistence for Day 34 preview artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.preview_deployment.errors import (
    PreviewDeploymentConflict,
    PreviewDeploymentCorrupt,
    PreviewDeploymentNotFound,
)
from runtime.preview_deployment.models import (
    PreviewDeploymentArtifact,
    PreviewHealthReceipt,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "preview-deployment-v1.json"
_MAX_BYTES = 256_000
_ARTIFACT_FIELDS = {item.name for item in fields(PreviewDeploymentArtifact)}
_HEALTH_FIELDS = {item.name for item in fields(PreviewHealthReceipt)}


class FilePreviewDeploymentArtifactStore:
    """Tenant/execution-scoped closed preview store with mode-0600 records."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Preview artifact root must be a Path")
        self._root = root

    def save(self, artifact: PreviewDeploymentArtifact) -> PreviewDeploymentArtifact:
        if not isinstance(artifact, PreviewDeploymentArtifact):
            raise TypeError("Preview deployment artifact is invalid")
        directory = self._execution_directory(artifact.tenant_id, artifact.execution_id)
        self._ensure_directory(directory)
        path = directory / _FILENAME
        record = _record(artifact)
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "digest": artifact.digest,
            "record": record,
        }
        content = canonical_json(envelope).encode("utf-8")
        if len(content) > _MAX_BYTES:
            raise PreviewDeploymentConflict("Preview artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise PreviewDeploymentConflict(
                    "Preview execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> PreviewDeploymentArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise PreviewDeploymentCorrupt("Preview artifact file is unsafe")
        if not path.exists():
            raise PreviewDeploymentNotFound("Preview artifact was not found")
        self._validate_directory(directory)
        try:
            content = self._read_file(path)
            if len(content) > _MAX_BYTES:
                raise ValueError("record is too large")
            envelope = json.loads(content)
            record = envelope.get("record") if isinstance(envelope, dict) else None
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(record, dict)
                or set(record) != _ARTIFACT_FIELDS
                or not isinstance(record["health_receipts"], list)
                or any(
                    not isinstance(item, dict) or set(item) != _HEALTH_FIELDS
                    for item in record["health_receipts"]
                )
            ):
                raise ValueError("preview envelope is invalid")
            artifact = _artifact(record)
            if artifact.digest != envelope["digest"]:
                raise ValueError("digest does not match")
            if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
                raise ValueError("path identity does not match")
            if content != canonical_json(envelope).encode("utf-8"):
                raise ValueError("record is not canonical")
            return artifact
        except PreviewDeploymentCorrupt:
            raise
        except Exception as error:
            raise PreviewDeploymentCorrupt("Preview deployment artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise PreviewDeploymentCorrupt(f"Preview {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise PreviewDeploymentCorrupt("Preview artifact path escaped its root") from error
        return target

    def _ensure_directory(self, directory: Path) -> None:
        current = self._root.absolute()
        current.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._require_real_directory(current)
        for component in directory.relative_to(current).parts:
            current = current / component
            current.mkdir(exist_ok=True, mode=0o700)
            self._require_real_directory(current)
        self._require_closed(directory, allow_missing=True)

    def _validate_directory(self, directory: Path) -> None:
        root = self._root.absolute()
        self._require_real_directory(root)
        current = root
        for component in directory.relative_to(root).parts:
            current = current / component
            self._require_real_directory(current)
        self._require_closed(directory, allow_missing=False)

    @staticmethod
    def _require_real_directory(path: Path) -> None:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise PreviewDeploymentNotFound("Preview directory was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise PreviewDeploymentCorrupt("Preview directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing and entries != {_FILENAME}):
            raise PreviewDeploymentCorrupt("Preview artifact directory is not closed")

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise PreviewDeploymentCorrupt("Preview artifact file is unsafe") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise PreviewDeploymentCorrupt("Preview artifact file is unsafe")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: PreviewDeploymentArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["generated_at"] = value.generated_at.isoformat()
    payload["expires_at"] = value.expires_at.isoformat()
    for record, receipt in zip(payload["health_receipts"], value.health_receipts, strict=True):
        record["checked_at"] = receipt.checked_at.isoformat()
    return payload


def _artifact(value: dict) -> PreviewDeploymentArtifact:
    payload = dict(value)
    payload["capability_ids"] = tuple(payload["capability_ids"])
    payload["action_ids"] = tuple(payload["action_ids"])
    payload["tool_ids"] = tuple(payload["tool_ids"])
    payload["health_receipts"] = tuple(
        PreviewHealthReceipt(
            check_id=item["check_id"],
            url=item["url"],
            status_code=item["status_code"],
            response_digest=item["response_digest"],
            checked_at=datetime.fromisoformat(item["checked_at"]),
        )
        for item in payload["health_receipts"]
    )
    payload["generated_at"] = datetime.fromisoformat(payload["generated_at"])
    payload["expires_at"] = datetime.fromisoformat(payload["expires_at"])
    return PreviewDeploymentArtifact(**payload)
