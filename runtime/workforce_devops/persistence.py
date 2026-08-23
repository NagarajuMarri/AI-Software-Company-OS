"""Canonical write-once storage for validated Day 28 DevOps artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.agents import AgentRole
from runtime.workforce_devops.errors import (
    DevOpsWorkforceConflict,
    DevOpsWorkforceCorrupt,
    DevOpsWorkforceNotFound,
)
from runtime.workforce_devops.models import (
    CIPipelinePlan,
    DeploymentPlan,
    DevOpsEngineeringSource,
    DevOpsStatusReport,
    DevOpsWorkArtifact,
    MigrationPlan,
    MonitoringPlan,
    PreviewEnvironmentPlan,
    RollbackPlan,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "devops-work-v1.json"
_MAX_BYTES = 384_000
_ARTIFACT_FIELDS = {item.name for item in fields(DevOpsWorkArtifact)}
_SOURCE_FIELDS = {item.name for item in fields(DevOpsEngineeringSource)}
_CI_FIELDS = {item.name for item in fields(CIPipelinePlan)}
_PREVIEW_FIELDS = {item.name for item in fields(PreviewEnvironmentPlan)}
_MIGRATION_FIELDS = {item.name for item in fields(MigrationPlan)}
_DEPLOYMENT_FIELDS = {item.name for item in fields(DeploymentPlan)}
_MONITORING_FIELDS = {item.name for item in fields(MonitoringPlan)}
_ROLLBACK_FIELDS = {item.name for item in fields(RollbackPlan)}
_STATUS_FIELDS = {item.name for item in fields(DevOpsStatusReport)}


class FileDevOpsArtifactStore:
    """Tenant/execution-scoped DevOps storage with integrity controls."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("DevOps artifact root must be a Path")
        self._root = root

    def save(self, artifact: DevOpsWorkArtifact) -> DevOpsWorkArtifact:
        if not isinstance(artifact, DevOpsWorkArtifact):
            raise TypeError("DevOps artifact is invalid")
        directory = self._execution_directory(artifact.tenant_id, artifact.execution_id)
        self._ensure_directory(directory)
        path = directory / _FILENAME
        envelope = {"schema_version": _SCHEMA_VERSION, "digest": artifact.digest, "record": _record(artifact)}
        content = canonical_json(envelope).encode("utf-8")
        if len(content) > _MAX_BYTES:
            raise DevOpsWorkforceConflict("DevOps artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise DevOpsWorkforceConflict("DevOps execution already has a different artifact")
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

    def load(self, tenant_id: str, execution_id: str) -> DevOpsWorkArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise DevOpsWorkforceCorrupt("DevOps artifact file is unsafe")
        if not path.exists():
            raise DevOpsWorkforceNotFound("DevOps artifact was not found")
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
        except DevOpsWorkforceCorrupt:
            raise
        except Exception as error:
            raise DevOpsWorkforceCorrupt("DevOps artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if not isinstance(value, str) or not value or value in {".", ".."} or "/" in value or "\\" in value:
                raise DevOpsWorkforceCorrupt(f"DevOps {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise DevOpsWorkforceCorrupt("DevOps artifact path escaped its root") from error
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
            raise DevOpsWorkforceNotFound("DevOps artifact directory was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise DevOpsWorkforceCorrupt("DevOps artifact directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing_file: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing_file and entries != {_FILENAME}):
            raise DevOpsWorkforceCorrupt("DevOps artifact directory is not closed")

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise DevOpsWorkforceCorrupt("DevOps artifact file is unsafe") from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise DevOpsWorkforceCorrupt("DevOps artifact file is unsafe")
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: DevOpsWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for record, source in zip(payload["sources"], value.sources, strict=True):
        record["business_role"] = source.business_role.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _artifact(value: dict) -> DevOpsWorkArtifact:
    _closed_records(value["sources"], _SOURCE_FIELDS)
    for key, expected in (
        ("ci_pipeline", _CI_FIELDS), ("preview_environment", _PREVIEW_FIELDS),
        ("migration_plan", _MIGRATION_FIELDS), ("deployment_plan", _DEPLOYMENT_FIELDS),
        ("monitoring_plan", _MONITORING_FIELDS), ("rollback_plan", _ROLLBACK_FIELDS),
        ("status_report", _STATUS_FIELDS),
    ):
        _closed_record(value[key], expected)
    return DevOpsWorkArtifact(
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
        qa_artifact_id=value["qa_artifact_id"], qa_execution_id=value["qa_execution_id"],
        qa_artifact_digest=value["qa_artifact_digest"], qa_status=value["qa_status"],
        security_artifact_id=value["security_artifact_id"],
        security_execution_id=value["security_execution_id"],
        security_artifact_digest=value["security_artifact_digest"],
        security_status=value["security_status"],
        capability_ids=tuple(value["capability_ids"]), action_ids=tuple(value["action_ids"]),
        title=value["title"], summary=value["summary"],
        ci_pipeline=_ci(value["ci_pipeline"]),
        preview_environment=_preview(value["preview_environment"]),
        migration_plan=_migration(value["migration_plan"]),
        deployment_plan=_deployment(value["deployment_plan"]),
        monitoring_plan=_monitoring(value["monitoring_plan"]),
        rollback_plan=_rollback(value["rollback_plan"]),
        acceptance_checks=tuple(value["acceptance_checks"]),
        coverage_requirements=tuple(value["coverage_requirements"]),
        handoff_notes=tuple(value["handoff_notes"]),
        status_report=DevOpsStatusReport(
            state=value["status_report"]["state"],
            completed_items=tuple(value["status_report"]["completed_items"]),
            next_actions=tuple(value["status_report"]["next_actions"]),
            blockers=tuple(value["status_report"]["blockers"]),
            escalations=tuple(value["status_report"]["escalations"]),
        ),
        authority_digest=value["authority_digest"], assignment_digest=value["assignment_digest"],
        request_digest=value["request_digest"], output_digest=value["output_digest"],
        receipt_digest=value["receipt_digest"], generated_at=datetime.fromisoformat(value["generated_at"]),
        status=value["status"], pilot_status=value["pilot_status"],
    )


def _source(item: dict) -> DevOpsEngineeringSource:
    return DevOpsEngineeringSource(
        artifact_id=item["artifact_id"], execution_id=item["execution_id"],
        business_role=AgentRole(item["business_role"]), artifact_digest=item["artifact_digest"],
        architecture_artifact_digest=item["architecture_artifact_digest"],
        target_component_ids=tuple(item["target_component_ids"]),
        interface_contract_ids=tuple(item["interface_contract_ids"]),
        status=item["status"], pilot_status=item["pilot_status"],
    )


def _ci(item: dict) -> CIPipelinePlan:
    return CIPipelinePlan(
        plan_id=item["plan_id"], source_engineering_artifact_digests=tuple(item["source_engineering_artifact_digests"]),
        qa_artifact_digest=item["qa_artifact_digest"], security_artifact_digest=item["security_artifact_digest"],
        stages=tuple(item["stages"]), required_gates=tuple(item["required_gates"]),
        artifact_requirements=tuple(item["artifact_requirements"]), failure_policy=item["failure_policy"],
        execution_state=item["execution_state"],
    )


def _preview(item: dict) -> PreviewEnvironmentPlan:
    return PreviewEnvironmentPlan(
        plan_id=item["plan_id"], environment_class=item["environment_class"],
        target_component_ids=tuple(item["target_component_ids"]),
        isolation_controls=tuple(item["isolation_controls"]),
        configuration_contract=tuple(item["configuration_contract"]),
        secret_reference_policy=item["secret_reference_policy"],
        health_checks=tuple(item["health_checks"]), lifecycle_steps=tuple(item["lifecycle_steps"]),
        execution_state=item["execution_state"],
    )


def _migration(item: dict) -> MigrationPlan:
    return MigrationPlan(
        plan_id=item["plan_id"], data_engineering_artifact_digest=item["data_engineering_artifact_digest"],
        target_component_ids=tuple(item["target_component_ids"]), migration_scopes=tuple(item["migration_scopes"]),
        preflight_checks=tuple(item["preflight_checks"]), apply_steps=tuple(item["apply_steps"]),
        verification_steps=tuple(item["verification_steps"]), rollback_steps=tuple(item["rollback_steps"]),
        execution_state=item["execution_state"],
    )


def _deployment(item: dict) -> DeploymentPlan:
    return DeploymentPlan(
        plan_id=item["plan_id"], target_environment=item["target_environment"],
        source_engineering_artifact_digests=tuple(item["source_engineering_artifact_digests"]),
        qa_artifact_digest=item["qa_artifact_digest"], security_artifact_digest=item["security_artifact_digest"],
        prerequisites=tuple(item["prerequisites"]), deployment_steps=tuple(item["deployment_steps"]),
        approval_gates=tuple(item["approval_gates"]), evidence_requirements=tuple(item["evidence_requirements"]),
        success_criteria=tuple(item["success_criteria"]), execution_state=item["execution_state"],
    )


def _monitoring(item: dict) -> MonitoringPlan:
    return MonitoringPlan(
        plan_id=item["plan_id"], target_environment=item["target_environment"],
        signals=tuple(item["signals"]), alert_conditions=tuple(item["alert_conditions"]),
        dashboard_requirements=tuple(item["dashboard_requirements"]),
        evidence_requirements=tuple(item["evidence_requirements"]), execution_state=item["execution_state"],
    )


def _rollback(item: dict) -> RollbackPlan:
    return RollbackPlan(
        plan_id=item["plan_id"], target_environment=item["target_environment"],
        deployment_plan_id=item["deployment_plan_id"], migration_plan_id=item["migration_plan_id"],
        triggers=tuple(item["triggers"]), rollback_steps=tuple(item["rollback_steps"]),
        data_safety_controls=tuple(item["data_safety_controls"]),
        verification_steps=tuple(item["verification_steps"]), escalation_policy=item["escalation_policy"],
        execution_state=item["execution_state"],
    )


def _closed_records(value: object, keys: set[str]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, dict) or set(item) != keys for item in value):
        raise ValueError("DevOps nested record is invalid")


def _closed_record(value: object, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("DevOps nested record is invalid")
