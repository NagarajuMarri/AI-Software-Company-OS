"""Canonical write-once persistence for Day 30 orchestration artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat

from runtime.workforce_orchestration.errors import (
    WorkforceOrchestrationConflict,
    WorkforceOrchestrationCorrupt,
    WorkforceOrchestrationNotFound,
)
from runtime.workforce_orchestration.models import (
    ConflictRoute,
    ContextPackage,
    DependencyNode,
    EscalationRecord,
    HandoffRecord,
    MultiAgentOrchestrationArtifact,
    OrchestrationSourceKind,
    OrchestrationStatusReport,
    ParallelWave,
    SourceBinding,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "multi-agent-orchestration-v1.json"
_MAX_BYTES = 512_000
_ARTIFACT_FIELDS = {item.name for item in fields(MultiAgentOrchestrationArtifact)}
_SOURCE_FIELDS = {item.name for item in fields(SourceBinding)}
_NODE_FIELDS = {item.name for item in fields(DependencyNode)}
_WAVE_FIELDS = {item.name for item in fields(ParallelWave)}
_CONTEXT_FIELDS = {item.name for item in fields(ContextPackage)}
_HANDOFF_FIELDS = {item.name for item in fields(HandoffRecord)}
_CONFLICT_FIELDS = {item.name for item in fields(ConflictRoute)}
_ESCALATION_FIELDS = {item.name for item in fields(EscalationRecord)}
_STATUS_FIELDS = {item.name for item in fields(OrchestrationStatusReport)}


class FileOrchestrationArtifactStore:
    """Tenant/execution-scoped store with closed-schema integrity controls."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Orchestration artifact root must be a Path")
        self._root = root

    def save(
        self, artifact: MultiAgentOrchestrationArtifact
    ) -> MultiAgentOrchestrationArtifact:
        if not isinstance(artifact, MultiAgentOrchestrationArtifact):
            raise TypeError("Orchestration artifact is invalid")
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
            raise WorkforceOrchestrationConflict("Orchestration artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise WorkforceOrchestrationConflict(
                    "Orchestration execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> MultiAgentOrchestrationArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise WorkforceOrchestrationCorrupt("Orchestration artifact file is unsafe")
        if not path.exists():
            raise WorkforceOrchestrationNotFound("Orchestration artifact was not found")
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
        except WorkforceOrchestrationCorrupt:
            raise
        except Exception as error:
            raise WorkforceOrchestrationCorrupt("Orchestration artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise WorkforceOrchestrationCorrupt(f"Orchestration {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise WorkforceOrchestrationCorrupt(
                "Orchestration artifact path escaped its root"
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
            raise WorkforceOrchestrationNotFound(
                "Orchestration artifact directory was not found"
            ) from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise WorkforceOrchestrationCorrupt(
                "Orchestration artifact directory is unsafe"
            )

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing_file: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (not allow_missing_file and entries != {_FILENAME}):
            raise WorkforceOrchestrationCorrupt(
                "Orchestration artifact directory is not closed"
            )

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise WorkforceOrchestrationCorrupt(
                "Orchestration artifact file is unsafe"
            ) from error
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise WorkforceOrchestrationCorrupt(
                    "Orchestration artifact file is unsafe"
                )
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: MultiAgentOrchestrationArtifact) -> dict[str, object]:
    payload = asdict(value)
    for record, source in zip(payload["source_bindings"], value.source_bindings, strict=True):
        record["kind"] = source.kind.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _artifact(value: dict) -> MultiAgentOrchestrationArtifact:
    _closed_records(value["source_bindings"], _SOURCE_FIELDS)
    _closed_records(value["dependency_nodes"], _NODE_FIELDS)
    _closed_records(value["parallel_waves"], _WAVE_FIELDS)
    _closed_records(value["context_packages"], _CONTEXT_FIELDS)
    _closed_records(value["handoffs"], _HANDOFF_FIELDS)
    _closed_records(value["conflicts"], _CONFLICT_FIELDS)
    _closed_records(value["escalations"], _ESCALATION_FIELDS)
    _closed_record(value["status_report"], _STATUS_FIELDS)
    return MultiAgentOrchestrationArtifact(
        artifact_id=value["artifact_id"],
        work_order_id=value["work_order_id"],
        work_order_digest=value["work_order_digest"],
        tenant_id=value["tenant_id"],
        opportunity_id=value["opportunity_id"],
        execution_id=value["execution_id"],
        assignment_id=value["assignment_id"],
        provider_id=value["provider_id"],
        authority_digest=value["authority_digest"],
        source_set_digest=value["source_set_digest"],
        source_bindings=tuple(
            SourceBinding(
                kind=OrchestrationSourceKind(item["kind"]),
                artifact_id=item["artifact_id"],
                artifact_digest=item["artifact_digest"],
                status=item["status"],
            )
            for item in value["source_bindings"]
        ),
        capability_ids=tuple(value["capability_ids"]),
        action_ids=tuple(value["action_ids"]),
        dependency_nodes=tuple(_node(item) for item in value["dependency_nodes"]),
        parallel_waves=tuple(_wave(item) for item in value["parallel_waves"]),
        context_packages=tuple(_context(item) for item in value["context_packages"]),
        handoffs=tuple(_handoff(item) for item in value["handoffs"]),
        conflicts=tuple(_conflict(item) for item in value["conflicts"]),
        escalations=tuple(_escalation(item) for item in value["escalations"]),
        status_report=OrchestrationStatusReport(
            state=value["status_report"]["state"],
            completed_items=tuple(value["status_report"]["completed_items"]),
            next_actions=tuple(value["status_report"]["next_actions"]),
            blockers=tuple(value["status_report"]["blockers"]),
            escalations=tuple(value["status_report"]["escalations"]),
        ),
        provider_output_digest=value["provider_output_digest"],
        generated_at=datetime.fromisoformat(value["generated_at"]),
        execution_state=value["execution_state"],
        status=value["status"],
        pilot_status=value["pilot_status"],
    )


def _node(value: dict) -> DependencyNode:
    return DependencyNode(
        value["node_id"], value["owner"], value["objective"],
        tuple(value["dependency_node_ids"]), tuple(value["source_artifact_digests"]),
        value["execution_state"],
    )


def _wave(value: dict) -> ParallelWave:
    return ParallelWave(
        value["wave_id"], value["sequence"], tuple(value["node_ids"]),
        tuple(value["entry_checks"]), tuple(value["exit_checks"]),
        value["max_parallelism"], value["execution_state"],
    )


def _context(value: dict) -> ContextPackage:
    return ContextPackage(
        value["context_id"], value["target_node_id"],
        tuple(value["allowed_source_digests"]), tuple(value["included_fields"]),
        tuple(value["excluded_data_classes"]), value["context_digest"],
    )


def _handoff(value: dict) -> HandoffRecord:
    return HandoffRecord(
        value["handoff_id"], tuple(value["source_node_ids"]),
        tuple(value["target_node_ids"]), tuple(value["artifact_digests"]),
        tuple(value["acceptance_checks"]), value["state"],
    )


def _conflict(value: dict) -> ConflictRoute:
    return ConflictRoute(
        value["conflict_id"], tuple(value["participant_node_ids"]), value["subject"],
        value["detection_rule"], value["resolution_owner"], value["resolution_policy"],
        value["downstream_blocked"], value["state"],
    )


def _escalation(value: dict) -> EscalationRecord:
    return EscalationRecord(
        value["escalation_id"], value["trigger"], value["human_owner"],
        tuple(value["required_evidence_digests"]),
        tuple(value["permitted_decisions"]), value["state"],
    )


def _closed_records(values: object, expected: set[str]) -> None:
    if (
        not isinstance(values, list)
        or any(not isinstance(item, dict) or set(item) != expected for item in values)
    ):
        raise ValueError("nested records are invalid")


def _closed_record(value: object, expected: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("nested record is invalid")
