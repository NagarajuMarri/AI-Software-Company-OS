"""Project-isolated atomic persistence for managed execution."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from runtime.managed_execution.errors import (
    ExecutionNotFoundError,
    ExecutionStateCorruptError,
    ExecutionStorageError,
    ExecutionValidationError,
    UnsupportedExecutionSchemaError,
)
from runtime.managed_execution.models import (
    AcceptedCodingResult,
    ExecutionDecision,
    ExecutionMode,
    ExecutionOperationPhase,
    ExecutionPlanStatus,
    ExternalEffectKind,
    ExternalEffectRecord,
    ExternalEffectState,
    GateStatus,
    ManagedExecutionOperation,
    ManagedProductExecutionPlan,
    ManagedProductExecutionRequest,
    QualityGateResult,
    ReviewDecisionStatus,
    ReviewEvidence,
    RuntimeTaskMapping,
    TaskExecution,
    ValidatedCodingResult,
    WorkspaceLifecycle,
    WorkspaceRecord,
)
from runtime.planning.validation import IDENTIFIER


class ManagedExecutionStore:
    SCHEMA_VERSION = 1

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "execution"

    def save_request(self, value: ManagedProductExecutionRequest) -> None:
        self._save(value.project_id, "requests", value.execution_request_id, value)

    def load_request(self, project_id: str, identifier: str) -> ManagedProductExecutionRequest:
        value = self._load(project_id, "requests", identifier)
        return ManagedProductExecutionRequest(
            **{
                **value,
                "selected_task_ids": tuple(value["selected_task_ids"]),
                "requested_at": _dt(value["requested_at"]),
                "execution_mode": ExecutionMode(value["execution_mode"]),
                "cost_limit_metadata": tuple(
                    tuple(item) for item in value["cost_limit_metadata"]
                ),
                "execution_notes": tuple(value["execution_notes"]),
            }
        )

    def list_requests(self, project_id: str) -> tuple[ManagedProductExecutionRequest, ...]:
        return tuple(self.load_request(project_id, path.stem)
                     for path in self._files(project_id, "requests"))

    def save_plan(self, value: ManagedProductExecutionPlan) -> None:
        self._save(value.project_id, "plans", value.execution_plan_id, value)

    def load_plan(self, project_id: str, identifier: str) -> ManagedProductExecutionPlan:
        value = self._load(project_id, "plans", identifier)
        tasks = tuple(TaskExecution(
            **{
                **task,
                "dependencies": tuple(task["dependencies"]),
                "role_requirements": tuple(task["role_requirements"]),
                "capability_requirements": tuple(task["capability_requirements"]),
                "acceptance_criteria": tuple(task["acceptance_criteria"]),
                "candidate_files": tuple(task["candidate_files"]),
                "allowed_paths": tuple(task["allowed_paths"]),
                "forbidden_paths": tuple(task["forbidden_paths"]),
                "allowed_commands": tuple(tuple(command) for command in task["allowed_commands"]),
                "quality_gates": tuple(task["quality_gates"]),
                "expected_artifacts": tuple(task["expected_artifacts"]),
            }
        ) for task in value["ordered_task_executions"])
        decisions = tuple(ExecutionDecision(
            **{
                **decision,
                "status": ReviewDecisionStatus(decision["status"]),
                "decided_at": _dt(decision["decided_at"]),
            }
        ) for decision in value["decisions"])
        return ManagedProductExecutionPlan(
            **{
                **value,
                "ordered_task_executions": tasks,
                "dependency_graph": tuple(
                    (item[0], tuple(item[1])) for item in value["dependency_graph"]
                ),
                "expected_runtime_work_item_ids": tuple(
                    value["expected_runtime_work_item_ids"]
                ),
                "role_requirements": tuple(value["role_requirements"]),
                "capability_requirements": tuple(value["capability_requirements"]),
                "quality_gates": tuple(value["quality_gates"]),
                "limits": tuple(tuple(item) for item in value["limits"]),
                "required_approvals": tuple(value["required_approvals"]),
                "generated_at": _dt(value["generated_at"]),
                "status": ExecutionPlanStatus(value["status"]),
                "planning_evidence_references": tuple(
                    value["planning_evidence_references"]
                ),
                "decisions": decisions,
            }
        )

    def list_plans(self, project_id: str) -> tuple[ManagedProductExecutionPlan, ...]:
        return tuple(self.load_plan(project_id, path.stem)
                     for path in self._files(project_id, "plans"))

    def save_operation(self, value: ManagedExecutionOperation) -> None:
        self._save(value.project_id, "operations", value.operation_id, value)

    def load_operation(self, project_id: str, identifier: str) -> ManagedExecutionOperation:
        value = self._load(project_id, "operations", identifier)
        return ManagedExecutionOperation(
            **{
                **value,
                "task_ids": tuple(value["task_ids"]),
                "runtime_ids": tuple(value["runtime_ids"]),
                "phase": ExecutionOperationPhase(value["phase"]),
                "external_coding_task_ids": tuple(value["external_coding_task_ids"]),
                "provider_operation_ids": tuple(value["provider_operation_ids"]),
                "gate_execution_ids": tuple(value["gate_execution_ids"]),
                "evidence_ids": tuple(value["evidence_ids"]),
                "approval_ids": tuple(value["approval_ids"]),
                "created_at": _dt(value["created_at"]),
                "updated_at": _dt(value["updated_at"]),
            }
        )

    def save_mapping(self, project_id: str, value: RuntimeTaskMapping) -> None:
        self._save(project_id, "task-mappings", value.project_task_id, value)

    def load_mapping(self, project_id: str, identifier: str) -> RuntimeTaskMapping:
        return RuntimeTaskMapping(**self._load(
            project_id, "task-mappings", identifier))

    def list_mappings(self, project_id: str) -> tuple[RuntimeTaskMapping, ...]:
        return tuple(self.load_mapping(project_id, path.stem)
                     for path in self._files(project_id, "task-mappings"))

    def save_workspace(self, value: WorkspaceRecord) -> None:
        self._save(value.project_id, "workspaces", value.workspace_id, value)

    def load_workspace(self, project_id: str, identifier: str) -> WorkspaceRecord:
        value = self._load(project_id, "workspaces", identifier)
        return WorkspaceRecord(**{
            **value,
            "lifecycle": WorkspaceLifecycle(value["lifecycle"]),
            "created_at": _dt(value["created_at"]),
            "updated_at": _dt(value["updated_at"]),
        })

    def save_gate_results(
        self, project_id: str, identifier: str, values: tuple[QualityGateResult, ...]
    ) -> None:
        self._save(project_id, "quality-gates", identifier, values)

    def load_gate_results(
        self, project_id: str, identifier: str
    ) -> tuple[QualityGateResult, ...]:
        return tuple(QualityGateResult(**{
            **item,
            "status": GateStatus(item["status"]),
            "started_at": _dt(item["started_at"]),
            "completed_at": _dt(item["completed_at"]),
        }) for item in self._load(project_id, "quality-gates", identifier))

    def save_evidence(self, value: ReviewEvidence) -> None:
        self._save(value.project_id, "evidence", value.evidence_id, value)

    def load_evidence(self, project_id: str, identifier: str) -> ReviewEvidence:
        value = self._load(project_id, "evidence", identifier)
        gates = tuple(QualityGateResult(**{
            **item,
            "status": GateStatus(item["status"]),
            "started_at": _dt(item["started_at"]),
            "completed_at": _dt(item["completed_at"]),
        }) for item in value["quality_gate_results"])
        return ReviewEvidence(**{
            **value,
            "task_ids": tuple(value["task_ids"]),
            "changed_files": tuple(value["changed_files"]),
            "accepted_coding_result_ids": tuple(
                value["accepted_coding_result_ids"]),
            "gate_execution_ids": tuple(value["gate_execution_ids"]),
            "quality_gate_results": gates,
            "acceptance_criteria_mapping": tuple(
                (item[0], tuple(item[1])) for item in value["acceptance_criteria_mapping"]
            ),
            "unresolved_risks": tuple(value["unresolved_risks"]),
            "warnings": tuple(value["warnings"]),
            "policy_exceptions": tuple(value["policy_exceptions"]),
            "reviewer_required_flags": tuple(value["reviewer_required_flags"]),
            "generated_at": _dt(value["generated_at"]),
        })

    def save_coding_result(self, value: AcceptedCodingResult) -> None:
        self._save(
            value.project_id, "coding-results", value.accepted_result_id, value)

    def load_coding_result(
        self, project_id: str, identifier: str
    ) -> AcceptedCodingResult:
        value = self._load(project_id, "coding-results", identifier)
        result = value["result"]
        return AcceptedCodingResult(**{
            **value,
            "result": ValidatedCodingResult(**{
                **result,
                "changed_files": tuple(result["changed_files"]),
                "executed_gates": tuple(result["executed_gates"]),
                "artifacts": tuple(result["artifacts"]),
                "progress_sequences": tuple(result["progress_sequences"]),
            }),
            "accepted_at": _dt(value["accepted_at"]),
        })

    def list_coding_results(
        self, project_id: str
    ) -> tuple[AcceptedCodingResult, ...]:
        return tuple(self.load_coding_result(project_id, path.stem)
                     for path in self._files(project_id, "coding-results"))

    def save_effect(self, value: ExternalEffectRecord) -> None:
        self._save(value.project_id, "repository-effects", value.effect_id, value)

    def load_effect(
        self, project_id: str, identifier: str
    ) -> ExternalEffectRecord:
        value = self._load(project_id, "repository-effects", identifier)
        return ExternalEffectRecord(**{
            **value,
            "kind": ExternalEffectKind(value["kind"]),
            "state": ExternalEffectState(value["state"]),
            "expected_identity": tuple(
                tuple(item) for item in value["expected_identity"]),
            "result_identity": tuple(
                tuple(item) for item in value["result_identity"]),
            "created_at": _dt(value["created_at"]),
            "updated_at": _dt(value["updated_at"]),
        })

    def list_effects(
        self, project_id: str
    ) -> tuple[ExternalEffectRecord, ...]:
        return tuple(self.load_effect(project_id, path.stem)
                     for path in self._files(project_id, "repository-effects"))

    def _save(self, project_id: str, kind: str, identifier: str, value) -> None:
        path = self._path(project_id, kind, identifier)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "kind": kind,
            "value": _encode(asdict(value) if hasattr(value, "__dataclass_fields__") else value),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception as error:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise ExecutionStorageError(f"Could not persist execution {kind}") from error

    def _load(self, project_id: str, kind: str, identifier: str):
        path = self._path(project_id, kind, identifier)
        if not path.exists():
            raise ExecutionNotFoundError(f"Execution {kind} {identifier!r} not found")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != self.SCHEMA_VERSION:
                raise UnsupportedExecutionSchemaError("Unsupported execution schema")
            if payload.get("kind") != kind:
                raise ValueError("Unexpected execution record kind")
            return payload["value"]
        except UnsupportedExecutionSchemaError:
            raise
        except Exception as error:
            raise ExecutionStateCorruptError(
                f"Execution state {path} cannot be safely loaded") from error

    def _path(self, project_id: str, kind: str, identifier: str) -> Path:
        if not IDENTIFIER.fullmatch(project_id) or not IDENTIFIER.fullmatch(identifier):
            raise ExecutionValidationError("Unsafe execution identifier")
        return self.root / project_id / kind / f"{identifier}.json"

    def _files(self, project_id: str, kind: str):
        if not IDENTIFIER.fullmatch(project_id):
            raise ExecutionValidationError("Unsafe project identifier")
        directory = self.root / project_id / kind
        return sorted(directory.glob("*.json"), key=lambda path: path.name) \
            if directory.exists() else ()


def _encode(value):
    if is_dataclass(value):
        return _encode(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    return value


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)
