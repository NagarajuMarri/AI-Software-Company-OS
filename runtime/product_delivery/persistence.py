"""Persistence ports and JSON-file storage for product delivery state."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from runtime.product_delivery.models import (
    HumanReviewStage,
    ProductDeliveryState,
    ProviderExecutionMode,
    ReviewDecision,
    ReviewDecisionType,
)


class ProductStateStore(Protocol):
    def save(self, state: ProductDeliveryState) -> None: ...

    def load(self, project: str) -> ProductDeliveryState | None: ...


class InMemoryProductStateStore:
    def __init__(self) -> None:
        self._values: dict[str, dict[str, object]] = {}

    def save(self, state: ProductDeliveryState) -> None:
        self._values[state.project] = _serialize(state)

    def load(self, project: str) -> ProductDeliveryState | None:
        value = self._values.get(project)
        return _deserialize(value) if value is not None else None


class JsonProductStateStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def save(self, state: ProductDeliveryState) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._target(state.project)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(_serialize(state), indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(target)

    def load(self, project: str) -> ProductDeliveryState | None:
        target = self._target(project)
        if not target.exists():
            return None
        value = json.loads(target.read_text(encoding="utf-8"))
        return _deserialize(value)

    def _target(self, project: str) -> Path:
        if not project or project in {".", ".."} or Path(project).name != project:
            raise ValueError("Project must be a non-empty filesystem-safe identifier")
        return self.directory / f"{project}.json"


def _serialize(state: ProductDeliveryState) -> dict[str, object]:
    value = asdict(state)
    value["execution_mode"] = state.execution_mode.value
    value["review_state"] = state.review_state.value
    value["review_history"] = [
        {
            "reviewer": item.reviewer,
            "decision": item.decision.value,
            "decided_at": item.decided_at.isoformat(),
            "comments": item.comments,
            "reviewed_commit": item.reviewed_commit,
        }
        for item in state.review_history
    ]
    return value


def _deserialize(value: dict[str, object]) -> ProductDeliveryState:
    data = dict(value)
    data["execution_mode"] = ProviderExecutionMode(str(data["execution_mode"]))
    data["review_state"] = HumanReviewStage(str(data["review_state"]))
    history = cast(list[dict[str, Any]], data.get("review_history", []))
    data["review_history"] = tuple(
        ReviewDecision(
            reviewer=str(item["reviewer"]),
            decision=ReviewDecisionType(str(item["decision"])),
            decided_at=datetime.fromisoformat(str(item["decided_at"])),
            comments=str(item["comments"]),
            reviewed_commit=str(item.get("reviewed_commit", data.get("latest_commit", ""))),
        )
        for item in history
    )
    data["pending_actions"] = list(
        cast(list[str], data.get("pending_actions", []))
    )
    return ProductDeliveryState(**data)  # type: ignore[arg-type]
