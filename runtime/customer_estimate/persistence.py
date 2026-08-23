"""Write-once canonical persistence for customer delivery-estimate drafts."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_estimate.errors import (
    CustomerDeliveryEstimateConflict,
    CustomerDeliveryEstimateCorrupt,
    CustomerDeliveryEstimateNotFound,
)
from runtime.customer_estimate.models import (
    CustomerDeliveryEstimateDraft,
    CustomerMilestoneEstimate,
    EffortBand,
    EstimateConfidence,
    estimate_id_for,
)
from runtime.customer_prd import ids_for
from runtime.customer_roadmap import roadmap_approval_id_for, roadmap_id_for


_SCHEMA_VERSION = 1


class FileCustomerDeliveryEstimateStore:
    """Persist one immutable estimate draft per customer product request."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, value: CustomerDeliveryEstimateDraft) -> CustomerDeliveryEstimateDraft:
        path = self._path(value.customer_id, value.request_id)
        try:
            _exclusive_write(path, _encode(value))
        except FileExistsError:
            existing = self.load(value.customer_id, value.request_id)
            if existing == value:
                return existing
            raise CustomerDeliveryEstimateConflict(
                "A different customer delivery-estimate draft already exists"
            ) from None
        return value

    def find(self, customer_id: str, request_id: str) -> CustomerDeliveryEstimateDraft | None:
        path = self._path(customer_id, request_id)
        if path.is_symlink():
            raise CustomerDeliveryEstimateCorrupt("Customer estimate file is unsafe")
        if not path.exists():
            return None
        return self.load(customer_id, request_id)

    def load(self, customer_id: str, request_id: str) -> CustomerDeliveryEstimateDraft:
        path = self._path(customer_id, request_id)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CustomerDeliveryEstimateCorrupt("Customer estimate file is unsafe")
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise CustomerDeliveryEstimateNotFound(
                "Customer delivery-estimate draft does not exist"
            ) from None
        try:
            envelope = json.loads(content)
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"schema_version", "digest", "record"}
                or envelope["schema_version"] != _SCHEMA_VERSION
                or not isinstance(envelope["record"], dict)
            ):
                raise ValueError("Invalid customer estimate envelope")
            value = _from_record(envelope["record"])
            _, product_id, prd_id = ids_for(request_id)
            if (
                value.customer_id != customer_id
                or value.request_id != request_id
                or value.estimate_id != estimate_id_for(request_id)
                or value.roadmap_id != roadmap_id_for(request_id)
                or value.roadmap_approval_id != roadmap_approval_id_for(request_id)
                or value.product_id != product_id
                or value.prd_id != prd_id
                or value.digest != envelope["digest"]
                or _encode(value) != content
            ):
                raise ValueError("Customer estimate authority mismatch")
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise CustomerDeliveryEstimateCorrupt(
                "Customer delivery-estimate authority is corrupt"
            ) from error

    def _path(self, customer_id: str, request_id: str) -> Path:
        estimate_id_for(customer_id)
        estimate_id_for(request_id)
        directory = self._root / customer_id / request_id
        for candidate in (directory.parent, directory):
            if candidate.exists() and candidate.is_symlink():
                raise CustomerDeliveryEstimateCorrupt("Customer estimate path is unsafe")
        resolved_parent = directory.parent.resolve()
        if self._root not in (resolved_parent, *resolved_parent.parents):
            raise CustomerDeliveryEstimateCorrupt("Customer estimate path escaped its store")
        if directory.exists():
            if not directory.is_dir():
                raise CustomerDeliveryEstimateCorrupt("Customer estimate directory is unsafe")
            if any(entry.name != "estimate-v0.1.json" for entry in directory.iterdir()):
                raise CustomerDeliveryEstimateCorrupt("Customer estimate directory is not closed")
        return directory / "estimate-v0.1.json"


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def _record(value: CustomerDeliveryEstimateDraft) -> dict[str, object]:
    return {
        "estimate_id": value.estimate_id,
        "customer_id": value.customer_id,
        "request_id": value.request_id,
        "roadmap_id": value.roadmap_id,
        "roadmap_approval_id": value.roadmap_approval_id,
        "product_id": value.product_id,
        "prd_id": value.prd_id,
        "prd_version": value.prd_version,
        "source_request_digest": value.source_request_digest,
        "requirements_digest": value.requirements_digest,
        "requirements_approval_digest": value.requirements_approval_digest,
        "prd_digest": value.prd_digest,
        "prd_approval_digest": value.prd_approval_digest,
        "roadmap_digest": value.roadmap_digest,
        "roadmap_approval_digest": value.roadmap_approval_digest,
        "generation_profile": value.generation_profile,
        "title": value.title,
        "milestones": [
            {
                "roadmap_item_id": item.roadmap_item_id,
                "milestone": item.milestone,
                "sequence": item.sequence,
                "requirement_ids": list(item.requirement_ids),
                "complexity_points": item.complexity_points,
                "minimum_effort_days": item.minimum_effort_days,
                "maximum_effort_days": item.maximum_effort_days,
                "effort_band": item.effort_band.value,
                "confidence": item.confidence.value,
                "drivers": list(item.drivers),
                "status": item.status,
            }
            for item in value.milestones
        ],
        "total_minimum_effort_days": value.total_minimum_effort_days,
        "total_maximum_effort_days": value.total_maximum_effort_days,
        "effort_unit": value.effort_unit,
        "confidence": value.confidence.value,
        "assumptions": list(value.assumptions),
        "generated_at": value.generated_at.isoformat(),
        "status": value.status,
    }


