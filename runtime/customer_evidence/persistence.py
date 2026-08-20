"""Canonical write-once persistence for preview evidence and customer reviews."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_evidence.errors import (
    CustomerEvidenceConflict,
    CustomerEvidenceCorrupt,
    CustomerEvidenceNotFound,
)
from runtime.customer_evidence.models import (
    CustomerPreviewEvidencePackage,
    CustomerPreviewReview,
    package_id_for,
    review_id_for,
)
from runtime.runtime_acceptance import EvidenceArtifact, EvidenceKind, EvidenceOutcome


_SCHEMA_VERSION = 1
_PACKAGE_FILE = "preview-evidence-v0.1.json"
_REVIEW_FILE = "preview-review-v0.1.json"


class FileCustomerPreviewEvidenceStore:
    """Persist one package and one exact customer decision per request."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save_package(
        self, value: CustomerPreviewEvidencePackage
    ) -> CustomerPreviewEvidencePackage:
        path = self._path(value.customer_id, value.request_id) / _PACKAGE_FILE
        try:
            _exclusive_write(path, _encode("PACKAGE", value.digest, _package_record(value)))
        except FileExistsError:
            existing = self.load_package(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise CustomerEvidenceConflict(
                "A different preview evidence package already exists"
            ) from None
        return value

    def find_package(
        self, customer_id: str, request_id: str
    ) -> CustomerPreviewEvidencePackage | None:
        path = self._path(customer_id, request_id) / _PACKAGE_FILE
        if path.is_symlink():
            raise CustomerEvidenceCorrupt("Preview evidence package file is unsafe")
        if not path.exists():
            return None
        return self.load_package(customer_id, request_id)

    def load_package(
        self, customer_id: str, request_id: str
    ) -> CustomerPreviewEvidencePackage:
        path = self._path(customer_id, request_id) / _PACKAGE_FILE
        kind, digest, record, content = _read(path)
        try:
            value = _package_from_record(record)
            if (
                kind != "PACKAGE"
                or value.customer_id != customer_id
                or value.request_id != request_id
                or value.package_id != package_id_for(request_id)
                or value.digest != digest
                or _encode("PACKAGE", value.digest, _package_record(value)) != content
            ):
                raise ValueError("Preview evidence authority mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise CustomerEvidenceCorrupt("Preview evidence package is corrupt") from error

    def save_review(self, value: CustomerPreviewReview) -> CustomerPreviewReview:
        path = self._path(value.customer_id, value.request_id) / _REVIEW_FILE
        try:
            _exclusive_write(path, _encode("REVIEW", value.digest, _review_record(value)))
        except FileExistsError:
            existing = self.load_review(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise CustomerEvidenceConflict(
                "A customer preview review already exists for this package"
            ) from None
        return value

    def find_review(
        self, customer_id: str, request_id: str
    ) -> CustomerPreviewReview | None:
        path = self._path(customer_id, request_id) / _REVIEW_FILE
        if path.is_symlink():
            raise CustomerEvidenceCorrupt("Preview review file is unsafe")
        if not path.exists():
            return None
        return self.load_review(customer_id, request_id)

    def load_review(self, customer_id: str, request_id: str) -> CustomerPreviewReview:
        path = self._path(customer_id, request_id) / _REVIEW_FILE
        kind, digest, record, content = _read(path)
        try:
            value = _review_from_record(record)
            if (
                kind != "REVIEW"
                or value.customer_id != customer_id
                or value.request_id != request_id
                or value.review_id != review_id_for(request_id)
                or value.package_id != package_id_for(request_id)
                or value.digest != digest
                or _encode("REVIEW", value.digest, _review_record(value)) != content
            ):
                raise ValueError("Preview review authority mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise CustomerEvidenceCorrupt("Preview review authority is corrupt") from error

    def _path(self, customer_id: str, request_id: str) -> Path:
        package_id_for(customer_id)
        package_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerEvidenceCorrupt("Preview evidence path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerEvidenceCorrupt("Preview evidence path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerEvidenceCorrupt("Preview evidence directory is unsafe")
            if any(
                entry.name not in {_PACKAGE_FILE, _REVIEW_FILE}
                for entry in directory.iterdir()
            ):
                raise CustomerEvidenceCorrupt("Preview evidence directory is not closed")
        return directory


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


def _read(path: Path) -> tuple[str, str, dict[str, Any], bytes]:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise CustomerEvidenceCorrupt("Preview evidence file is unsafe")
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        raise CustomerEvidenceNotFound("Preview evidence record does not exist") from None
    try:
        envelope = json.loads(content)
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"schema_version", "kind", "digest", "record"}
            or envelope["schema_version"] != _SCHEMA_VERSION
            or not isinstance(envelope["kind"], str)
            or not isinstance(envelope["digest"], str)
            or not isinstance(envelope["record"], dict)
        ):
            raise ValueError("Invalid preview evidence envelope")
        return envelope["kind"], envelope["digest"], envelope["record"], content
    except (ValueError, json.JSONDecodeError) as error:
        raise CustomerEvidenceCorrupt("Preview evidence envelope is corrupt") from error


def _encode(kind: str, digest: str, record: dict[str, object]) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": _SCHEMA_VERSION,
                "kind": kind,
                "digest": digest,
                "record": record,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _package_record(value: CustomerPreviewEvidencePackage) -> dict[str, object]:
    return {
        "package_id": value.package_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "product_id": value.product_id,
        "progress_id": value.progress_id,
        "progress_digest": value.progress_digest,
        "roadmap_digest": value.roadmap_digest,
        "estimate_digest": value.estimate_digest,
        "preview_label": value.preview_label,
        "preview_url": value.preview_url,
        "commit_sha": value.commit_sha,
        "evidence": [_evidence_record(item) for item in value.evidence],
        "published_at": value.published_at.isoformat(),
        "status": value.status,
    }


def _evidence_record(value: EvidenceArtifact) -> dict[str, object]:
    return {
        "evidence_id": value.evidence_id,
        "run_id": value.run_id,
        "capability_id": value.capability_id,
        "journey_id": value.journey_id,
        "kind": value.kind.value,
        "outcome": value.outcome.value,
        "commit_sha": value.commit_sha,
        "artifact_uri": value.artifact_uri,
        "digest": value.digest,
        "observed_at": value.observed_at.isoformat(),
        "summary": value.summary,
        "metadata": [list(item) for item in value.metadata],
    }


def _review_record(value: CustomerPreviewReview) -> dict[str, object]:
    return {
        "review_id": value.review_id,
        "package_id": value.package_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "package_digest": value.package_digest,
        "progress_digest": value.progress_digest,
        "decision": value.decision,
        "comments": value.comments,
        "confirmation_version": value.confirmation_version,
        "reviewed_at": value.reviewed_at.isoformat(),
    }


def _package_from_record(value: dict[str, Any]) -> CustomerPreviewEvidencePackage:
    if set(value) != {
        "package_id", "customer_id", "request_id", "product_id", "progress_id",
        "progress_digest", "roadmap_digest", "estimate_digest", "preview_label",
        "preview_url", "commit_sha", "evidence", "published_at", "status",
    }:
        raise ValueError("Preview evidence package fields are invalid")
    return CustomerPreviewEvidencePackage(
        value["package_id"], value["customer_id"], value["request_id"],
        value["product_id"], value["progress_id"], value["progress_digest"],
        value["roadmap_digest"], value["estimate_digest"], value["preview_label"],
        value["preview_url"], value["commit_sha"],
        tuple(_evidence_from_record(item) for item in value["evidence"]),
        datetime.fromisoformat(value["published_at"]), value["status"],
    )


def _evidence_from_record(value: dict[str, Any]) -> EvidenceArtifact:
    if set(value) != {
        "evidence_id", "run_id", "capability_id", "journey_id", "kind", "outcome",
        "commit_sha", "artifact_uri", "digest", "observed_at", "summary", "metadata",
    }:
        raise ValueError("Preview evidence item fields are invalid")
    return EvidenceArtifact(
        value["evidence_id"], value["run_id"], value["capability_id"],
        value["journey_id"], EvidenceKind(value["kind"]), EvidenceOutcome(value["outcome"]),
        value["commit_sha"], value["artifact_uri"], value["digest"],
        datetime.fromisoformat(value["observed_at"]), value["summary"],
        tuple(tuple(item) for item in value["metadata"]),
    )


def _review_from_record(value: dict[str, Any]) -> CustomerPreviewReview:
    if set(value) != {
        "review_id", "package_id", "customer_id", "request_id", "package_digest",
        "progress_digest", "decision", "comments", "confirmation_version", "reviewed_at",
    }:
        raise ValueError("Preview review fields are invalid")
    return CustomerPreviewReview(
        value["review_id"], value["package_id"], value["customer_id"],
        value["request_id"], value["package_digest"], value["progress_digest"],
        value["decision"], value["comments"], value["confirmation_version"],
        datetime.fromisoformat(value["reviewed_at"]),
    )
