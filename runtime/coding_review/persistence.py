"""Canonical write-once persistence for Day 32 coding-review artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.coding_review.errors import (
    CodingReviewConflict,
    CodingReviewCorrupt,
    CodingReviewNotFound,
)
from runtime.coding_review.models import (
    CodingReviewArtifact,
    CodingRoundRecord,
    FailureRoute,
    ObservedProductFile,
    ReviewFinding,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "coding-review-v1.json"
_MAX_BYTES = 512_000
_ARTIFACT_FIELDS = {item.name for item in fields(CodingReviewArtifact)}
_ROUND_FIELDS = {item.name for item in fields(CodingRoundRecord)}
_FINDING_FIELDS = {item.name for item in fields(ReviewFinding)}
_ROUTE_FIELDS = {item.name for item in fields(FailureRoute)}
_FILE_FIELDS = {item.name for item in fields(ObservedProductFile)}


class FileCodingReviewArtifactStore:
    """Tenant/execution-scoped closed store with no host workspace path."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Coding-review artifact root must be a Path")
        self._root = root

    def save(self, artifact: CodingReviewArtifact) -> CodingReviewArtifact:
        if not isinstance(artifact, CodingReviewArtifact):
            raise TypeError("Coding-review artifact is invalid")
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
            raise CodingReviewConflict("Coding-review artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise CodingReviewConflict(
                    "Coding-review execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> CodingReviewArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise CodingReviewCorrupt("Coding-review artifact file is unsafe")
        if not path.exists():
            raise CodingReviewNotFound("Coding-review artifact was not found")
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
            _closed_nested(record)
            artifact = _artifact(record)
            if artifact.digest != envelope["digest"]:
                raise ValueError("digest does not match")
            if artifact.tenant_id != tenant_id or artifact.execution_id != execution_id:
                raise ValueError("path identity does not match")
            if content != canonical_json(envelope).encode("utf-8"):
                raise ValueError("record is not canonical")
            return artifact
        except CodingReviewCorrupt:
            raise
        except Exception as error:
            raise CodingReviewCorrupt("Coding-review artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise CodingReviewCorrupt(f"Coding-review {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise CodingReviewCorrupt("Coding-review artifact path escaped its root") from error
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
            raise CodingReviewNotFound("Coding-review artifact directory was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise CodingReviewCorrupt("Coding-review artifact directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing and entries != {_FILENAME}):
            raise CodingReviewCorrupt("Coding-review artifact directory is not closed")

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise CodingReviewCorrupt("Coding-review artifact file is unsafe") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise CodingReviewCorrupt("Coding-review artifact file is unsafe")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _closed_nested(record: dict) -> None:
    if any(not isinstance(item, dict) or set(item) != _ROUND_FIELDS for item in record["rounds"]):
        raise ValueError("round record is invalid")
    for round_record in record["rounds"]:
        if any(
            not isinstance(item, dict) or set(item) != _FINDING_FIELDS
            for item in round_record["findings"]
        ):
            raise ValueError("finding record is invalid")
    if any(
        not isinstance(item, dict) or set(item) != _ROUTE_FIELDS
        for item in record["failure_routes"]
    ):
        raise ValueError("route record is invalid")
    if any(
        not isinstance(item, dict) or set(item) != _FILE_FIELDS
        for item in record["final_files"]
    ):
        raise ValueError("file record is invalid")


def _finding(value: dict) -> ReviewFinding:
    return ReviewFinding(**value)


def _round(value: dict) -> CodingRoundRecord:
    return CodingRoundRecord(
        round_number=value["round_number"],
        resolved_feedback_codes=tuple(value["resolved_feedback_codes"]),
        changed_paths=tuple(value["changed_paths"]),
        qa_status=value["qa_status"],
        qa_test_count=value["qa_test_count"],
        qa_result_digest=value["qa_result_digest"],
        security_status=value["security_status"],
        findings=tuple(_finding(item) for item in value["findings"]),
        diff_digest=value["diff_digest"],
        file_write_count=value["file_write_count"],
        specialized_command_count=value["specialized_command_count"],
    )


def _artifact(value: dict) -> CodingReviewArtifact:
    return CodingReviewArtifact(
        artifact_id=value["artifact_id"],
        work_order_id=value["work_order_id"],
        work_order_digest=value["work_order_digest"],
        tenant_id=value["tenant_id"],
        opportunity_id=value["opportunity_id"],
        execution_id=value["execution_id"],
        assignment_id=value["assignment_id"],
        orchestration_artifact_id=value["orchestration_artifact_id"],
        orchestration_artifact_digest=value["orchestration_artifact_digest"],
        orchestration_source_set_digest=value["orchestration_source_set_digest"],
        workspace_artifact_id=value["workspace_artifact_id"],
        workspace_artifact_digest=value["workspace_artifact_digest"],
        qa_artifact_id=value["qa_artifact_id"],
        qa_artifact_digest=value["qa_artifact_digest"],
        security_artifact_id=value["security_artifact_id"],
        security_artifact_digest=value["security_artifact_digest"],
        repository_id=value["repository_id"],
        repository_identity=value["repository_identity"],
        workspace_id=value["workspace_id"],
        base_branch=value["base_branch"],
        base_commit=value["base_commit"],
        base_tree=value["base_tree"],
        feature_branch=value["feature_branch"],
        provider_id=value["provider_id"],
        authority_digest=value["authority_digest"],
        capability_ids=tuple(value["capability_ids"]),
        action_ids=tuple(value["action_ids"]),
        tool_ids=tuple(value["tool_ids"]),
        rounds=tuple(_round(item) for item in value["rounds"]),
        failure_routes=tuple(FailureRoute(**item) for item in value["failure_routes"]),
        final_changed_paths=tuple(value["final_changed_paths"]),
        final_files=tuple(ObservedProductFile(**item) for item in value["final_files"]),
        final_diff_digest=value["final_diff_digest"],
        qa_execution_count=value["qa_execution_count"],
        security_execution_count=value["security_execution_count"],
        product_file_write_count=value["product_file_write_count"],
        specialized_command_count=value["specialized_command_count"],
        git_inspection_count=value["git_inspection_count"],
        provider_output_digest=value["provider_output_digest"],
        generated_at=datetime.fromisoformat(value["generated_at"]),
        network_call_count=value["network_call_count"],
        general_command_count=value["general_command_count"],
        credential_access_count=value["credential_access_count"],
        staged_path_count=value["staged_path_count"],
        commit_count=value["commit_count"],
        push_count=value["push_count"],
        pull_request_count=value["pull_request_count"],
        source_state=value["source_state"],
        workspace_state=value["workspace_state"],
        qa_state=value["qa_state"],
        security_state=value["security_state"],
        delivery_state=value["delivery_state"],
        status=value["status"],
        pilot_status=value["pilot_status"],
    )
