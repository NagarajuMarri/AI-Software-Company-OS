"""Version-preserving atomic JSON persistence for PRM objects."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from runtime.product_requirements.models import *  # noqa: F403


class ProductRequirementsStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save_prd(self, prd: ProductRequirementsDocument) -> Path:
        target = self._safe(prd.product_id) / "prds" / self._safe_name(prd.prd_id) / f"v{self._safe_name(prd.version)}.json"
        if target.exists():
            existing = self.load_prd(prd.product_id, prd.prd_id, prd.version)
            if existing == prd: return target
            if existing and existing.status is RequirementStatus.LOCKED and prd.status is not RequirementStatus.SUPERSEDED:
                raise ValueError("Locked PRD versions are immutable")
        self._write(target, prd)
        return target

    def load_prd(self, product_id: str, prd_id: str, version: str) -> ProductRequirementsDocument | None:
        target = self._safe(product_id) / "prds" / self._safe_name(prd_id) / f"v{self._safe_name(version)}.json"
        if not target.exists(): return None
        return _prd(json.loads(target.read_text(encoding="utf-8")))

    def list_prds(self, product_id: str, prd_id: str) -> tuple[ProductRequirementsDocument, ...]:
        folder = self._safe(product_id) / "prds" / self._safe_name(prd_id)
        if not folder.exists(): return ()
        values = [self.load_prd(product_id, prd_id, path.stem[1:]) for path in sorted(folder.glob("v*.json"))]
        return tuple(value for value in values if value is not None)

    def list_product_prds(self, product_id: str) -> tuple[ProductRequirementsDocument, ...]:
        folder = self._safe(product_id) / "prds"
        if not folder.exists(): return ()
        return tuple(_prd(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(folder.glob("*/v*.json")))

    def save_trace(self, product_id: str, trace: ImplementationTrace) -> None:
        self._write(self._safe(product_id) / "traces" / f"{self._safe_name(trace.trace_id)}.json", trace)

    def list_traces(self, product_id: str) -> tuple[ImplementationTrace, ...]:
        folder = self._safe(product_id) / "traces"
        return tuple(_trace(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(folder.glob("*.json"))) if folder.exists() else ()

    def save_change_request(self, request: RequirementChangeRequest) -> None:
        self._write(self._safe(request.product_id) / "change_requests" / f"{self._safe_name(request.change_request_id)}.json", request)

    def list_change_requests(self, product_id: str) -> tuple[RequirementChangeRequest, ...]:
        folder = self._safe(product_id) / "change_requests"
        return tuple(_change_request(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(folder.glob("*.json"))) if folder.exists() else ()

    def load_trace(self, product_id: str, trace_id: str) -> ImplementationTrace | None:
        target = self._safe(product_id) / "traces" / f"{self._safe_name(trace_id)}.json"
        return _trace(json.loads(target.read_text(encoding="utf-8"))) if target.exists() else None

    def save_decision(self, product_id: str, entry: DecisionLogEntry) -> None:
        self._write(self._safe(product_id) / "decisions" / f"{self._safe_name(entry.decision_id)}.json", entry)

    def list_decisions(self, product_id: str) -> tuple[DecisionLogEntry, ...]:
        folder = self._safe(product_id) / "decisions"
        return tuple(_decision(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(folder.glob("*.json"))) if folder.exists() else ()

    def _safe(self, value: str) -> Path:
        return self.root / self._safe_name(value)

    @staticmethod
    def _safe_name(value: str) -> str:
        if not value or Path(value).name != value or value in {".", ".."}: raise ValueError("Identifier must be filesystem safe")
        return value

    @staticmethod
    def _write(target: Path, value: Any) -> None:
        target.parent.mkdir(parents=True, exist_ok=True); temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(value), default=_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(target)


def _json(value: object) -> str:
    if isinstance(value, Enum): return value.value
    if isinstance(value, datetime): return value.isoformat()
    raise TypeError(type(value).__name__)


def _requirement(data: dict) -> ProductRequirement:
    for name in ("acceptance_criteria", "affected_products", "tags", "conflicts_with"): data[name] = tuple(data.get(name, ()))
    data["priority"] = RequirementPriority(data["priority"]); data["status"] = RequirementStatus(data["status"]); data["category"] = RequirementCategory(data["category"])
    for name in ("created_at", "updated_at"): data[name] = datetime.fromisoformat(data[name])
    if data.get("locked_at"): data["locked_at"] = datetime.fromisoformat(data["locked_at"])
    return ProductRequirement(**data)


def _prd(data: dict) -> ProductRequirementsDocument:
    schema_version = data.pop("schema_version", 1)
    if schema_version != 1: raise ValueError("Unsupported PRD schema version")
    data["status"] = RequirementStatus(data["status"]); data["requirements"] = tuple(_requirement(x) for x in data["requirements"])
    data["explicit_exclusions"] = tuple(data["explicit_exclusions"]); data["future_roadmap"] = tuple(data["future_roadmap"])
    data["revision_history"] = tuple(RevisionRecord(x["version"], x["actor"], x["action"], x["reason"], datetime.fromisoformat(x["timestamp"])) for x in data["revision_history"])
    data["requirement_groups"] = tuple(
        RequirementGroup(**{**x, "requirement_ids": tuple(x["requirement_ids"])})
        for x in data.get("requirement_groups", ())
    )
    data["approval_history"] = tuple(
        RequirementApproval(**{**x, "requirement_ids": tuple(x["requirement_ids"]),
                               "timestamp": datetime.fromisoformat(x["timestamp"])})
        for x in data.get("approval_history", ())
    )
    for name in ("created_at", "updated_at", "locked_at"): data[name] = datetime.fromisoformat(data[name]) if data.get(name) else None
    return ProductRequirementsDocument(**data)


def load_prd_artifact(path: str | Path) -> ProductRequirementsDocument:
    """Load a tracked PRD artifact without mutating managed state."""
    return _prd(json.loads(Path(path).read_text(encoding="utf-8")))


def _trace(data: dict) -> ImplementationTrace:
    data["recorded_at"] = datetime.fromisoformat(data["recorded_at"]); return ImplementationTrace(**data)


def _decision(data: dict) -> DecisionLogEntry:
    data["decision_type"] = DecisionType(data["decision_type"]); data["affected_requirements"] = tuple(data["affected_requirements"]); data["timestamp"] = datetime.fromisoformat(data["timestamp"]); return DecisionLogEntry(**data)


def _change_request(data: dict) -> RequirementChangeRequest:
    data["requirement_ids"] = tuple(data["requirement_ids"])
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return RequirementChangeRequest(**data)
