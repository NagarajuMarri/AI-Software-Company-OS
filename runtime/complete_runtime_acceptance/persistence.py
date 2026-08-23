"""Canonical write-once persistence for Day 35 runtime-acceptance artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.complete_runtime_acceptance.errors import (
    RuntimeAcceptanceConflict,
    RuntimeAcceptanceCorrupt,
    RuntimeAcceptanceNotFound,
)
from runtime.complete_runtime_acceptance.models import (
    CompleteRuntimeAcceptanceArtifact,
    RuntimeJourneyReceipt,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "complete-runtime-acceptance-v1.json"
_MAX_BYTES = 512_000
_ARTIFACT_FIELDS = {item.name for item in fields(CompleteRuntimeAcceptanceArtifact)}
_RECEIPT_FIELDS = {item.name for item in fields(RuntimeJourneyReceipt)}


class FileCompleteRuntimeAcceptanceArtifactStore:
    """Tenant/execution-scoped closed store with mode-0600 immutable records."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Runtime-acceptance artifact root must be a Path")
        self._root = root

    def save(
        self, artifact: CompleteRuntimeAcceptanceArtifact
    ) -> CompleteRuntimeAcceptanceArtifact:
        if not isinstance(artifact, CompleteRuntimeAcceptanceArtifact):
            raise TypeError("Complete runtime-acceptance artifact is invalid")
        directory = self._execution_directory(artifact.tenant_id, artifact.execution_id)
        self._ensure_directory(directory)
        path = directory / _FILENAME
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "digest": artifact.digest,
            "record": _record(artifact),
        }
        content = canonical_json(envelope).encode("utf-8")
        if len(content) > _MAX_BYTES:
            raise RuntimeAcceptanceConflict("Runtime-acceptance artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise RuntimeAcceptanceConflict(
                    "Runtime-acceptance execution already has a different artifact"
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

    def load(
        self, tenant_id: str, execution_id: str
    ) -> CompleteRuntimeAcceptanceArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise RuntimeAcceptanceCorrupt("Runtime-acceptance artifact file is unsafe")
        if not path.exists():
            raise RuntimeAcceptanceNotFound("Runtime-acceptance artifact was not found")
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
                or not isinstance(record["journey_receipts"], list)
                or any(
                    not isinstance(item, dict) or set(item) != _RECEIPT_FIELDS
                    for item in record["journey_receipts"]
                )
            ):
                raise ValueError("runtime-acceptance envelope is invalid")
            artifact = _artifact(record)
            if artifact.digest != envelope["digest"]:
                raise ValueError("digest does not match")
            if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
                raise ValueError("path identity does not match")
            if content != canonical_json(envelope).encode("utf-8"):
                raise ValueError("record is not canonical")
            return artifact
        except RuntimeAcceptanceCorrupt:
            raise
        except Exception as error:
            raise RuntimeAcceptanceCorrupt(
                "Complete runtime-acceptance artifact is corrupt"
            ) from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise RuntimeAcceptanceCorrupt(
                    f"Runtime-acceptance {label} path is invalid"
                )
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise RuntimeAcceptanceCorrupt(
                "Runtime-acceptance artifact path escaped its root"
            ) from error
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
            raise RuntimeAcceptanceNotFound(
                "Runtime-acceptance directory was not found"
            ) from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise RuntimeAcceptanceCorrupt("Runtime-acceptance directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing and entries != {_FILENAME}):
            raise RuntimeAcceptanceCorrupt(
                "Runtime-acceptance artifact directory is not closed"
            )

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise RuntimeAcceptanceCorrupt(
                "Runtime-acceptance artifact file is unsafe"
            ) from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise RuntimeAcceptanceCorrupt(
                    "Runtime-acceptance artifact file is unsafe"
                )
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: CompleteRuntimeAcceptanceArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["generated_at"] = value.generated_at.isoformat()
    payload["expires_at"] = value.expires_at.isoformat()
    for record, receipt in zip(
        payload["journey_receipts"], value.journey_receipts, strict=True
    ):
        record["completed_at"] = receipt.completed_at.isoformat()
    return payload


def _artifact(value: dict) -> CompleteRuntimeAcceptanceArtifact:
    payload = dict(value)
    for name in (
        "capability_ids",
        "journey_ids",
        "governance_capability_ids",
        "action_ids",
        "tool_ids",
    ):
        payload[name] = tuple(payload[name])
    payload["journey_receipts"] = tuple(
        RuntimeJourneyReceipt(
            journey_id=item["journey_id"],
            capability_id=item["capability_id"],
            title=item["title"],
            outcome=item["outcome"],
            evidence_count=item["evidence_count"],
            evidence_digest=item["evidence_digest"],
            screenshot_digest=item["screenshot_digest"],
            completed_at=datetime.fromisoformat(item["completed_at"]),
        )
        for item in payload["journey_receipts"]
    )
    payload["generated_at"] = datetime.fromisoformat(payload["generated_at"])
    payload["expires_at"] = datetime.fromisoformat(payload["expires_at"])
    return CompleteRuntimeAcceptanceArtifact(**payload)
