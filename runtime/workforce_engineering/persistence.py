"""Canonical write-once storage for validated Day 25 Engineering artifacts."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import json
import os
from pathlib import Path
import stat
from typing import Any

from runtime.agents import AgentRole
from runtime.workforce_engineering.errors import (
    EngineeringWorkforceConflict,
    EngineeringWorkforceCorrupt,
    EngineeringWorkforceNotFound,
)
from runtime.workforce_engineering.models import (
    EngineeringChangeKind,
    EngineeringContractKind,
    EngineeringDiscipline,
    EngineeringImplementationItem,
    EngineeringInterfaceContract,
    EngineeringStatusReport,
    EngineeringWorkArtifact,
    canonical_json,
)


_SCHEMA_VERSION = 1
_FILENAME = "engineering-work-v1.json"
_MAX_BYTES = 256_000
_ARTIFACT_FIELDS = {item.name for item in fields(EngineeringWorkArtifact)}
_IMPLEMENTATION_FIELDS = {item.name for item in fields(EngineeringImplementationItem)}
_INTERFACE_FIELDS = {item.name for item in fields(EngineeringInterfaceContract)}
_STATUS_FIELDS = {item.name for item in fields(EngineeringStatusReport)}


class FileEngineeringArtifactStore:
    """Tenant/execution-scoped Engineering storage with integrity controls."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("Engineering artifact root must be a Path")
        self._root = root

    def save(self, artifact: EngineeringWorkArtifact) -> EngineeringWorkArtifact:
        if not isinstance(artifact, EngineeringWorkArtifact):
            raise TypeError("Engineering artifact is invalid")
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
            raise EngineeringWorkforceConflict("Engineering artifact exceeds storage limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self.load(artifact.tenant_id, artifact.execution_id)
            if existing != artifact:
                raise EngineeringWorkforceConflict(
                    "Engineering execution already has a different artifact"
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

    def load(self, tenant_id: str, execution_id: str) -> EngineeringWorkArtifact:
        directory = self._execution_directory(tenant_id, execution_id)
        path = directory / _FILENAME
        if path.is_symlink():
            raise EngineeringWorkforceCorrupt("Engineering artifact file is unsafe")
        if not path.exists():
            raise EngineeringWorkforceNotFound("Engineering artifact was not found")
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
        except EngineeringWorkforceCorrupt:
            raise
        except Exception as error:
            raise EngineeringWorkforceCorrupt("Engineering artifact is corrupt") from error

    def _execution_directory(self, tenant_id: str, execution_id: str) -> Path:
        for value, label in ((tenant_id, "tenant"), (execution_id, "execution")):
            if (
                not isinstance(value, str)
                or not value
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
            ):
                raise EngineeringWorkforceCorrupt(f"Engineering {label} path is invalid")
        root = self._root.absolute()
        target = root / tenant_id / execution_id
        try:
            target.relative_to(root)
        except ValueError as error:
            raise EngineeringWorkforceCorrupt(
                "Engineering artifact path escaped its root"
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
            raise EngineeringWorkforceNotFound(
                "Engineering artifact directory was not found"
            ) from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise EngineeringWorkforceCorrupt("Engineering artifact directory is unsafe")

    @staticmethod
    def _require_closed(directory: Path, *, allow_missing_file: bool) -> None:
        entries = {item.name for item in directory.iterdir()}
        if not entries <= {_FILENAME} or (
            not allow_missing_file and entries != {_FILENAME}
        ):
            raise EngineeringWorkforceCorrupt(
                "Engineering artifact directory is not closed"
            )

    @staticmethod
    def _read_file(path: Path) -> bytes:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise EngineeringWorkforceCorrupt(
                "Engineering artifact file is unsafe"
            ) from error
        try:
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or stat.S_IMODE(details.st_mode) != 0o600
            ):
                raise EngineeringWorkforceCorrupt(
                    "Engineering artifact file is unsafe"
                )
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                return handle.read(_MAX_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _record(value: EngineeringWorkArtifact) -> dict[str, object]:
    payload = asdict(value)
    payload["business_role"] = value.business_role.value
    for item, source in zip(
        payload["implementation_items"], value.implementation_items, strict=True
    ):
        item["discipline"] = source.discipline.value
        item["change_kind"] = source.change_kind.value
    for contract, contract_source in zip(
        payload["interface_contracts"], value.interface_contracts, strict=True
    ):
        contract["kind"] = contract_source.kind.value
    payload["generated_at"] = value.generated_at.isoformat()
    return payload


def _artifact(value: dict[str, Any]) -> EngineeringWorkArtifact:
    implementation_items = value["implementation_items"]
    interface_contracts = value["interface_contracts"]
    status = value["status_report"]
    if (
        not isinstance(implementation_items, list)
        or any(
            not isinstance(item, dict) or set(item) != _IMPLEMENTATION_FIELDS
            for item in implementation_items
        )
        or not isinstance(interface_contracts, list)
        or any(
            not isinstance(item, dict)
            or set(item) != _INTERFACE_FIELDS
            or not isinstance(item["inputs"], list)
            or any(not isinstance(value, str) for value in item["inputs"])
            or not isinstance(item["outputs"], list)
            or any(not isinstance(value, str) for value in item["outputs"])
            for item in interface_contracts
        )
        or not isinstance(status, dict)
        or set(status) != _STATUS_FIELDS
    ):
        raise ValueError("Engineering nested record is invalid")
    return EngineeringWorkArtifact(
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
        target_component_ids=tuple(value["target_component_ids"]),
        capability_ids=tuple(value["capability_ids"]),
        action_ids=tuple(value["action_ids"]),
        title=value["title"],
        summary=value["summary"],
        implementation_items=tuple(
            EngineeringImplementationItem(
                item_id=item["item_id"],
                discipline=EngineeringDiscipline(item["discipline"]),
                target_component_id=item["target_component_id"],
                change_kind=EngineeringChangeKind(item["change_kind"]),
                implementation=item["implementation"],
                expected_outcome=item["expected_outcome"],
            )
            for item in implementation_items
        ),
        interface_contracts=tuple(
            EngineeringInterfaceContract(
                contract_id=item["contract_id"],
                kind=EngineeringContractKind(item["kind"]),
                name=item["name"],
                producer=item["producer"],
                consumer=item["consumer"],
                inputs=tuple(item["inputs"]),
                outputs=tuple(item["outputs"]),
                failure_behavior=item["failure_behavior"],
            )
            for item in interface_contracts
        ),
        acceptance_checks=tuple(value["acceptance_checks"]),
        validation_checks=tuple(value["validation_checks"]),
        handoff_notes=tuple(value["handoff_notes"]),
        status_report=EngineeringStatusReport(
            state=status["state"],
            completed_items=tuple(status["completed_items"]),
            next_actions=tuple(status["next_actions"]),
            blockers=tuple(status["blockers"]),
            escalations=tuple(status["escalations"]),
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
