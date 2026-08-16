"""Atomic, history-preserving storage for runtime acceptance runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from runtime.runtime_acceptance.models import (
    AcceptanceJourney,
    AcceptanceStage,
    CapabilityAcceptanceContract,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    HumanAcceptance,
    JourneyResult,
    RuntimeAcceptanceRun,
)


class RuntimeAcceptanceStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(self, run: RuntimeAcceptanceRun) -> Path:
        directory = self.root / self._safe(run.product_id) / self._safe(run.run_id)
        target = directory / "current.json"
        if target.exists():
            existing = self.load(run.product_id, run.run_id)
            if existing is not None:
                immutable_contract = (
                    existing.run_id,
                    existing.product_id,
                    existing.version,
                    existing.commit_sha,
                    existing.capabilities,
                    existing.journeys,
                    existing.created_at,
                )
                candidate_contract = (
                    run.run_id,
                    run.product_id,
                    run.version,
                    run.commit_sha,
                    run.capabilities,
                    run.journeys,
                    run.created_at,
                )
                if immutable_contract != candidate_contract:
                    raise ValueError(
                        "Runtime acceptance identity and locked contract are immutable"
                    )
                if existing.stage is AcceptanceStage.COMPLETED and existing != run:
                    raise ValueError("Completed runtime acceptance evidence is immutable")
                if run.updated_at < existing.updated_at:
                    raise ValueError("Runtime acceptance timestamps cannot move backwards")
                if run.stage is not existing.stage:
                    from runtime.runtime_acceptance.lifecycle import TRANSITIONS

                    if run.stage not in TRANSITIONS[existing.stage]:
                        raise ValueError("Runtime acceptance lifecycle cannot be skipped")
                if run.evidence[: len(existing.evidence)] != existing.evidence:
                    raise ValueError("Runtime evidence history is immutable")
                if (
                    run.journey_results[: len(existing.journey_results)]
                    != existing.journey_results
                ):
                    raise ValueError("Journey result history is immutable")
                if run.human_acceptances[: len(existing.human_acceptances)] != existing.human_acceptances:
                    raise ValueError("Human acceptance history is immutable")
                if existing == run:
                    return target
        elif run.stage is not AcceptanceStage.PLANNED:
            raise ValueError("New runtime acceptance persistence starts PLANNED")
        snapshot = directory / "snapshots" / (
            f"{len(run.evidence):04d}-{len(run.journey_results):04d}-"
            f"{len(run.human_acceptances):04d}-{run.stage.value.lower()}.json"
        )
        self._write(snapshot, run)
        self._write(target, run)
        return target

    def load(self, product_id: str, run_id: str) -> RuntimeAcceptanceRun | None:
        target = self.root / self._safe(product_id) / self._safe(run_id) / "current.json"
        return self.load_snapshot(target) if target.exists() else None

    def find(self, run_id: str) -> RuntimeAcceptanceRun | None:
        self._safe(run_id)
        matches = list(self.root.glob(f"*/{run_id}/current.json"))
        if len(matches) > 1:
            raise ValueError("Runtime acceptance run ID is ambiguous")
        return self.load_snapshot(matches[0]) if matches else None

    def list_for_product(self, product_id: str) -> tuple[RuntimeAcceptanceRun, ...]:
        root = self.root / self._safe(product_id)
        return tuple(self.load_snapshot(path) for path in sorted(root.glob("*/current.json")))

    @staticmethod
    def load_snapshot(path: Path) -> RuntimeAcceptanceRun:
        return _run(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _safe(value: str) -> str:
        if not value or Path(value).name != value or value in {".", ".."}:
            raise ValueError("Unsafe runtime acceptance identity")
        return value

    @staticmethod
    def _write(target: Path, run: RuntimeAcceptanceRun) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(run), default=_json, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)


def _json(value: object) -> str:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _run(data: dict) -> RuntimeAcceptanceRun:
    data["stage"] = AcceptanceStage(data["stage"])
    data["created_at"] = _dt(data["created_at"])
    data["updated_at"] = _dt(data["updated_at"])
    data["completed_at"] = _dt(data.get("completed_at"))
    data["capabilities"] = tuple(
        CapabilityAcceptanceContract(
            **{
                **item,
                "required_journey_ids": tuple(item["required_journey_ids"]),
                "requirement_ids": tuple(item.get("requirement_ids", ())),
            }
        )
        for item in data.get("capabilities", ())
    )
    data["journeys"] = tuple(
        AcceptanceJourney(
            **{
                **item,
                "required_evidence": tuple(
                    EvidenceKind(value) for value in item["required_evidence"]
                ),
            }
        )
        for item in data.get("journeys", ())
    )
    data["evidence"] = tuple(
        EvidenceArtifact(
            **{
                **item,
                "kind": EvidenceKind(item["kind"]),
                "outcome": EvidenceOutcome(item["outcome"]),
                "observed_at": _dt(item["observed_at"]),
                "metadata": tuple(tuple(pair) for pair in item.get("metadata", ())),
            }
        )
        for item in data.get("evidence", ())
    )
    data["journey_results"] = tuple(
        JourneyResult(
            **{
                **item,
                "outcome": EvidenceOutcome(item["outcome"]),
                "evidence_ids": tuple(item["evidence_ids"]),
                "completed_at": _dt(item["completed_at"]),
            }
        )
        for item in data.get("journey_results", ())
    )
    data["human_acceptances"] = tuple(
        HumanAcceptance(
            **{
                **item,
                "accepted_at": _dt(item["accepted_at"]),
                "evidence_ids": tuple(item.get("evidence_ids", ())),
            }
        )
        for item in data.get("human_acceptances", ())
    )
    data["blockers"] = tuple(data.get("blockers", ()))
    return RuntimeAcceptanceRun(**data)