def _encode(value: CustomerDeliveryEstimateDraft) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "digest": value.digest,
        "record": _record(value),
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _from_record(value: dict[str, Any]) -> CustomerDeliveryEstimateDraft:
    expected = {
        "estimate_id", "customer_id", "request_id", "roadmap_id",
        "roadmap_approval_id", "product_id", "prd_id", "prd_version",
        "source_request_digest", "requirements_digest", "requirements_approval_digest",
        "prd_digest", "prd_approval_digest", "roadmap_digest", "roadmap_approval_digest",
        "generation_profile", "title", "milestones", "total_minimum_effort_days",
        "total_maximum_effort_days", "effort_unit", "confidence", "assumptions",
        "generated_at", "status",
    }
    if set(value) != expected:
        raise ValueError("Customer estimate fields are invalid")
    return CustomerDeliveryEstimateDraft(
        value["estimate_id"], value["customer_id"], value["request_id"],
        value["roadmap_id"], value["roadmap_approval_id"], value["product_id"],
        value["prd_id"], value["prd_version"], value["source_request_digest"],
        value["requirements_digest"], value["requirements_approval_digest"],
        value["prd_digest"], value["prd_approval_digest"], value["roadmap_digest"],
        value["roadmap_approval_digest"], value["generation_profile"], value["title"],
        tuple(_milestone(item) for item in value["milestones"]),
        value["total_minimum_effort_days"], value["total_maximum_effort_days"],
        value["effort_unit"], EstimateConfidence(value["confidence"]),
        tuple(value["assumptions"]), datetime.fromisoformat(value["generated_at"]),
        value["status"],
    )


def _milestone(value: dict[str, Any]) -> CustomerMilestoneEstimate:
    if set(value) != {
        "roadmap_item_id", "milestone", "sequence", "requirement_ids",
        "complexity_points", "minimum_effort_days", "maximum_effort_days",
        "effort_band", "confidence", "drivers", "status",
    }:
        raise ValueError("Customer milestone estimate fields are invalid")
    return CustomerMilestoneEstimate(
        value["roadmap_item_id"], value["milestone"], value["sequence"],
        tuple(value["requirement_ids"]), value["complexity_points"],
        value["minimum_effort_days"], value["maximum_effort_days"],
        EffortBand(value["effort_band"]), EstimateConfidence(value["confidence"]),
        tuple(value["drivers"]), value["status"],
    )
