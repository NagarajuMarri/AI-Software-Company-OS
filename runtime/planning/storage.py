"""Project-isolated atomic planning persistence."""

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from runtime.planning.errors import *
from runtime.planning.models import *
from runtime.planning.validation import IDENTIFIER


class PlanningStore:
    SCHEMA_VERSION = 1

    def __init__(self, state_root):
        self.root = Path(state_root) / "planning"

    def save_request(self, request):
        self._write(self._path(request.project_id, "requests", request.request_id),
                    {"schema_version": 1, "kind": "request", "request": _encode(asdict(request))})

    def load_request(self, project_id, request_id):
        return _request(self._read(self._path(project_id, "requests", request_id), "request")["request"])

    def list_requests(self, project_id):
        return tuple(self.load_request(project_id, path.stem)
                     for path in self._files(project_id, "requests"))

    def save_proposal(self, proposal):
        self._write(self._path(proposal.project_id, "proposals", proposal.proposal_id),
                    {"schema_version": 1, "kind": "proposal", "proposal": _encode(asdict(proposal))})

    def load_proposal(self, project_id, proposal_id):
        return _proposal(self._read(self._path(project_id, "proposals", proposal_id), "proposal")["proposal"])

    def list_proposals(self, project_id):
        return tuple(self.load_proposal(project_id, path.stem)
                     for path in self._files(project_id, "proposals"))

    def save_context_reference(self, context):
        payload = {"schema_version": 1, "kind": "context-reference",
                   "project_id": context.project_id,
                   "request_id": context.request.request_id,
                   "knowledge_scanned_at": context.knowledge_scanned_at.isoformat(),
                   "file_paths": [x.path for x in context.relevant_files],
                   "symbol_names": [x.qualified_name for x in context.relevant_symbols]}
        self._write(self._path(context.project_id, "contexts", context.request.request_id), payload)

    def _path(self, project_id, kind, identifier):
        for value in (project_id, identifier):
            if not IDENTIFIER.fullmatch(value):
                raise PlanningValidationError(f"Unsafe planning identifier {value!r}")
        return self.root / project_id / kind / f"{identifier}.json"

    def _files(self, project_id, kind):
        directory = self.root / project_id / kind
        return sorted(directory.glob("*.json"), key=lambda x: x.name) if directory.exists() else ()

    def _read(self, path, kind):
        if not path.exists():
            raise PlanningNotFoundError(f"Planning {kind} {path.stem!r} does not exist")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") != self.SCHEMA_VERSION:
                raise UnsupportedPlanningSchemaError(
                    f"Unsupported planning schema {data.get('schema_version')!r}")
            if data.get("kind") != kind:
                raise ValueError("unexpected planning record kind")
            return data
        except UnsupportedPlanningSchemaError:
            raise
        except Exception as error:
            raise PlanningStateCorruptError(f"Planning state {path} cannot be safely loaded") from error

    def _write(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, sort_keys=True, indent=2)
                stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception as error:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
            raise PlanningStorageError(f"Could not persist planning state {path}") from error


def _encode(value):
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Enum): return value.value
    if isinstance(value, dict): return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_encode(v) for v in value]
    return value


def _request(x):
    return ManagedProductChangeRequest(**{**x,
        "requested_capabilities": tuple(x["requested_capabilities"]),
        "acceptance_criteria": tuple(x["acceptance_criteria"]),
        "constraints": tuple(x["constraints"]), "out_of_scope": tuple(x["out_of_scope"]),
        "priority": ChangePriority(x["priority"]), "created_at": datetime.fromisoformat(x["created_at"])})


def _proposal(x):
    tasks = tuple(ProposedTask(**{**task, "dependencies": tuple(task["dependencies"]),
        "role_requirements": tuple(task["role_requirements"]),
        "capability_requirements": tuple(task["capability_requirements"]),
        "acceptance_criteria": tuple(task["acceptance_criteria"]),
        "candidate_files": tuple(task["candidate_files"]),
        "quality_gates": tuple(task["quality_gates"]),
        "risk_level": RiskLevel(task["risk_level"])}) for task in x["tasks"])
    decisions = tuple(ProposalDecision(ProposalStatus(value["status"]), value["actor"],
        datetime.fromisoformat(value["timestamp"]), value["reason"]) for value in x["decisions"])
    return ProposedProductMilestone(**{**x, "tasks": tasks,
        "scope": tuple(x["scope"]), "out_of_scope": tuple(x["out_of_scope"]),
        "architecture_considerations": tuple(x["architecture_considerations"]),
        "acceptance_criteria": tuple(x["acceptance_criteria"]),
        "candidate_impacted_files": tuple(x["candidate_impacted_files"]),
        "quality_gates": tuple(x["quality_gates"]), "risks": tuple(x["risks"]),
        "assumptions": tuple(x["assumptions"]),
        "required_human_approvals": tuple(x["required_human_approvals"]),
        "provider_metadata": tuple(tuple(v) for v in x["provider_metadata"]),
        "generated_at": datetime.fromisoformat(x["generated_at"]),
        "status": ProposalStatus(x["status"]), "decisions": decisions,
        "materialised_at": datetime.fromisoformat(x["materialised_at"]) if x["materialised_at"] else None})
