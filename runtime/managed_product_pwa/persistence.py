"""Write-once persistence for PWA and aggregate-submission authority."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from runtime.managed_product_pwa.errors import AcceptanceSubmissionError, PwaPlanError
from runtime.managed_product_pwa.models import (
    AcceptanceSubmissionPlan,
    AcceptanceSubmissionReceipt,
    CapabilityExecutionReference,
    PwaClaim,
    PwaVerificationPlan,
)


_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class InMemoryPwaVerificationPlanStore:
    def __init__(self) -> None:
        self._plans: dict[tuple[str, str, str], PwaVerificationPlan] = {}

    def save(self, plan: PwaVerificationPlan) -> PwaVerificationPlan:
        key = (plan.product_id, plan.run_id, plan.plan_id)
        existing = self._plans.get(key)
        if existing is not None and existing != plan:
            raise PwaPlanError("PWA verification plan is immutable")
        self._plans[key] = plan
        return plan

    def load(self, product_id: str, run_id: str, plan_id: str) -> PwaVerificationPlan:
        try:
            return self._plans[(product_id, run_id, plan_id)]
        except KeyError as error:
            raise PwaPlanError("Unknown PWA verification plan") from error


class FilePwaVerificationPlanStore:
    SCHEMA_VERSION = 1

    def __init__(self, root_directory: str | Path) -> None:
        self.root = _root(root_directory, PwaPlanError, "PWA plan")

    def save(self, plan: PwaVerificationPlan) -> PwaVerificationPlan:
        path = _path(self.root, plan.product_id, plan.run_id, plan.plan_id, "pwa", PwaPlanError)
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "digest": plan.digest,
            "plan": _pwa_payload(plan),
        }
        _create_or_compare(path, envelope, PwaPlanError, "PWA verification plan")
        return self.load(plan.product_id, plan.run_id, plan.plan_id)

    def load(self, product_id: str, run_id: str, plan_id: str) -> PwaVerificationPlan:
        path = _path(self.root, product_id, run_id, plan_id, "pwa", PwaPlanError)
        try:
            envelope = _read_envelope(path, self.SCHEMA_VERSION)
            if set(envelope) != {"schema_version", "digest", "plan"}:
                raise ValueError("unexpected PWA plan fields")
            plan = _pwa_from_payload(envelope["plan"])
            if (
                plan.product_id != product_id
                or plan.run_id != run_id
                or plan.plan_id != plan_id
                or plan.digest != envelope["digest"]
                or _pwa_payload(plan) != envelope["plan"]
            ):
                raise ValueError("identity or digest mismatch")
            return plan
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise PwaPlanError("PWA verification plan is missing or corrupt") from error


class InMemoryAcceptanceSubmissionStore:
    def __init__(self) -> None:
        self._plans: dict[tuple[str, str, str], AcceptanceSubmissionPlan] = {}
        self._receipts: dict[tuple[str, str, str], AcceptanceSubmissionReceipt] = {}

    def save_plan(self, plan: AcceptanceSubmissionPlan) -> AcceptanceSubmissionPlan:
        key = (plan.product_id, plan.run_id, plan.submission_id)
        existing = self._plans.get(key)
        if existing is not None and existing != plan:
            raise AcceptanceSubmissionError("Acceptance submission plan is immutable")
        self._plans[key] = plan
        return plan

    def load_plan(
        self, product_id: str, run_id: str, submission_id: str
    ) -> AcceptanceSubmissionPlan:
        try:
            return self._plans[(product_id, run_id, submission_id)]
        except KeyError as error:
            raise AcceptanceSubmissionError("Unknown acceptance submission plan") from error

    def save_receipt(
        self, receipt: AcceptanceSubmissionReceipt
    ) -> AcceptanceSubmissionReceipt:
        key = (receipt.product_id, receipt.run_id, receipt.submission_id)
        existing = self._receipts.get(key)
        if existing is not None and existing != receipt:
            raise AcceptanceSubmissionError("Acceptance submission receipt is immutable")
        self._receipts[key] = receipt
        return receipt

    def find_receipt(
        self, product_id: str, run_id: str, submission_id: str
    ) -> AcceptanceSubmissionReceipt | None:
        return self._receipts.get((product_id, run_id, submission_id))


class FileAcceptanceSubmissionStore:
    SCHEMA_VERSION = 1

    def __init__(self, root_directory: str | Path) -> None:
        self.root = _root(root_directory, AcceptanceSubmissionError, "submission")

    def save_plan(self, plan: AcceptanceSubmissionPlan) -> AcceptanceSubmissionPlan:
        path = self._plan_path(plan.product_id, plan.run_id, plan.submission_id)
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "digest": plan.digest,
            "plan": _submission_payload(plan),
        }
        _create_or_compare(
            path, envelope, AcceptanceSubmissionError, "Acceptance submission plan"
        )
        return self.load_plan(plan.product_id, plan.run_id, plan.submission_id)

    def load_plan(
        self, product_id: str, run_id: str, submission_id: str
    ) -> AcceptanceSubmissionPlan:
        path = self._plan_path(product_id, run_id, submission_id)
        try:
            envelope = _read_envelope(path, self.SCHEMA_VERSION)
            if set(envelope) != {"schema_version", "digest", "plan"}:
                raise ValueError("unexpected submission plan fields")
            plan = _submission_from_payload(envelope["plan"])
            if (
                plan.product_id != product_id
                or plan.run_id != run_id
                or plan.submission_id != submission_id
                or plan.digest != envelope["digest"]
                or _submission_payload(plan) != envelope["plan"]
            ):
                raise ValueError("identity or digest mismatch")
            return plan
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AcceptanceSubmissionError(
                "Acceptance submission plan is missing or corrupt"
            ) from error

    def save_receipt(
        self, receipt: AcceptanceSubmissionReceipt
    ) -> AcceptanceSubmissionReceipt:
        path = self._receipt_path(
            receipt.product_id, receipt.run_id, receipt.submission_id
        )
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "receipt": _receipt_payload(receipt),
        }
        _create_or_compare(
            path, envelope, AcceptanceSubmissionError, "Acceptance submission receipt"
        )
        restored = self.find_receipt(
            receipt.product_id, receipt.run_id, receipt.submission_id
        )
        if restored != receipt:
            raise AcceptanceSubmissionError("Acceptance submission receipt is immutable")
        return receipt

    def find_receipt(
        self, product_id: str, run_id: str, submission_id: str
    ) -> AcceptanceSubmissionReceipt | None:
        path = self._receipt_path(product_id, run_id, submission_id)
        if not path.exists():
            return None
        try:
            envelope = _read_envelope(path, self.SCHEMA_VERSION)
            if set(envelope) != {"schema_version", "receipt"}:
                raise ValueError("unexpected receipt fields")
            receipt = _receipt_from_payload(envelope["receipt"])
            if (
                receipt.product_id != product_id
                or receipt.run_id != run_id
                or receipt.submission_id != submission_id
                or _receipt_payload(receipt) != envelope["receipt"]
            ):
                raise ValueError("receipt identity mismatch")
            return receipt
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AcceptanceSubmissionError(
                "Acceptance submission receipt is corrupt"
            ) from error

    def _plan_path(self, product_id: str, run_id: str, submission_id: str) -> Path:
        return _path(
            self.root,
            product_id,
            run_id,
            submission_id,
            "submission",
            AcceptanceSubmissionError,
        )

    def _receipt_path(self, product_id: str, run_id: str, submission_id: str) -> Path:
        plan_path = self._plan_path(product_id, run_id, submission_id)
        return plan_path.with_name(f"{submission_id}.receipt.json")


def _root(root_directory: str | Path, error_type, label: str) -> Path:  # noqa: ANN001
    root = Path(root_directory).absolute()
    if root.exists() and root.is_symlink():
        raise error_type(f"{label} root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def _path(
    root: Path,
    product_id: str,
    run_id: str,
    item_id: str,
    suffix: str,
    error_type,
) -> Path:
    for identity in (product_id, run_id, item_id):
        if not isinstance(identity, str) or not _SAFE.fullmatch(identity):
            raise error_type("Persistence identity is unsafe")
    product = root / product_id
    directory = product / run_id
    try:
        for directory_path in (product, directory):
            if directory_path.exists() and directory_path.is_symlink():
                raise error_type("Persistence path contains a symlink")
            directory_path.mkdir(exist_ok=True)
            directory_path.chmod(0o700)
    except OSError as error:
        raise error_type("Persistence directory is unavailable") from error
    resolved = directory.resolve()
    if root.resolve() not in resolved.parents:
        raise error_type("Persistence path escaped its root")
    return resolved / f"{item_id}.{suffix}.json"


def _create_or_compare(path: Path, payload: dict[str, object], error_type, label: str) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if path.exists():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise error_type(f"{label} is immutable")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != encoded:
                raise error_type(f"{label} is immutable")
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise error_type(f"{label} could not be persisted") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _read_envelope(path: Path, schema_version: int) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("unsafe symlink")
    value = json.loads(path.read_bytes())
    if value.get("schema_version") != schema_version:
        raise ValueError("unsupported schema")
    return value


def _pwa_payload(plan: PwaVerificationPlan) -> dict[str, object]:
    return {
        "plan_id": plan.plan_id,
        "run_id": plan.run_id,
        "product_id": plan.product_id,
        "configuration_id": plan.configuration_id,
        "configuration_revision": plan.configuration_revision,
        "configuration_digest": plan.configuration_digest,
        "commit_sha": plan.commit_sha,
        "acceptance_profile_id": plan.acceptance_profile_id,
        "acceptance_profile_version": plan.acceptance_profile_version,
        "acceptance_profile_digest": plan.acceptance_profile_digest,
        "provider_id": plan.provider_id,
        "start_path": plan.start_path,
        "manifest_path": plan.manifest_path,
        "service_worker_path": plan.service_worker_path,
        "shell_test_id": plan.shell_test_id,
        "shell_expected_text": plan.shell_expected_text,
        "claims": [value.value for value in plan.claims],
        "created_by": plan.created_by,
        "created_at": plan.created_at.isoformat(),
    }


def _pwa_from_payload(value: dict[str, Any]) -> PwaVerificationPlan:
    return PwaVerificationPlan(
        value["plan_id"],
        value["run_id"],
        value["product_id"],
        value["configuration_id"],
        value["configuration_revision"],
        value["configuration_digest"],
        value["commit_sha"],
        value["acceptance_profile_id"],
        value["acceptance_profile_version"],
        value["acceptance_profile_digest"],
        value["provider_id"],
        value["start_path"],
        value["manifest_path"],
        value["service_worker_path"],
        value["shell_test_id"],
        value["shell_expected_text"],
        tuple(PwaClaim(item) for item in value["claims"]),
        value["created_by"],
        datetime.fromisoformat(value["created_at"]),
    )


def _submission_payload(plan: AcceptanceSubmissionPlan) -> dict[str, object]:
    return {
        "submission_id": plan.submission_id,
        "run_id": plan.run_id,
        "product_id": plan.product_id,
        "configuration_id": plan.configuration_id,
        "configuration_revision": plan.configuration_revision,
        "configuration_digest": plan.configuration_digest,
        "commit_sha": plan.commit_sha,
        "acceptance_profile_id": plan.acceptance_profile_id,
        "acceptance_profile_version": plan.acceptance_profile_version,
        "acceptance_profile_digest": plan.acceptance_profile_digest,
        "sources": [
            {
                "capability_id": item.capability_id,
                "plan_id": item.plan_id,
                "plan_digest": item.plan_digest,
                "result_digest": item.result_digest,
                "journey_ids": list(item.journey_ids),
            }
            for item in plan.sources
        ],
        "created_by": plan.created_by,
        "created_at": plan.created_at.isoformat(),
    }


def _submission_from_payload(value: dict[str, Any]) -> AcceptanceSubmissionPlan:
    return AcceptanceSubmissionPlan(
        value["submission_id"],
        value["run_id"],
        value["product_id"],
        value["configuration_id"],
        value["configuration_revision"],
        value["configuration_digest"],
        value["commit_sha"],
        value["acceptance_profile_id"],
        value["acceptance_profile_version"],
        value["acceptance_profile_digest"],
        tuple(
            CapabilityExecutionReference(
                item["capability_id"],
                item["plan_id"],
                item["plan_digest"],
                item["result_digest"],
                tuple(item["journey_ids"]),
            )
            for item in value["sources"]
        ),
        value["created_by"],
        datetime.fromisoformat(value["created_at"]),
    )


def _receipt_payload(value: AcceptanceSubmissionReceipt) -> dict[str, object]:
    return {
        "submission_id": value.submission_id,
        "submission_digest": value.submission_digest,
        "run_id": value.run_id,
        "product_id": value.product_id,
        "runtime_evidence_digest": value.runtime_evidence_digest,
        "source_result_digests": list(value.source_result_digests),
        "submitted_at": value.submitted_at.isoformat(),
    }


def _receipt_from_payload(value: dict[str, Any]) -> AcceptanceSubmissionReceipt:
    return AcceptanceSubmissionReceipt(
        value["submission_id"],
        value["submission_digest"],
        value["run_id"],
        value["product_id"],
        value["runtime_evidence_digest"],
        tuple(value["source_result_digests"]),
        datetime.fromisoformat(value["submitted_at"]),
    )
