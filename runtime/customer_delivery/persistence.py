"""Atomic integrity-checked persistence for governed customer delivery."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from runtime.customer_delivery.errors import (
    CustomerDeliveryConflict,
    CustomerDeliveryCorrupt,
    CustomerDeliveryNotFound,
)
from runtime.customer_delivery.models import (
    CustomerDeliveryReview,
    CustomerDeliveryStatus,
    ReviewedFile,
    delivery_id_for,
)


_SCHEMA_VERSION = 1
_FILENAME = "delivery-review-v1.json"


class FileCustomerDeliveryStore:
    """Persist one monotonic review/delivery record per customer request."""

    def __init__(self, root: Path) -> None:
        path = Path(root).expanduser()
        if path.is_symlink():
            raise CustomerDeliveryCorrupt("Customer delivery store cannot be a symbolic link")
        self._root = path.resolve()
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self._root.chmod(0o700)

    def find(self, customer_id: str, request_id: str) -> CustomerDeliveryReview | None:
        path = self._path(customer_id, request_id)
        return None if not path.exists() else self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerDeliveryReview:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerDeliveryCorrupt("Customer delivery record path is unsafe")
        if os.name != "nt" and path.exists() and path.stat().st_mode & 0o077:
            raise CustomerDeliveryCorrupt("Customer delivery record permissions are too broad")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerDeliveryNotFound("Customer delivery review does not exist") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid delivery envelope")
            value = _from_record(envelope["record"])
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.delivery_id != delivery_id_for(request_id)
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Delivery authority mismatch")
            return value
        except CustomerDeliveryCorrupt:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerDeliveryCorrupt("Customer delivery record is corrupt") from error

    def create(self, value: CustomerDeliveryReview) -> CustomerDeliveryReview:
        path = self._path(value.customer_id, value.request_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing.review_digest == value.review_digest:
                return existing
            raise CustomerDeliveryConflict("A different delivery review already exists") from None
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_encode(value))
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise
        return value

    def replace(
        self,
        value: CustomerDeliveryReview,
        *,
        expected_digest: str,
    ) -> CustomerDeliveryReview:
        current = self.load(value.customer_id, value.request_id)
        if current.digest != expected_digest:
            raise CustomerDeliveryConflict("Customer delivery record changed")
        if current.review_digest != value.review_digest:
            raise CustomerDeliveryConflict("Approved delivery review cannot change")
        path = self._path(value.customer_id, value.request_id)
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{value.delivery_id}.", suffix=".tmp"
        )
        try:
            if os.name != "nt":
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_encode(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return value

    def _path(self, customer_id: str, request_id: str) -> Path:
        delivery_id_for(customer_id)
        delivery_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerDeliveryCorrupt("Customer delivery path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerDeliveryCorrupt("Customer delivery path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerDeliveryCorrupt("Customer delivery directory is unsafe")
            if any(value.name != _FILENAME for value in directory.iterdir()):
                raise CustomerDeliveryCorrupt("Customer delivery directory is not closed")
        return directory / _FILENAME


def _record(value: CustomerDeliveryReview) -> dict[str, object]:
    record = asdict(value)
    record["status"] = value.status.value
    record["created_at"] = value.created_at.isoformat()
    record["updated_at"] = value.updated_at.isoformat()
    record["reviewed_at"] = value.reviewed_at.isoformat() if value.reviewed_at else None
    record["reviewed_files"] = [asdict(item) for item in value.reviewed_files]
    return record


def _encode(value: CustomerDeliveryReview) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _from_record(value: dict[str, object]) -> CustomerDeliveryReview:
    expected = {
        "delivery_id",
        "customer_id",
        "request_id",
        "product_id",
        "execution_plan_id",
        "execution_plan_digest",
        "execution_scope_digest",
        "provider_operation_id",
        "provider_task_id",
        "patch_manifest_digest",
        "git_diff_digest",
        "workspace_id",
        "workspace_branch",
        "workspace_commit_before_turn",
        "repository_full_name",
        "base_branch",
        "reviewed_files",
        "additions",
        "deletions",
        "commit_message",
        "pull_request_title",
        "pull_request_body",
        "pull_request_body_digest",
        "created_at",
        "updated_at",
        "status",
        "reviewed_at",
        "reviewed_by",
        "commit_sha",
        "tree_sha",
        "pull_request_number",
        "pull_request_url",
        "failure_classification",
    }
    if set(value) != expected or not isinstance(value["reviewed_files"], list):
        raise ValueError("Delivery record fields are invalid")
    files = value["reviewed_files"]
    if any(not isinstance(item, dict) or set(item) != {"path", "content_digest"} for item in files):
        raise ValueError("Reviewed file records are invalid")
    return CustomerDeliveryReview(
        delivery_id=value["delivery_id"],  # type: ignore[arg-type]
        customer_id=value["customer_id"],  # type: ignore[arg-type]
        request_id=value["request_id"],  # type: ignore[arg-type]
        product_id=value["product_id"],  # type: ignore[arg-type]
        execution_plan_id=value["execution_plan_id"],  # type: ignore[arg-type]
        execution_plan_digest=value["execution_plan_digest"],  # type: ignore[arg-type]
        execution_scope_digest=value["execution_scope_digest"],  # type: ignore[arg-type]
        provider_operation_id=value["provider_operation_id"],  # type: ignore[arg-type]
        provider_task_id=value["provider_task_id"],  # type: ignore[arg-type]
        patch_manifest_digest=value["patch_manifest_digest"],  # type: ignore[arg-type]
        git_diff_digest=value["git_diff_digest"],  # type: ignore[arg-type]
        workspace_id=value["workspace_id"],  # type: ignore[arg-type]
        workspace_branch=value["workspace_branch"],  # type: ignore[arg-type]
        workspace_commit_before_turn=value["workspace_commit_before_turn"],  # type: ignore[arg-type]
        repository_full_name=value["repository_full_name"],  # type: ignore[arg-type]
        base_branch=value["base_branch"],  # type: ignore[arg-type]
        reviewed_files=tuple(ReviewedFile(**item) for item in files),
        additions=value["additions"],  # type: ignore[arg-type]
        deletions=value["deletions"],  # type: ignore[arg-type]
        commit_message=value["commit_message"],  # type: ignore[arg-type]
        pull_request_title=value["pull_request_title"],  # type: ignore[arg-type]
        pull_request_body=value["pull_request_body"],  # type: ignore[arg-type]
        pull_request_body_digest=value["pull_request_body_digest"],  # type: ignore[arg-type]
        created_at=datetime.fromisoformat(value["created_at"]),  # type: ignore[arg-type]
        updated_at=datetime.fromisoformat(value["updated_at"]),  # type: ignore[arg-type]
        status=CustomerDeliveryStatus(value["status"]),
        reviewed_at=(
            datetime.fromisoformat(value["reviewed_at"]) if value["reviewed_at"] else None  # type: ignore[arg-type]
        ),
        reviewed_by=value["reviewed_by"],  # type: ignore[arg-type]
        commit_sha=value["commit_sha"],  # type: ignore[arg-type]
        tree_sha=value["tree_sha"],  # type: ignore[arg-type]
        pull_request_number=value["pull_request_number"],  # type: ignore[arg-type]
        pull_request_url=value["pull_request_url"],  # type: ignore[arg-type]
        failure_classification=value["failure_classification"],  # type: ignore[arg-type]
    )
