"""Canonical write-once storage for validated Day 27 Security artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.agents import AgentRole
from runtime.workforce_security.errors import (
    SecurityWorkforceConflict,
    SecurityWorkforceCorrupt,
    SecurityWorkforceNotFound,
)
from runtime.workforce_security.models import (
    DependencyCheckKind,
    DependencyCheckSpec,
    SecretCheckSpec,
    SecurityEngineeringSource,
    SecurityFinding,
    SecurityFindingKind,
    SecuritySeverity,
    SecurityStatusReport,
    SecurityThreat,
    SecurityWorkArtifact,
    ThreatCategory,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "security-work-v1.json"
_MAX_BYTES = 384_000
_ARTIFACT_FIELDS = {item.name for item in fields(SecurityWorkArtifact)}
_SOURCE_FIELDS = {item.name for item in fields(SecurityEngineeringSource)}
_THREAT_FIELDS = {item.name for item in fields(SecurityThreat)}
_DEPENDENCY_FIELDS = {item.name for item in fields(DependencyCheckSpec)}
_SECRET_FIELDS = {item.name for item in fields(SecretCheckSpec)}
_FINDING_FIELDS = {item.name for item in fields(SecurityFinding)}
_STATUS_FIELDS = {item.name for item in fields(SecurityStatusReport)}


class FileSecurityArtifactStore:
    """Tenant/execution-scoped Security storage with integrity controls."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Security artifact root must be a Path")
        self._root = root

    def save(self, artifact: SecurityWorkArtifact) -> SecurityWorkArtifact:
        if not isinstance(artifact, SecurityWorkArtifact):
            raise TypeError("Security artifact is invalid")
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
            raise SecurityWorkforceConflict("Security artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise SecurityWorkforceConflict(
                    "Security execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> SecurityWorkArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise SecurityWorkforceCorrupt("Security artifact file is unsafe")
        if not path.exists():
            raise SecurityWorkforceNotFound("Security artifact was not found")
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
            if content != canonical_json(envelope).encode("utf-8"):
                raise ValueError("record is not canonical")
            return artifact
        except SecurityWorkforceCorrupt:
            raise
        except Exception as error:
            raise SecurityWorkforceCorrupt("Security artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise SecurityWorkforceCorrupt(f"Security {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise SecurityWorkforceCorrupt("Security artifact path escaped its root") from error
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
            raise SecurityWorkforceNotFound("Security artifact directory was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise SecurityWorkforceCorrupt("Security artifact directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing_file: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing_file and entries != {_FILENAME}):
            raise SecurityWorkforceCorrupt("Security artifact directory is not closed")

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise SecurityWorkforceCorrupt("Security artifact file is unsafe") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise SecurityWorkforceCorrupt("Security artifact file is unsafe")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: SecurityWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for record, source in zip(payload["sources"], value.sources, strict=True):
        record["business_role"] = source.business_role.value
    for record, threat in zip(payload["threats"], value.threats, strict=True):
        record["category"] = threat.category.value
    for record, check in zip(payload["dependency_checks"], value.dependency_checks, strict=True):
        record["kind"] = check.kind.value
        record["failure_threshold"] = check.failure_threshold.value
    for record, finding in zip(payload["findings"], value.findings, strict=True):
        record["kind"] = finding.kind.value
        record["severity"] = finding.severity.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _artifact(value: dict) -> SecurityWorkArtifact:
    _closed_records(value["sources"], _SOURCE_FIELDS)
    _closed_records(value["threats"], _THREAT_FIELDS)
    _closed_records(value["dependency_checks"], _DEPENDENCY_FIELDS)
    _closed_records(value["secret_checks"], _SECRET_FIELDS)
    _closed_records(value["findings"], _FINDING_FIELDS)
    _closed_record(value["status_report"], _STATUS_FIELDS)
    return SecurityWorkArtifact(
        artifact_id=value["artifact_id"],
        work_order_id=value["work_order_id"],
        work_order_digest=value["work_order_digest"],
        tenant_id=value["tenant_id"],
        opportunity_id=value["opportunity_id"],
        execution_id=value["execution_id"],
        assignment_id=value["assignment_id"],
        twin_id=value["twin_id"],
        business_role=AgentRole(value["business_role"]),
        provider_id=value["provider_id"],
        opportunity_digest=value["opportunity_digest"],
        architecture_artifact_id=value["architecture_artifact_id"],
        architecture_artifact_digest=value["architecture_artifact_digest"],
        architecture_status=value["architecture_status"],
        sources=tuple(_source(item) for item in value["sources"]),
        qa_artifact_id=value["qa_artifact_id"],
        qa_execution_id=value["qa_execution_id"],
        qa_artifact_digest=value["qa_artifact_digest"],
        qa_status=value["qa_status"],
        capability_ids=tuple(value["capability_ids"]),
        action_ids=tuple(value["action_ids"]),
        title=value["title"],
        summary=value["summary"],
        threats=tuple(_threat(item) for item in value["threats"]),
        dependency_checks=tuple(_dependency(item) for item in value["dependency_checks"]),
        secret_checks=tuple(_secret(item) for item in value["secret_checks"]),
        findings=tuple(_finding(item) for item in value["findings"]),
        acceptance_checks=tuple(value["acceptance_checks"]),
        coverage_requirements=tuple(value["coverage_requirements"]),
        handoff_notes=tuple(value["handoff_notes"]),
        status_report=SecurityStatusReport(
            state=value["status_report"]["state"],
            completed_items=tuple(value["status_report"]["completed_items"]),
            next_actions=tuple(value["status_report"]["next_actions"]),
            blockers=tuple(value["status_report"]["blockers"]),
            escalations=tuple(value["status_report"]["escalations"]),
        ),
        authority_digest=value["authority_digest"],
        assignment_digest=value["assignment_digest"],
        request_digest=value["request_digest"],
        output_digest=value["output_digest"],
        receipt_digest=value["receipt_digest"],
        generated_at=datetime.fromisoformat(value["generated_at"]),
        status=value["status"],
        pilot_status=value["pilot_status"],
    )


def _source(item: dict) -> SecurityEngineeringSource:
    return SecurityEngineeringSource(
        artifact_id=item["artifact_id"],
        execution_id=item["execution_id"],
        business_role=AgentRole(item["business_role"]),
        artifact_digest=item["artifact_digest"],
        architecture_artifact_digest=item["architecture_artifact_digest"],
        target_component_ids=tuple(item["target_component_ids"]),
        interface_contract_ids=tuple(item["interface_contract_ids"]),
        status=item["status"],
        pilot_status=item["pilot_status"],
    )


def _threat(item: dict) -> SecurityThreat:
    return SecurityThreat(
        threat_id=item["threat_id"],
        category=ThreatCategory(item["category"]),
        source_engineering_artifact_digests=tuple(item["source_engineering_artifact_digests"]),
        target_component_ids=tuple(item["target_component_ids"]),
        asset=item["asset"],
        trust_boundary=item["trust_boundary"],
        scenario=item["scenario"],
        security_properties=tuple(item["security_properties"]),
        mitigations=tuple(item["mitigations"]),
        residual_risk=item["residual_risk"],
        validation_state=item["validation_state"],
    )


def _dependency(item: dict) -> DependencyCheckSpec:
    return DependencyCheckSpec(
        check_id=item["check_id"],
        kind=DependencyCheckKind(item["kind"]),
        source_engineering_artifact_digest=item["source_engineering_artifact_digest"],
        target_component_ids=tuple(item["target_component_ids"]),
        manifest_scope=item["manifest_scope"],
        required_checks=tuple(item["required_checks"]),
        failure_threshold=SecuritySeverity(item["failure_threshold"]),
        expected_evidence=tuple(item["expected_evidence"]),
        execution_state=item["execution_state"],
    )


def _secret(item: dict) -> SecretCheckSpec:
    return SecretCheckSpec(
        check_id=item["check_id"],
        source_engineering_artifact_digest=item["source_engineering_artifact_digest"],
        target_component_ids=tuple(item["target_component_ids"]),
        search_scopes=tuple(item["search_scopes"]),
        detector_classes=tuple(item["detector_classes"]),
        allowlist_policy=item["allowlist_policy"],
        incident_response=item["incident_response"],
        expected_evidence=tuple(item["expected_evidence"]),
        execution_state=item["execution_state"],
    )


def _finding(item: dict) -> SecurityFinding:
    return SecurityFinding(
        finding_id=item["finding_id"],
        kind=SecurityFindingKind(item["kind"]),
        severity=SecuritySeverity(item["severity"]),
        source_engineering_artifact_digests=tuple(item["source_engineering_artifact_digests"]),
        qa_artifact_digest=item["qa_artifact_digest"],
        title=item["title"],
        evidence_basis=item["evidence_basis"],
        risk=item["risk"],
        recommendation=item["recommendation"],
        verification_requirements=tuple(item["verification_requirements"]),
        status=item["status"],
    )


def _closed_records(value: object, keys: set[str]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, dict) or set(item) != keys for item in value):
        raise ValueError("Security nested record is invalid")


def _closed_record(value: object, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Security nested record is invalid")
