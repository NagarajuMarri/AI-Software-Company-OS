"""Canonical write-once storage for validated Day 29 Documentation artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.agents import AgentRole
from runtime.workforce_documentation.errors import (
    DocumentationWorkforceConflict,
    DocumentationWorkforceCorrupt,
    DocumentationWorkforceNotFound,
)
from runtime.workforce_documentation.models import (
    CustomerHandoff,
    DocumentationEngineeringSource,
    DocumentationKind,
    DocumentationRecord,
    DocumentationSection,
    DocumentationStatusReport,
    DocumentationWorkArtifact,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "documentation-work-v1.json"
_MAX_BYTES = 384_000
_ARTIFACT_FIELDS = {item.name for item in fields(DocumentationWorkArtifact)}
_SOURCE_FIELDS = {item.name for item in fields(DocumentationEngineeringSource)}
_DOCUMENT_FIELDS = {item.name for item in fields(DocumentationRecord)}
_SECTION_FIELDS = {item.name for item in fields(DocumentationSection)}
_HANDOFF_FIELDS = {item.name for item in fields(CustomerHandoff)}
_STATUS_FIELDS = {item.name for item in fields(DocumentationStatusReport)}


class FileDocumentationArtifactStore:
    """Tenant/execution-scoped Documentation storage with integrity controls."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Documentation artifact root must be a Path")
        self._root = root

    def save(self, artifact: DocumentationWorkArtifact) -> DocumentationWorkArtifact:
        if not isinstance(artifact, DocumentationWorkArtifact):
            raise TypeError("Documentation artifact is invalid")
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
            raise DocumentationWorkforceConflict("Documentation artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise DocumentationWorkforceConflict(
                    "Documentation execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> DocumentationWorkArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise DocumentationWorkforceCorrupt("Documentation artifact file is unsafe")
        if not path.exists():
            raise DocumentationWorkforceNotFound("Documentation artifact was not found")
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
        except DocumentationWorkforceCorrupt:
            raise
        except Exception as error:
            raise DocumentationWorkforceCorrupt("Documentation artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str) or not value or value in {".", ".."}
                or "/" in value or "\\" in value
            ):
                raise DocumentationWorkforceCorrupt(
                    f"Documentation {label} path is invalid"
                )
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise DocumentationWorkforceCorrupt(
                "Documentation artifact path escaped its root"
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
            raise DocumentationWorkforceNotFound(
                "Documentation artifact directory was not found"
            ) from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise DocumentationWorkforceCorrupt(
                "Documentation artifact directory is unsafe"
            )

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing_file: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing_file and entries != {_FILENAME}):
            raise DocumentationWorkforceCorrupt(
                "Documentation artifact directory is not closed"
            )

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise DocumentationWorkforceCorrupt(
                "Documentation artifact file is unsafe"
            ) from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise DocumentationWorkforceCorrupt(
                    "Documentation artifact file is unsafe"
                )
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: DocumentationWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for record, source in zip(payload["sources"], value.sources, strict=True):
        record["business_role"] = source.business_role.value
    for record, document in zip(payload["documents"], value.documents, strict=True):
        record["kind"] = document.kind.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _artifact(value: dict) -> DocumentationWorkArtifact:
    _closed_records(value["sources"], _SOURCE_FIELDS)
    _closed_records(value["documents"], _DOCUMENT_FIELDS)
    for document in value["documents"]:
        _closed_records(document["sections"], _SECTION_FIELDS)
    _closed_record(value["customer_handoff"], _HANDOFF_FIELDS)
    _closed_record(value["status_report"], _STATUS_FIELDS)
    return DocumentationWorkArtifact(
        artifact_id=value["artifact_id"], work_order_id=value["work_order_id"],
        work_order_digest=value["work_order_digest"], tenant_id=value["tenant_id"],
        opportunity_id=value["opportunity_id"], execution_id=value["execution_id"],
        assignment_id=value["assignment_id"], twin_id=value["twin_id"],
        business_role=AgentRole(value["business_role"]), provider_id=value["provider_id"],
        opportunity_digest=value["opportunity_digest"],
        architecture_artifact_id=value["architecture_artifact_id"],
        architecture_artifact_digest=value["architecture_artifact_digest"],
        architecture_status=value["architecture_status"],
        sources=tuple(_source(item) for item in value["sources"]),
        qa_artifact_id=value["qa_artifact_id"],
        qa_artifact_digest=value["qa_artifact_digest"], qa_status=value["qa_status"],
        security_artifact_id=value["security_artifact_id"],
        security_artifact_digest=value["security_artifact_digest"],
        security_status=value["security_status"],
        devops_artifact_id=value["devops_artifact_id"],
        devops_artifact_digest=value["devops_artifact_digest"],
        devops_status=value["devops_status"],
        capability_ids=tuple(value["capability_ids"]), action_ids=tuple(value["action_ids"]),
        title=value["title"], summary=value["summary"],
        documents=tuple(_document(item) for item in value["documents"]),
        customer_handoff=CustomerHandoff(
            handoff_id=value["customer_handoff"]["handoff_id"],
            audience=tuple(value["customer_handoff"]["audience"]),
            readiness_summary=value["customer_handoff"]["readiness_summary"],
            deliverable_document_ids=tuple(value["customer_handoff"]["deliverable_document_ids"]),
            review_checklist=tuple(value["customer_handoff"]["review_checklist"]),
            known_limitations=tuple(value["customer_handoff"]["known_limitations"]),
            next_actions=tuple(value["customer_handoff"]["next_actions"]),
            publication_state=value["customer_handoff"]["publication_state"],
        ),
        acceptance_checks=tuple(value["acceptance_checks"]),
        coverage_requirements=tuple(value["coverage_requirements"]),
        status_report=DocumentationStatusReport(
            state=value["status_report"]["state"],
            completed_items=tuple(value["status_report"]["completed_items"]),
            next_actions=tuple(value["status_report"]["next_actions"]),
            blockers=tuple(value["status_report"]["blockers"]),
            escalations=tuple(value["status_report"]["escalations"]),
        ),
        authority_digest=value["authority_digest"], assignment_digest=value["assignment_digest"],
        request_digest=value["request_digest"], output_digest=value["output_digest"],
        receipt_digest=value["receipt_digest"],
        generated_at=datetime.fromisoformat(value["generated_at"]),
        status=value["status"], pilot_status=value["pilot_status"],
    )


def _source(item: dict) -> DocumentationEngineeringSource:
    return DocumentationEngineeringSource(
        artifact_id=item["artifact_id"], execution_id=item["execution_id"],
        business_role=AgentRole(item["business_role"]), artifact_digest=item["artifact_digest"],
        architecture_artifact_digest=item["architecture_artifact_digest"],
        target_component_ids=tuple(item["target_component_ids"]),
        interface_contract_ids=tuple(item["interface_contract_ids"]),
        status=item["status"], pilot_status=item["pilot_status"],
    )


def _document(item: dict) -> DocumentationRecord:
    return DocumentationRecord(
        document_id=item["document_id"], kind=DocumentationKind(item["kind"]),
        title=item["title"], audience=tuple(item["audience"]), purpose=item["purpose"],
        source_artifact_digests=tuple(item["source_artifact_digests"]),
        sections=tuple(DocumentationSection(**section) for section in item["sections"]),
        validation_checks=tuple(item["validation_checks"]),
        validation_state=item["validation_state"],
        publication_state=item["publication_state"], status=item["status"],
    )


def _closed_records(value: object, keys: set[str]) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, dict) or set(item) != keys for item in value
    ):
        raise ValueError("Documentation nested record is invalid")


def _closed_record(value: object, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Documentation nested record is invalid")
