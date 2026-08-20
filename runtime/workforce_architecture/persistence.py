"""Canonical write-once storage for validated Software Architect proposals."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat
from typing import Any

from runtime.agents import AgentRole
from runtime.workforce_architecture.errors import (
    ArchitectureWorkforceConflict,
    ArchitectureWorkforceCorrupt,
    ArchitectureWorkforceNotFound,
)
from runtime.workforce_architecture.models import (
    ArchitectureComponent,
    ArchitectureDecisionDraft,
    ArchitectureProposalArtifact,
    ArchitectureStatusReport,
    RiskLikelihood,
    RiskSeverity,
    TechnicalRisk,
    TechnologyRecommendation,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "architecture-proposal-v1.json"
_MAX_BYTES = 256_000
_ARTIFACT_FIELDS = {item.name for item in fields(ArchitectureProposalArtifact)}
_COMPONENT_FIELDS = {item.name for item in fields(ArchitectureComponent)}
_TECHNOLOGY_FIELDS = {item.name for item in fields(TechnologyRecommendation)}
_ADR_FIELDS = {item.name for item in fields(ArchitectureDecisionDraft)}
_RISK_FIELDS = {item.name for item in fields(TechnicalRisk)}
_STATUS_FIELDS = {item.name for item in fields(ArchitectureStatusReport)}


class FileArchitectureArtifactStore:
    """Tenant/execution-scoped architecture storage with integrity controls."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Architecture artifact root must be a Path")
        self._root = root

    def save(self, artifact: ArchitectureProposalArtifact) -> ArchitectureProposalArtifact:
        if not isinstance(artifact, ArchitectureProposalArtifact):
            raise TypeError("Architecture artifact is invalid")
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
            raise ArchitectureWorkforceConflict("Architecture artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise ArchitectureWorkforceConflict(
                    "Architecture execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> ArchitectureProposalArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise ArchitectureWorkforceCorrupt("Architecture artifact file is unsafe")
        if not path.exists():
            raise ArchitectureWorkforceNotFound("Architecture artifact was not found")
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
        except ArchitectureWorkforceCorrupt:
            raise
        except Exception as error:
            raise ArchitectureWorkforceCorrupt(
                "Architecture artifact is corrupt"
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
                raise ArchitectureWorkforceCorrupt(f"Architecture {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ArchitectureWorkforceCorrupt(
                "Architecture artifact path escaped its root"
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
            raise ArchitectureWorkforceNotFound(
                "Architecture artifact directory was not found"
            ) from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise ArchitectureWorkforceCorrupt("Architecture artifact directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing_file: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (
            not allow_missing_file and entries != {_FILENAME}
        ):
            raise ArchitectureWorkforceCorrupt(
                "Architecture artifact directory is not closed"
            )

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise ArchitectureWorkforceCorrupt(
                "Architecture artifact file is unsafe"
            ) from error
        try:
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or stat.S_IMODE(details.st_mode) != 0o600
            ):
                raise ArchitectureWorkforceCorrupt(
                    "Architecture artifact file is unsafe"
                )
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: ArchitectureProposalArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for risk, source in zip(payload["technical_risks"], value.technical_risks, strict=True):
        risk["severity"] = source.severity.value
        risk["likelihood"] = source.likelihood.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _artifact(value: dict[str, Any]) -> ArchitectureProposalArtifact:
    components = value["components"]
    technologies = value["technology_recommendations"]
    adrs = value["adr_drafts"]
    risks = value["technical_risks"]
    status = value["status_report"]
    if (
        not isinstance(components, list)
        or any(not isinstance(item, dict) or set(item) != _COMPONENT_FIELDS for item in components)
        or not isinstance(technologies, list)
        or any(not isinstance(item, dict) or set(item) != _TECHNOLOGY_FIELDS for item in technologies)
        or not isinstance(adrs, list)
        or any(not isinstance(item, dict) or set(item) != _ADR_FIELDS for item in adrs)
        or not isinstance(risks, list)
        or any(not isinstance(item, dict) or set(item) != _RISK_FIELDS for item in risks)
        or not isinstance(status, dict)
        or set(status) != _STATUS_FIELDS
    ):
        raise ValueError("Architecture nested record is invalid")
    return ArchitectureProposalArtifact(
        artifact_id=value["artifact_id"],
        tenant_id=value["tenant_id"],
        opportunity_id=value["opportunity_id"],
        execution_id=value["execution_id"],
        assignment_id=value["assignment_id"],
        twin_id=value["twin_id"],
        business_role=AgentRole(value["business_role"]),
        provider_id=value["provider_id"],
        opportunity_digest=value["opportunity_digest"],
        product_manager_artifact_digest=value["product_manager_artifact_digest"],
        title=value["title"],
        summary=value["summary"],
        domain_boundary=value["domain_boundary"],
        principles=tuple(value["principles"]),
        components=tuple(
            ArchitectureComponent(
                component_id=item["component_id"],
                name=item["name"],
                responsibility=item["responsibility"],
                interfaces=tuple(item["interfaces"]),
                data_responsibility=item["data_responsibility"],
            )
            for item in components
        ),
        integration_points=tuple(value["integration_points"]),
        data_lifecycle=tuple(value["data_lifecycle"]),
        security_controls=tuple(value["security_controls"]),
        quality_strategy=tuple(value["quality_strategy"]),
        technology_recommendations=tuple(
            TechnologyRecommendation(
                recommendation_id=item["recommendation_id"],
                area=item["area"],
                technology=item["technology"],
                rationale=item["rationale"],
                alternatives_considered=tuple(item["alternatives_considered"]),
                status=item["status"],
            )
            for item in technologies
        ),
        adr_drafts=tuple(
            ArchitectureDecisionDraft(
                adr_id=item["adr_id"],
                title=item["title"],
                context=item["context"],
                decision=item["decision"],
                consequences=tuple(item["consequences"]),
                status=item["status"],
                human_approval_required=item["human_approval_required"],
            )
            for item in adrs
        ),
        technical_risks=tuple(
            TechnicalRisk(
                risk_id=item["risk_id"],
                title=item["title"],
                severity=RiskSeverity(item["severity"]),
                likelihood=RiskLikelihood(item["likelihood"]),
                impact=item["impact"],
                mitigation=item["mitigation"],
                escalation=item["escalation"],
            )
            for item in risks
        ),
        status_report=ArchitectureStatusReport(
            state=status["state"],
            completed_items=tuple(status["completed_items"]),
            next_actions=tuple(status["next_actions"]),
            blockers=tuple(status["blockers"]),
            human_decisions_required=tuple(status["human_decisions_required"]),
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
