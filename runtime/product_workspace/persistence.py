"""Canonical write-once persistence for Day 31 workspace artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.product_workspace.errors import (
    ProductWorkspaceConflict,
    ProductWorkspaceCorrupt,
    ProductWorkspaceNotFound,
)
from runtime.product_workspace.models import (
    ProductWorkspaceArtifact,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "isolated-product-workspace-v1.json"
_MAX_BYTES = 128_000
_ARTIFACT_FIELDS = {item.name for item in fields(ProductWorkspaceArtifact)}


class FileProductWorkspaceArtifactStore:
    """Tenant/execution-scoped closed store containing no local host path."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Product workspace artifact root must be a Path")
        self._root = root

    def save(self, artifact: ProductWorkspaceArtifact) -> ProductWorkspaceArtifact:
        if not isinstance(artifact, ProductWorkspaceArtifact):
            raise TypeError("Product workspace artifact is invalid")
        directory = self._execution_directory(artifact.tenant_id, artifact.execution_id)
        self._ensure_directory(directory)
        path = directory / _FILENAME
        record = asdict(artifact)
        record["generated_at"] = artifact.generated_at.isoformat()
        envelope = {
            "schema_version": _SCHEMA_VERSION,
            "digest": artifact.digest,
            "record": record,
        }
        content = canonical_json(envelope).encode()
        if len(content) > _MAX_BYTES:
            raise ProductWorkspaceConflict("Product workspace artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise ProductWorkspaceConflict(
                    "Product workspace execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> ProductWorkspaceArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise ProductWorkspaceCorrupt("Product workspace artifact file is unsafe")
        if not path.exists():
            raise ProductWorkspaceNotFound("Product workspace artifact was not found")
        self._validate_directory(directory)
        try:
            content = self._read_file(path)
            if len(content) > _MAX_BYTES:
                raise ValueError("record is too large")
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
                or set(envelope["record"]) != _ARTIFACT_FIELDS
            ):
                raise ValueError("envelope is invalid")
            artifact = _artifact(envelope["record"])
            if artifact.digest != envelope["digest"]:
                raise ValueError("digest does not match")
            if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
                raise ValueError("path identity does not match")
            if content != canonical_json(envelope).encode():
                raise ValueError("record is not canonical")
            return artifact
        except ProductWorkspaceCorrupt:
            raise
        except Exception as error:
            raise ProductWorkspaceCorrupt("Product workspace artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise ProductWorkspaceCorrupt(f"Product workspace {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ProductWorkspaceCorrupt("Product workspace artifact path escaped its root") from error
        return target

    def _ensure_directory(self, directory: Path) -> None:
        current = self._root.absolute()
        current.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._require_real_directory(current)
        for component in directory.relative_to(current).parts:
            current = current / component
            current.mkdir(exist_ok=True, mode=0o700)
            self._require_real_directory(current)
        self._require_closed(directory, allow_missing_file=True)

    def _validate_directory(self, directory: Path) -> None:
        root = self._root.absolute()
        self._require_real_directory(root)
        current = root
        for component in directory.relative_to(root).parts:
            current = current / component
            self._require_real_directory(current)
        self._require_closed(directory, allow_missing_file=False)

    @staticmethod
    def _require_real_directory(path: Path) -> None:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise ProductWorkspaceNotFound(
                "Product workspace artifact directory was not found"
            ) from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise ProductWorkspaceCorrupt("Product workspace artifact directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing_file: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing_file and entries != {_FILENAME}):
            raise ProductWorkspaceCorrupt("Product workspace artifact directory is not closed")

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise ProductWorkspaceCorrupt("Product workspace artifact file is unsafe") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise ProductWorkspaceCorrupt("Product workspace artifact file is unsafe")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _artifact(value: dict) -> ProductWorkspaceArtifact:
    return ProductWorkspaceArtifact(
        artifact_id=value["artifact_id"],
        work_order_id=value["work_order_id"],
        work_order_digest=value["work_order_digest"],
        tenant_id=value["tenant_id"],
        opportunity_id=value["opportunity_id"],
        execution_id=value["execution_id"],
        assignment_id=value["assignment_id"],
        orchestration_artifact_id=value["orchestration_artifact_id"],
        orchestration_artifact_digest=value["orchestration_artifact_digest"],
        repository_id=value["repository_id"],
        repository_identity=value["repository_identity"],
        provider_id=value["provider_id"],
        authority_digest=value["authority_digest"],
        capability_ids=tuple(value["capability_ids"]),
        action_ids=tuple(value["action_ids"]),
        tool_ids=tuple(value["tool_ids"]),
        workspace_id=value["workspace_id"],
        workspace_relative_path=value["workspace_relative_path"],
        base_branch=value["base_branch"],
        base_commit=value["base_commit"],
        base_tree=value["base_tree"],
        feature_branch=value["feature_branch"],
        workspace_head=value["workspace_head"],
        workspace_tree=value["workspace_tree"],
        git_command_count=value["git_command_count"],
        network_call_count=value["network_call_count"],
        general_command_count=value["general_command_count"],
        product_file_write_count=value["product_file_write_count"],
        unrelated_path_change_count=value["unrelated_path_change_count"],
        provider_output_digest=value["provider_output_digest"],
        generated_at=datetime.fromisoformat(value["generated_at"]),
        source_state=value["source_state"],
        workspace_state=value["workspace_state"],
        branch_state=value["branch_state"],
        status=value["status"],
        pilot_status=value["pilot_status"],
    )
