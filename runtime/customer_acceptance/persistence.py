"""Atomic integrity-checked persistence for customer preview acceptance."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from runtime.customer_acceptance.errors import (
    CustomerAcceptanceConflict,
    CustomerAcceptanceCorrupt,
    CustomerAcceptanceNotFound,
)
from runtime.customer_acceptance.models import (
    AcceptanceJourneySummary,
    CustomerAcceptanceRecord,
    CustomerAcceptanceStatus,
    acceptance_id_for,
)


_SCHEMA_VERSION = 1
_FILENAME = "preview-acceptance-v1.json"


class FileCustomerAcceptanceStore:
    """Persist one monotonic Module 5 record per customer request."""

    def __init__(self, root: Path) -> None:
        path = Path(root).expanduser()
        if path.is_symlink():
            raise CustomerAcceptanceCorrupt("Customer acceptance store cannot be a symbolic link")
        self._root = path.resolve()
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            self._root.chmod(0o700)

    def find(self, customer_id: str, request_id: str) -> CustomerAcceptanceRecord | None:
        path = self._path(customer_id, request_id)
        return None if not path.exists() else self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerAcceptanceRecord:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerAcceptanceCorrupt("Customer acceptance record path is unsafe")
        if os.name != "nt" and path.exists() and path.stat().st_mode & 0o077:
            raise CustomerAcceptanceCorrupt("Customer acceptance record permissions are too broad")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerAcceptanceNotFound("Customer acceptance record does not exist") from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid acceptance envelope")
            value = _from_record(envelope["record"])
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.acceptance_id != acceptance_id_for(request_id)
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Acceptance authority mismatch")
            return value
        except CustomerAcceptanceCorrupt:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerAcceptanceCorrupt("Customer acceptance record is corrupt") from error

    def create(self, value: CustomerAcceptanceRecord) -> CustomerAcceptanceRecord:
        path = self._path(value.customer_id, value.request_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing.approval_digest == value.approval_digest:
                return existing
            raise CustomerAcceptanceConflict("A different acceptance plan already exists") from None
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
        value: CustomerAcceptanceRecord,
        *,
        expected_digest: str,
    ) -> CustomerAcceptanceRecord:
        current = self.load(value.customer_id, value.request_id)
        if current.digest != expected_digest:
            raise CustomerAcceptanceConflict("Customer acceptance record changed")
        if current.approval_digest != value.approval_digest:
            raise CustomerAcceptanceConflict("Approved acceptance authority cannot change")
        path = self._path(value.customer_id, value.request_id)
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{value.acceptance_id}.", suffix=".tmp"
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
        acceptance_id_for(customer_id)
        acceptance_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerAcceptanceCorrupt("Customer acceptance path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerAcceptanceCorrupt("Customer acceptance path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerAcceptanceCorrupt("Customer acceptance directory is unsafe")
            if any(value.name != _FILENAME for value in directory.iterdir()):
                raise CustomerAcceptanceCorrupt("Customer acceptance directory is not closed")
        return directory / _FILENAME


def _record(value: CustomerAcceptanceRecord) -> dict[str, object]:
    record = asdict(value)
    record["status"] = value.status.value
    record["created_at"] = value.created_at.isoformat()
    record["updated_at"] = value.updated_at.isoformat()
    record["approved_at"] = value.approved_at.isoformat() if value.approved_at else None
    record["journeys"] = [asdict(item) for item in value.journeys]
    return record


def _encode(value: CustomerAcceptanceRecord) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _from_record(value: dict[str, object]) -> CustomerAcceptanceRecord:
    expected = {
        "acceptance_id",
        "customer_id",
        "request_id",
        "product_id",
        "delivery_id",
        "delivery_digest",
        "delivery_review_digest",
        "repository_full_name",
        "base_branch",
        "head_branch",
        "commit_sha",
        "tree_sha",
        "pull_request_number",
        "pull_request_url",
        "configuration_digest",
        "preview_environment_id",
        "preview_url",
        "workflow_file",
        "automated_test_job",
        "security_job",
        "browser_plan_id",
        "browser_plan_digest",
        "journeys",
        "created_at",
        "updated_at",
        "status",
        "approved_at",
        "approved_by",
        "workflow_run_id",
        "workflow_run_url",
        "deployment_revision",
        "deployment_receipt_digest",
        "browser_execution_digest",
        "evidence_package_id",
        "evidence_package_digest",
        "failure_classification",
    }
    if set(value) != expected or not isinstance(value["journeys"], list):
        raise ValueError("Acceptance record fields are invalid")
    journeys = value["journeys"]
    journey_fields = {"journey_id", "capability_id", "title", "start_path", "step_count"}
    if any(not isinstance(item, dict) or set(item) != journey_fields for item in journeys):
        raise ValueError("Acceptance journey records are invalid")
    return CustomerAcceptanceRecord(
        acceptance_id=value["acceptance_id"],  # type: ignore[arg-type]
        customer_id=value["customer_id"],  # type: ignore[arg-type]
        request_id=value["request_id"],  # type: ignore[arg-type]
        product_id=value["product_id"],  # type: ignore[arg-type]
        delivery_id=value["delivery_id"],  # type: ignore[arg-type]
        delivery_digest=value["delivery_digest"],  # type: ignore[arg-type]
        delivery_review_digest=value["delivery_review_digest"],  # type: ignore[arg-type]
        repository_full_name=value["repository_full_name"],  # type: ignore[arg-type]
        base_branch=value["base_branch"],  # type: ignore[arg-type]
        head_branch=value["head_branch"],  # type: ignore[arg-type]
        commit_sha=value["commit_sha"],  # type: ignore[arg-type]
        tree_sha=value["tree_sha"],  # type: ignore[arg-type]
        pull_request_number=value["pull_request_number"],  # type: ignore[arg-type]
        pull_request_url=value["pull_request_url"],  # type: ignore[arg-type]
        configuration_digest=value["configuration_digest"],  # type: ignore[arg-type]
        preview_environment_id=value["preview_environment_id"],  # type: ignore[arg-type]
        preview_url=value["preview_url"],  # type: ignore[arg-type]
        workflow_file=value["workflow_file"],  # type: ignore[arg-type]
        automated_test_job=value["automated_test_job"],  # type: ignore[arg-type]
        security_job=value["security_job"],  # type: ignore[arg-type]
        browser_plan_id=value["browser_plan_id"],  # type: ignore[arg-type]
        browser_plan_digest=value["browser_plan_digest"],  # type: ignore[arg-type]
        journeys=tuple(AcceptanceJourneySummary(**item) for item in journeys),
        created_at=datetime.fromisoformat(value["created_at"]),  # type: ignore[arg-type]
        updated_at=datetime.fromisoformat(value["updated_at"]),  # type: ignore[arg-type]
        status=CustomerAcceptanceStatus(value["status"]),
        approved_at=(
            datetime.fromisoformat(value["approved_at"]) if value["approved_at"] else None  # type: ignore[arg-type]
        ),
        approved_by=value["approved_by"],  # type: ignore[arg-type]
        workflow_run_id=value["workflow_run_id"],  # type: ignore[arg-type]
        workflow_run_url=value["workflow_run_url"],  # type: ignore[arg-type]
        deployment_revision=value["deployment_revision"],  # type: ignore[arg-type]
        deployment_receipt_digest=value["deployment_receipt_digest"],  # type: ignore[arg-type]
        browser_execution_digest=value["browser_execution_digest"],  # type: ignore[arg-type]
        evidence_package_id=value["evidence_package_id"],  # type: ignore[arg-type]
        evidence_package_digest=value["evidence_package_digest"],  # type: ignore[arg-type]
        failure_classification=value["failure_classification"],  # type: ignore[arg-type]
    )
