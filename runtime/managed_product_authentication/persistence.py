"""Write-once persistence for authentication verification authority."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from runtime.managed_product_authentication.errors import AuthenticationPlanError
from runtime.managed_product_authentication.models import (
    AuthenticationClaim,
    AuthenticationJourneyVerification,
    AuthenticationVerificationPlan,
)
from runtime.runtime_acceptance.models import EvidenceKind


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class InMemoryAuthenticationVerificationPlanStore:
    def __init__(self) -> None:
        self._plans: dict[tuple[str, str, str], AuthenticationVerificationPlan] = {}

    def save(self, plan: AuthenticationVerificationPlan) -> AuthenticationVerificationPlan:
        key = (plan.product_id, plan.run_id, plan.verification_id)
        existing = self._plans.get(key)
        if existing is not None and existing != plan:
            raise AuthenticationPlanError("Authentication verification plan is immutable")
        self._plans[key] = plan
        return plan

    def load(
        self, product_id: str, run_id: str, verification_id: str
    ) -> AuthenticationVerificationPlan:
        try:
            return self._plans[(product_id, run_id, verification_id)]
        except KeyError as error:
            raise AuthenticationPlanError("Unknown authentication verification plan") from error


class FileAuthenticationVerificationPlanStore:
    SCHEMA_VERSION = 1

    def __init__(self, root_directory: str | Path) -> None:
        self.root = Path(root_directory).absolute()
        if self.root.exists() and self.root.is_symlink():
            raise AuthenticationPlanError("Authentication plan root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)

    def save(self, plan: AuthenticationVerificationPlan) -> AuthenticationVerificationPlan:
        path = self._path(plan.product_id, plan.run_id, plan.verification_id)
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "digest": plan.digest,
            "plan": _payload(plan),
        }
        encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        if path.exists():
            if path.is_symlink():
                raise AuthenticationPlanError("Authentication plan path is unsafe")
            existing = self.load(plan.product_id, plan.run_id, plan.verification_id)
            if existing != plan:
                raise AuthenticationPlanError("Authentication verification plan is immutable")
            return existing
        _atomic_create(path, encoded)
        persisted = self.load(plan.product_id, plan.run_id, plan.verification_id)
        if persisted != plan:
            raise AuthenticationPlanError("Authentication verification plan is immutable")
        return persisted

    def load(
        self, product_id: str, run_id: str, verification_id: str
    ) -> AuthenticationVerificationPlan:
        path = self._path(product_id, run_id, verification_id)
        if path.is_symlink():
            raise AuthenticationPlanError("Authentication plan path is unsafe")
        try:
            envelope = json.loads(path.read_bytes())
            if set(envelope) != {"schema_version", "digest", "plan"}:
                raise ValueError("unexpected envelope fields")
            if envelope["schema_version"] != self.SCHEMA_VERSION:
                raise ValueError("unsupported schema")
            plan = _from_payload(envelope["plan"])
            if (
                plan.product_id != product_id
                or plan.run_id != run_id
                or plan.verification_id != verification_id
                or plan.digest != envelope["digest"]
                or _payload(plan) != envelope["plan"]
            ):
                raise ValueError("identity or digest mismatch")
            return plan
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationPlanError(
                "Authentication verification plan is missing or corrupt"
            ) from error

    def _path(self, product_id: str, run_id: str, verification_id: str) -> Path:
        for value in (product_id, run_id, verification_id):
            if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
                raise AuthenticationPlanError("Authentication plan identity is unsafe")
        product = self.root / product_id
        directory = product / run_id
        try:
            if product.exists() and product.is_symlink():
                raise AuthenticationPlanError("Authentication plan path contains a symlink")
            product.mkdir(exist_ok=True)
            product.chmod(0o700)
            if directory.exists() and directory.is_symlink():
                raise AuthenticationPlanError("Authentication plan path contains a symlink")
            directory.mkdir(exist_ok=True)
            directory.chmod(0o700)
        except OSError as error:
            raise AuthenticationPlanError("Authentication plan directory is unavailable") from error
        resolved = directory.resolve()
        if self.root.resolve() not in resolved.parents:
            raise AuthenticationPlanError("Authentication plan path escaped its root")
        return resolved / f"{verification_id}.json"


def _atomic_create(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise AuthenticationPlanError("Authentication plan could not be persisted") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _payload(plan: AuthenticationVerificationPlan) -> dict[str, object]:
    return {
        "verification_id": plan.verification_id,
        "run_id": plan.run_id,
        "product_id": plan.product_id,
        "browser_plan_id": plan.browser_plan_id,
        "browser_plan_digest": plan.browser_plan_digest,
        "configuration_id": plan.configuration_id,
        "configuration_revision": plan.configuration_revision,
        "configuration_digest": plan.configuration_digest,
        "commit_sha": plan.commit_sha,
        "acceptance_profile_id": plan.acceptance_profile_id,
        "acceptance_profile_version": plan.acceptance_profile_version,
        "acceptance_profile_digest": plan.acceptance_profile_digest,
        "provider_id": plan.provider_id,
        "journeys": [
            {
                "journey_id": item.journey_id,
                "required_step_ids": list(item.required_step_ids),
                "claims": [value.value for value in item.claims],
                "evidence_kinds": [value.value for value in item.evidence_kinds],
            }
            for item in plan.journeys
        ],
        "created_by": plan.created_by,
        "created_at": plan.created_at.isoformat(),
    }


def _from_payload(payload: dict[str, Any]) -> AuthenticationVerificationPlan:
    journeys = tuple(
        AuthenticationJourneyVerification(
            item["journey_id"],
            tuple(item["required_step_ids"]),
            tuple(AuthenticationClaim(value) for value in item["claims"]),
            tuple(EvidenceKind(value) for value in item["evidence_kinds"]),
        )
        for item in payload["journeys"]
    )
    return AuthenticationVerificationPlan(
        payload["verification_id"],
        payload["run_id"],
        payload["product_id"],
        payload["browser_plan_id"],
        payload["browser_plan_digest"],
        payload["configuration_id"],
        payload["configuration_revision"],
        payload["configuration_digest"],
        payload["commit_sha"],
        payload["acceptance_profile_id"],
        payload["acceptance_profile_version"],
        payload["acceptance_profile_digest"],
        payload["provider_id"],
        journeys,
        payload["created_by"],
        datetime.fromisoformat(payload["created_at"]),
    )
