"""Canonical write-once persistence for Day 33 delivery artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.github_delivery.errors import (
    GitHubDeliveryConflict,
    GitHubDeliveryCorrupt,
    GitHubDeliveryNotFound,
)
from runtime.github_delivery.models import (
    DraftPullRequestReceipt,
    GitHubDeliveryArtifact,
    ReviewedFileBinding,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "github-delivery-v1.json"
_MAX_BYTES = 256_000
_ARTIFACT_FIELDS = {item.name for item in fields(GitHubDeliveryArtifact)}
_FILE_FIELDS = {item.name for item in fields(ReviewedFileBinding)}
_PR_FIELDS = {item.name for item in fields(DraftPullRequestReceipt)}


class FileGitHubDeliveryArtifactStore:
    """Tenant/execution-scoped closed store with no host path or credential."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("GitHub delivery artifact root must be a Path")
        self._root = root

    def save(self, artifact: GitHubDeliveryArtifact) -> GitHubDeliveryArtifact:
        if not isinstance(artifact, GitHubDeliveryArtifact):
            raise TypeError("GitHub delivery artifact is invalid")
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
        content = canonical_json(envelope).encode("utf-8")
        if len(content) > _MAX_BYTES:
            raise GitHubDeliveryConflict("GitHub delivery artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise GitHubDeliveryConflict(
                    "GitHub delivery execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> GitHubDeliveryArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise GitHubDeliveryCorrupt("GitHub delivery artifact file is unsafe")
        if not path.exists():
            raise GitHubDeliveryNotFound("GitHub delivery artifact was not found")
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
            ):
                raise ValueError("envelope is invalid")
            if any(
                not isinstance(item, dict) or set(item) != _FILE_FIELDS
                for item in record["reviewed_files"]
            ):
                raise ValueError("reviewed file bindings are invalid")
            if not isinstance(record["pull_request"], dict) or set(record["pull_request"]) != _PR_FIELDS:
                raise ValueError("pull-request receipt is invalid")
            artifact = _artifact(record)
            if artifact.digest != envelope["digest"]:
                raise ValueError("digest does not match")
            if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
                raise ValueError("path identity does not match")
            if content != canonical_json(envelope).encode("utf-8"):
                raise ValueError("record is not canonical")
            return artifact
        except GitHubDeliveryCorrupt:
            raise
        except Exception as error:
            raise GitHubDeliveryCorrupt("GitHub delivery artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise GitHubDeliveryCorrupt(f"GitHub delivery {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise GitHubDeliveryCorrupt("GitHub delivery artifact path escaped its root") from error
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
            raise GitHubDeliveryNotFound("GitHub delivery directory was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise GitHubDeliveryCorrupt("GitHub delivery directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing and entries != {_FILENAME}):
            raise GitHubDeliveryCorrupt("GitHub delivery directory is not closed")

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise GitHubDeliveryCorrupt("GitHub delivery artifact file is unsafe") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise GitHubDeliveryCorrupt("GitHub delivery artifact file is unsafe")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _artifact(value: dict) -> GitHubDeliveryArtifact:
    return GitHubDeliveryArtifact(
        artifact_id=value["artifact_id"],
        work_order_id=value["work_order_id"],
        work_order_digest=value["work_order_digest"],
        tenant_id=value["tenant_id"],
        opportunity_id=value["opportunity_id"],
        execution_id=value["execution_id"],
        assignment_id=value["assignment_id"],
        coding_review_artifact_id=value["coding_review_artifact_id"],
        coding_review_artifact_digest=value["coding_review_artifact_digest"],
        workspace_artifact_digest=value["workspace_artifact_digest"],
        orchestration_artifact_digest=value["orchestration_artifact_digest"],
        qa_artifact_digest=value["qa_artifact_digest"],
        security_artifact_digest=value["security_artifact_digest"],
        repository_id=value["repository_id"],
        repository_identity=value["repository_identity"],
        repository_full_name=value["repository_full_name"],
        workspace_id=value["workspace_id"],
        base_branch=value["base_branch"],
        base_commit=value["base_commit"],
        base_tree=value["base_tree"],
        feature_branch=value["feature_branch"],
        reviewed_files=tuple(ReviewedFileBinding(**item) for item in value["reviewed_files"]),
        final_diff_digest=value["final_diff_digest"],
        commit_message=value["commit_message"],
        pull_request_title=value["pull_request_title"],
        pull_request_body_digest=value["pull_request_body_digest"],
        provider_id=value["provider_id"],
        authority_digest=value["authority_digest"],
        capability_ids=tuple(value["capability_ids"]),
        action_ids=tuple(value["action_ids"]),
        tool_ids=tuple(value["tool_ids"]),
        staged_paths=tuple(value["staged_paths"]),
        committed_paths=tuple(value["committed_paths"]),
        commit_parent=value["commit_parent"],
        commit_sha=value["commit_sha"],
        commit_tree=value["commit_tree"],
        remote_branch_sha=value["remote_branch_sha"],
        pull_request=DraftPullRequestReceipt(**value["pull_request"]),
        git_command_count=value["git_command_count"],
        controlled_network_call_count=value["controlled_network_call_count"],
        credential_handle_count=value["credential_handle_count"],
        provider_output_digest=value["provider_output_digest"],
        generated_at=datetime.fromisoformat(value["generated_at"]),
        secret_value_exposure_count=value["secret_value_exposure_count"],
        unapproved_network_call_count=value["unapproved_network_call_count"],
        unrelated_path_count=value["unrelated_path_count"],
        general_command_count=value["general_command_count"],
        force_push_count=value["force_push_count"],
        commit_count=value["commit_count"],
        push_count=value["push_count"],
        pull_request_count=value["pull_request_count"],
        merge_count=value["merge_count"],
        deployment_count=value["deployment_count"],
        release_count=value["release_count"],
        source_state=value["source_state"],
        workspace_state=value["workspace_state"],
        branch_state=value["branch_state"],
        pull_request_state=value["pull_request_state"],
        delivery_state=value["delivery_state"],
        status=value["status"],
        pilot_status=value["pilot_status"],
    )
