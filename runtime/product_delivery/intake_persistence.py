"""Atomic JSON persistence for existing-product delivery intake."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from runtime.product_delivery.intake_models import (
    BranchReconciliation,
    ExistingProductIntakeStage,
    HumanReviewedProductDelivery,
    ImplementationSource,
    VerificationOutcome,
    VerificationResult,
)
from runtime.product_delivery.models import ProviderExecutionMode


class ExistingProductDeliveryStore(Protocol):
    def save(self, delivery: HumanReviewedProductDelivery) -> None: ...

    def load(self, project_id: str) -> HumanReviewedProductDelivery | None: ...


class InMemoryExistingProductDeliveryStore:
    def __init__(self) -> None:
        self._values: dict[str, dict[str, object]] = {}

    def save(self, delivery: HumanReviewedProductDelivery) -> None:
        self._values[delivery.project_id] = _serialize(delivery)

    def load(self, project_id: str) -> HumanReviewedProductDelivery | None:
        value = self._values.get(project_id)
        return _deserialize(value) if value is not None else None


class JsonExistingProductDeliveryStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def save(self, delivery: HumanReviewedProductDelivery) -> None:
        target = self._target(delivery.project_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(_serialize(delivery), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(target)

    def load(self, project_id: str) -> HumanReviewedProductDelivery | None:
        target = self._target(project_id)
        if not target.exists():
            return None
        value = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Product delivery state must be a JSON object")
        return _deserialize(cast(dict[str, object], value))

    def _target(self, project_id: str) -> Path:
        if not project_id or project_id in {".", ".."} or Path(project_id).name != project_id:
            raise ValueError("Project ID must be a filesystem-safe identifier")
        return self.directory / f"{project_id}.json"


def _serialize(delivery: HumanReviewedProductDelivery) -> dict[str, object]:
    value = asdict(delivery)
    value["execution_mode"] = delivery.execution_mode.value
    value["implementation_source"] = delivery.implementation_source.value
    value["stage"] = delivery.stage.value
    value["created_at"] = (
        delivery.created_at.isoformat() if delivery.created_at is not None else None
    )
    value["verification_results"] = [
        {
            "gate": result.gate,
            "outcome": result.outcome.value,
            "details": result.details,
            "recorded_at": result.recorded_at.isoformat(),
        }
        for result in delivery.verification_results
    ]
    return value


def _deserialize(value: dict[str, object]) -> HumanReviewedProductDelivery:
    data = dict(value)
    data["execution_mode"] = ProviderExecutionMode(str(data["execution_mode"]))
    data["implementation_source"] = ImplementationSource(
        str(data["implementation_source"])
    )
    data["stage"] = ExistingProductIntakeStage(str(data["stage"]))
    created_at = data.get("created_at")
    data["created_at"] = (
        datetime.fromisoformat(str(created_at)) if created_at is not None else None
    )
    reconciliation = cast(dict[str, Any], data["reconciliation"])
    reconciliation["changed_paths"] = tuple(reconciliation["changed_paths"])
    data["reconciliation"] = BranchReconciliation(**reconciliation)
    results = cast(list[dict[str, Any]], data.get("verification_results", []))
    data["verification_results"] = tuple(
        VerificationResult(
            gate=str(item["gate"]),
            outcome=VerificationOutcome(str(item["outcome"])),
            details=str(item["details"]),
            recorded_at=datetime.fromisoformat(str(item["recorded_at"])),
        )
        for item in results
    )
    for field_name in ("verification_requirements", "known_limitations"):
        data[field_name] = tuple(cast(list[str], data.get(field_name, [])))
    return HumanReviewedProductDelivery(**data)  # type: ignore[arg-type]
