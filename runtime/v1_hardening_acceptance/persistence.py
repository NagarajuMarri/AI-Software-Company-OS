"""Restrictive primary/backup persistence for Day 37 acceptance evidence."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import stat
import uuid

from runtime.v1_hardening_acceptance.errors import (
    V1HardeningConflict,
    V1HardeningCorrupt,
    V1HardeningNotFound,
)
from runtime.v1_hardening_acceptance.models import (
    HardeningControlReceipt,
    MonitoringSignalReceipt,
    V1HardeningAcceptanceArtifact,
    canonical_digest,
)


_PRIMARY = "v1-hardening-acceptance-v1.json"
_BACKUP = "v1-hardening-acceptance-v1.backup.json"
_EXPECTED = {_PRIMARY, _BACKUP}


class FileV1HardeningAcceptanceArtifactStore:
    """Store a canonical artifact plus one verified recovery copy."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, artifact: V1HardeningAcceptanceArtifact) -> V1HardeningAcceptanceArtifact:
        directory = self._directory(artifact.tenant_id, artifact.execution_id)
        self._ensure_directory(directory)
        primary = directory / _PRIMARY
        backup = directory / _BACKUP
        if primary.exists() or backup.exists():
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing == artifact:
                return existing
            raise V1HardeningConflict("Day 37 artifact is immutable")
        payload = _payload(artifact)
        self._write(primary, payload)
        self._write(backup, payload)
        self._require_closed(directory, allow_primary_missing=False)
        self.verify_backup(artifact)
        return artifact

    def load(self, tenant_id: str, execution_id: str) -> V1HardeningAcceptanceArtifact:
        directory = self._directory(tenant_id, execution_id)
        self._require_directory(directory)
        self._require_closed(directory, allow_primary_missing=False)
        primary_bytes = self._read(directory / _PRIMARY)
        backup_bytes = self._read(directory / _BACKUP)
        if primary_bytes != backup_bytes:
            raise V1HardeningCorrupt("Day 37 primary and backup artifacts differ")
        artifact = _decode(primary_bytes)
        if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
            raise V1HardeningCorrupt("Day 37 artifact identity changed")
        return artifact

    def find(self, tenant_id: str, execution_id: str) -> V1HardeningAcceptanceArtifact | None:
        try:
            return self.load(tenant_id, execution_id)
        except V1HardeningNotFound:
            return None

    def verify_backup(self, artifact: V1HardeningAcceptanceArtifact) -> None:
        directory = self._directory(artifact.tenant_id, artifact.execution_id)
        recovered = _decode(self._read(directory / _BACKUP))
        if recovered != artifact:
            raise V1HardeningCorrupt("Day 37 backup verification failed")

    def recover(self, tenant_id: str, execution_id: str) -> V1HardeningAcceptanceArtifact:
        """Explicitly restore a missing or corrupt regular primary from the verified backup."""
        directory = self._directory(tenant_id, execution_id)
        self._require_directory(directory)
        self._require_closed(directory, allow_primary_missing=True)
        backup_bytes = self._read(directory / _BACKUP)
        artifact = _decode(backup_bytes)
        if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
            raise V1HardeningCorrupt("Day 37 backup identity changed")
        primary = directory / _PRIMARY
        if primary.exists() and primary.is_symlink():
            raise V1HardeningCorrupt("Day 37 primary artifact is unsafe")
        self._write(primary, backup_bytes, replace=True)
        return self.load(tenant_id, execution_id)

    def _directory(self, tenant_id: str, execution_id: str) -> Path:
        for value in (tenant_id, execution_id):
            if not value or any(
                character
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-"
                for character in value
            ):
                raise V1HardeningCorrupt("Day 37 storage identity is unsafe")
        candidate = self.root / tenant_id / execution_id
        try:
            candidate.resolve(strict=False).relative_to(self.root.resolve(strict=False))
        except ValueError as error:
            raise V1HardeningCorrupt("Day 37 storage path escaped its root") from error
        return candidate

    def _ensure_directory(self, directory: Path) -> None:
        current = self.root
        for part in directory.relative_to(self.root).parts:
            current.mkdir(mode=0o700, parents=False, exist_ok=True)
            self._require_directory(current)
            try:
                os.chmod(current, 0o700)
            except OSError as error:
                raise V1HardeningCorrupt("Day 37 directory permissions are unsafe") from error
            current = current / part
        current.mkdir(mode=0o700, parents=False, exist_ok=True)
        self._require_directory(current)
        os.chmod(current, 0o700)

    @staticmethod
    def _write(path: Path, payload: bytes, *, replace: bool = False) -> None:
        temporary = path.parent / f".day37-{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            if path.exists() and not replace:
                raise V1HardeningConflict("Day 37 artifact is immutable")
            os.replace(temporary, path)
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _read(path: Path) -> bytes:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise V1HardeningNotFound("Day 37 artifact was not found") from error
        if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise V1HardeningCorrupt("Day 37 artifact is unsafe")
        if stat.S_IMODE(details.st_mode) != 0o600:
            raise V1HardeningCorrupt("Day 37 artifact permissions are unsafe")
        return path.read_bytes()

    @staticmethod
    def _require_directory(path: Path) -> None:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise V1HardeningNotFound("Day 37 artifact directory was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise V1HardeningCorrupt("Day 37 artifact directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_primary_missing: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        allowed = _EXPECTED if not allow_primary_missing else (_EXPECTED | {_BACKUP})
        required = {_BACKUP} if allow_primary_missing else _EXPECTED
        if not required <= entries or not entries <= allowed:
            raise V1HardeningCorrupt("Day 37 artifact directory is not closed")


def _payload(artifact: V1HardeningAcceptanceArtifact) -> bytes:
    record = asdict(artifact)
    record["generated_at"] = artifact.generated_at.isoformat()
    record["expires_at"] = artifact.expires_at.isoformat()
    for item, control_receipt in zip(
        record["control_receipts"], artifact.control_receipts, strict=True
    ):
        item["verified_at"] = control_receipt.verified_at.isoformat()
    for item, monitoring_receipt in zip(
        record["monitoring_receipts"], artifact.monitoring_receipts, strict=True
    ):
        item["observed_at"] = monitoring_receipt.observed_at.isoformat()
    envelope = {"schema_version": 1, "record": record, "record_digest": canonical_digest(record)}
    return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()


def _decode(payload: bytes) -> V1HardeningAcceptanceArtifact:
    try:
        envelope = json.loads(payload)
        if (
            set(envelope) != {"schema_version", "record", "record_digest"}
            or envelope["schema_version"] != 1
        ):
            raise ValueError("schema")
        record = envelope["record"]
        if envelope["record_digest"] != canonical_digest(record):
            raise ValueError("digest")
        values = dict(record)
        values["control_receipts"] = tuple(
            HardeningControlReceipt(
                control_id=item["control_id"],
                source_digest=item["source_digest"],
                state=item["state"],
                evidence_ids=tuple(item["evidence_ids"]),
                verified_at=datetime.fromisoformat(item["verified_at"]),
                previous_audit_digest=item["previous_audit_digest"],
                audit_digest=item["audit_digest"],
            )
            for item in values["control_receipts"]
        )
        values["monitoring_receipts"] = tuple(
            MonitoringSignalReceipt(
                signal_id=item["signal_id"],
                state=item["state"],
                evidence_digest=item["evidence_digest"],
                observed_at=datetime.fromisoformat(item["observed_at"]),
            )
            for item in values["monitoring_receipts"]
        )
        for name in (
            "journey_ids",
            "documentation_ids",
            "governance_capability_ids",
            "action_ids",
            "tool_ids",
        ):
            values[name] = tuple(values[name])
        values["generated_at"] = datetime.fromisoformat(values["generated_at"])
        values["expires_at"] = datetime.fromisoformat(values["expires_at"])
        return V1HardeningAcceptanceArtifact(**values)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise V1HardeningCorrupt("Day 37 artifact is corrupt") from error
