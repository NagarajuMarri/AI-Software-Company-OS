"""Provider-neutral, history-preserving Release Management persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from runtime.release_management.models import *  # noqa: F403


class ReleaseStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(self, release: Release) -> Path:
        target = self.root / self._safe(release.release_id) / "snapshots" / f"{release.status.value.lower()}.json"
        if target.exists():
            existing = self.load_snapshot(target)
            if existing == release: return target
            if existing.status in {ReleaseStatus.RELEASED, ReleaseStatus.ROLLED_BACK,
                                   ReleaseStatus.SUPERSEDED, ReleaseStatus.ARCHIVED}:
                raise ValueError("Released history is immutable")
            if release.approvals[:len(existing.approvals)] != existing.approvals:
                raise ValueError("Approval history is immutable")
        self._write(target, release)
        self._write(self.root / self._safe(release.release_id) / "current.json", release)
        return target

    def load(self, release_id: str) -> Release | None:
        target = self.root / self._safe(release_id) / "current.json"
        return self.load_snapshot(target) if target.exists() else None

    def list_releases(self) -> tuple[Release, ...]:
        return tuple(self.load_snapshot(path) for path in sorted(self.root.glob("*/current.json")))

    @staticmethod
    def load_snapshot(path: Path) -> Release:
        return _release(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _safe(value: str) -> str:
        if not value or Path(value).name != value or value in {".", ".."}: raise ValueError("Unsafe release ID")
        return value

    @staticmethod
    def _write(target: Path, value: Any) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(value), default=_json, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        temporary.replace(target)


def _json(value: object) -> str:
    if isinstance(value, Enum): return value.value
    if isinstance(value, datetime): return value.isoformat()
    raise TypeError(type(value).__name__)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _release(data: dict) -> Release:
    data["version"] = Version.parse(data["version"] if isinstance(data["version"], str) else _version_text(data["version"]))
    data["kind"] = ReleaseKind(data["kind"]); data["status"] = ReleaseStatus(data["status"])
    for name in ("product_ids","requirement_ids","milestone_ids","commit_shas","pull_request_urls","decision_ids",
                 "locked_capability_ids","runtime_acceptance_run_ids"):
        data[name] = tuple(data.get(name, ()))
    for name in ("created_at","updated_at","released_at"): data[name] = _dt(data.get(name))
    data["candidates"] = tuple(ReleaseCandidate(**{**x,"version":Version.parse(_version_text(x["version"])),"created_at":_dt(x["created_at"])}) for x in data.get("candidates",()))
    data["approvals"] = tuple(ReleaseApproval(**{**x,"timestamp":_dt(x["timestamp"])}) for x in data.get("approvals",()))
    if data.get("notes"):
        x=data["notes"]; data["notes"]=ReleaseNotes(**{**x,**{n:tuple(x[n]) for n in ("requirements","milestones","commits","pull_requests","decisions")}})
    if data.get("changelog"): data["changelog"] = Changelog(tuple(data["changelog"]["entries"]))
    data["artifacts"] = tuple(ReleaseArtifact(**x) for x in data.get("artifacts",()))
    data["rollbacks"] = tuple(RollbackRecord(**{**x,"timestamp":_dt(x["timestamp"])}) for x in data.get("rollbacks",()))
    data["decisions"] = tuple(ReleaseDecision(**{**x,"requirement_ids":tuple(x["requirement_ids"]),"timestamp":_dt(x["timestamp"])}) for x in data.get("decisions",()))
    data["deployments"] = tuple(DeploymentRecord(**{**x,"artifact_ids":tuple(x["artifact_ids"]),"timestamp":_dt(x["timestamp"])}) for x in data.get("deployments",()))
    return Release(**data)


def _version_text(value: dict) -> str:
    stable=f'{value["major"]}.{value["minor"]}.{value["patch"]}'
    candidate=value.get("release_candidate")
    return stable if candidate is None else f"{stable}-rc.{candidate}"
