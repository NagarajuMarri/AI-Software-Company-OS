"""Immutable browser-plan and content-addressed evidence persistence."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlsplit

from runtime.managed_product_browser.errors import BrowserArtifactError, BrowserPlanError
from runtime.managed_product_browser.models import (
    BrowserActionKind,
    BrowserInputBinding,
    BrowserJourneyPlan,
    BrowserJourneySpecification,
    BrowserLocator,
    BrowserLocatorKind,
    BrowserStep,
    BrowserExecutionResult,
    BrowserExecutionStage,
)
from runtime.runtime_acceptance.models import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    JourneyResult,
)


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ARTIFACT_FILENAME = re.compile(r"^[0-9a-f]{64}\.(json|png)$")


class InMemoryBrowserJourneyPlanStore:
    def __init__(self) -> None:
        self._plans: dict[tuple[str, str, str], BrowserJourneyPlan] = {}

    def save(self, plan: BrowserJourneyPlan) -> BrowserJourneyPlan:
        key = (plan.product_id, plan.run_id, plan.plan_id)
        existing = self._plans.get(key)
        if existing is not None and existing != plan:
            raise BrowserPlanError("Browser journey plan is immutable")
        self._plans[key] = plan
        return plan

    def load(self, product_id: str, run_id: str, plan_id: str) -> BrowserJourneyPlan:
        try:
            return self._plans[(product_id, run_id, plan_id)]
        except KeyError as error:
            raise BrowserPlanError("Unknown browser journey plan") from error


class FileBrowserJourneyPlanStore:
    """Write-once canonical plans that fail closed on corruption."""

    SCHEMA_VERSION = 1

    def __init__(self, root_directory: str | Path) -> None:
        self.root = Path(root_directory).absolute()
        _prepare_root(self.root)

    def save(self, plan: BrowserJourneyPlan) -> BrowserJourneyPlan:
        path = self._path(plan.product_id, plan.run_id, plan.plan_id)
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "digest": plan.digest,
            "plan": _plan_payload(plan),
        }
        encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        if path.exists():
            if path.is_symlink():
                raise BrowserPlanError("Browser journey plan path is unsafe")
            existing = self.load(plan.product_id, plan.run_id, plan.plan_id)
            if existing != plan:
                raise BrowserPlanError("Browser journey plan is immutable")
            return existing
        _atomic_create(path, encoded, BrowserPlanError)
        return plan

    def load(self, product_id: str, run_id: str, plan_id: str) -> BrowserJourneyPlan:
        path = self._path(product_id, run_id, plan_id)
        if path.is_symlink():
            raise BrowserPlanError("Browser journey plan path is unsafe")
        try:
            raw = path.read_bytes()
            envelope = json.loads(raw)
            if set(envelope) != {"schema_version", "digest", "plan"}:
                raise ValueError("unexpected envelope fields")
            if envelope["schema_version"] != self.SCHEMA_VERSION:
                raise ValueError("unsupported schema")
            plan = _plan_from_payload(envelope["plan"])
            if (
                plan.product_id != product_id
                or plan.run_id != run_id
                or plan.plan_id != plan_id
                or plan.digest != envelope["digest"]
                or _plan_payload(plan) != envelope["plan"]
            ):
                raise ValueError("identity or digest mismatch")
            return plan
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise BrowserPlanError("Browser journey plan is missing or corrupt") from error

    def _path(self, product_id: str, run_id: str, plan_id: str) -> Path:
        directory = _safe_directory(self.root, product_id, run_id, BrowserPlanError)
        if not _SAFE_IDENTIFIER.fullmatch(plan_id):
            raise BrowserPlanError("Browser plan identity is unsafe")
        return directory / f"{plan_id}.json"


class InMemoryBrowserExecutionStore:
    def __init__(self) -> None:
        self._results: dict[tuple[str, str, str], BrowserExecutionResult] = {}

    def save(self, result: BrowserExecutionResult) -> BrowserExecutionResult:
        key = (result.product_id, result.run_id, result.plan_id)
        existing = self._results.get(key)
        if existing is not None and existing != result:
            raise BrowserArtifactError("Browser execution result is immutable")
        self._results[key] = result
        return result

    def load(self, product_id: str, run_id: str, plan_id: str) -> BrowserExecutionResult:
        try:
            return self._results[(product_id, run_id, plan_id)]
        except KeyError as error:
            raise BrowserArtifactError("Unknown browser execution result") from error

    def find(
        self, product_id: str, run_id: str, plan_id: str
    ) -> BrowserExecutionResult | None:
        return self._results.get((product_id, run_id, plan_id))


class FileBrowserExecutionStore:
    """Write-once terminal browser results bound to content-addressed artifacts."""

    SCHEMA_VERSION = 1

    def __init__(self, root_directory: str | Path) -> None:
        self.root = Path(root_directory).absolute()
        _prepare_root(self.root)

    def save(self, result: BrowserExecutionResult) -> BrowserExecutionResult:
        path = self._path(result.product_id, result.run_id, result.plan_id)
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "digest": result.digest,
            "result": _result_payload(result),
        }
        encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        if path.exists():
            if path.is_symlink():
                raise BrowserArtifactError("Browser execution result path is unsafe")
            existing = self.load(result.product_id, result.run_id, result.plan_id)
            if existing != result:
                raise BrowserArtifactError("Browser execution result is immutable")
            return existing
        _atomic_create(path, encoded, BrowserArtifactError)
        return result

    def load(self, product_id: str, run_id: str, plan_id: str) -> BrowserExecutionResult:
        path = self._path(product_id, run_id, plan_id)
        if path.is_symlink():
            raise BrowserArtifactError("Browser execution result path is unsafe")
        try:
            envelope = json.loads(path.read_bytes())
            if set(envelope) != {"schema_version", "digest", "result"}:
                raise ValueError("unexpected envelope fields")
            if envelope["schema_version"] != self.SCHEMA_VERSION:
                raise ValueError("unsupported schema")
            result = _result_from_payload(envelope["result"])
            if (
                result.product_id != product_id
                or result.run_id != run_id
                or result.plan_id != plan_id
                or result.digest != envelope["digest"]
                or _result_payload(result) != envelope["result"]
            ):
                raise ValueError("identity or digest mismatch")
            return result
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise BrowserArtifactError("Browser execution result is missing or corrupt") from error

    def find(
        self, product_id: str, run_id: str, plan_id: str
    ) -> BrowserExecutionResult | None:
        path = self._path(product_id, run_id, plan_id)
        if not path.exists():
            return None
        return self.load(product_id, run_id, plan_id)

    def _path(self, product_id: str, run_id: str, plan_id: str) -> Path:
        directory = _safe_directory(self.root, product_id, run_id, BrowserArtifactError)
        if not _SAFE_IDENTIFIER.fullmatch(plan_id):
            raise BrowserArtifactError("Browser result identity is unsafe")
        return directory / f"{plan_id}.json"


class ContentAddressedBrowserArtifactStore:
    """Persist bounded evidence bytes without interpreting or rewriting them."""

    def __init__(self, root_directory: str | Path, *, maximum_bytes: int = 10_000_000) -> None:
        if maximum_bytes < 1 or maximum_bytes > 100_000_000:
            raise ValueError("Browser artifact size limit is outside policy")
        self.root = Path(root_directory).absolute()
        self.maximum_bytes = maximum_bytes
        _prepare_root(self.root)

    def write_json(self, product_id: str, run_id: str, payload: object) -> tuple[str, str]:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return self.write_bytes(product_id, run_id, encoded, "json")

    def write_bytes(
        self,
        product_id: str,
        run_id: str,
        content: bytes,
        extension: str,
    ) -> tuple[str, str]:
        if not isinstance(content, bytes) or not content or len(content) > self.maximum_bytes:
            raise BrowserArtifactError("Browser artifact is empty or outside size policy")
        if extension not in {"json", "png"}:
            raise BrowserArtifactError("Browser artifact extension is unsupported")
        if extension == "png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise BrowserArtifactError("Browser screenshot is not a PNG artifact")
        if extension == "json":
            try:
                json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise BrowserArtifactError("Browser JSON artifact is invalid") from error
        directory = self._directory(product_id, run_id)
        digest = hashlib.sha256(content).hexdigest()
        path = directory / f"{digest}.{extension}"
        if path.exists():
            if path.is_symlink():
                raise BrowserArtifactError("Browser artifact path is unsafe")
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise BrowserArtifactError("Existing browser artifact failed integrity validation")
            except OSError as error:
                raise BrowserArtifactError("Existing browser artifact is unreadable") from error
        else:
            _atomic_create(path, content, BrowserArtifactError)
        return f"artifact://browser/{product_id}/{run_id}/{digest}.{extension}", digest

    def resolve(self, artifact_uri: str) -> Path:
        parsed = urlsplit(artifact_uri)
        parts = tuple(part for part in parsed.path.split("/") if part)
        if (
            parsed.scheme != "artifact"
            or parsed.netloc != "browser"
            or parsed.query
            or parsed.fragment
            or len(parts) != 3
        ):
            raise BrowserArtifactError("Browser artifact URI is invalid")
        product_id, run_id, filename = parts
        if not _ARTIFACT_FILENAME.fullmatch(filename):
            raise BrowserArtifactError("Browser artifact URI is invalid")
        path = self._directory(product_id, run_id) / filename
        resolved = path.resolve()
        if self.root.resolve() not in resolved.parents or not resolved.is_file():
            raise BrowserArtifactError("Browser artifact is unavailable")
        expected = filename.split(".", 1)[0]
        try:
            actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as error:
            raise BrowserArtifactError("Browser artifact is unreadable") from error
        if actual != expected:
            raise BrowserArtifactError("Browser artifact failed integrity validation")
        return resolved

    def verify(self, artifact_uri: str, expected_digest: str) -> None:
        if (
            not isinstance(expected_digest, str)
            or len(expected_digest) != 64
            or any(character not in "0123456789abcdef" for character in expected_digest)
        ):
            raise BrowserArtifactError("Browser artifact digest is invalid")
        path = self.resolve(artifact_uri)
        if path.name.split(".", 1)[0] != expected_digest:
            raise BrowserArtifactError("Browser artifact digest does not match its URI")

    def read_json(self, artifact_uri: str, expected_digest: str) -> object:
        """Return one verified JSON artifact without weakening content addressing."""

        self.verify(artifact_uri, expected_digest)
        path = self.resolve(artifact_uri)
        if path.suffix != ".json":
            raise BrowserArtifactError("Browser artifact is not JSON")
        try:
            return json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BrowserArtifactError("Browser JSON artifact is unreadable") from error

    def _directory(self, product_id: str, run_id: str) -> Path:
        return _safe_directory(self.root, product_id, run_id, BrowserArtifactError)


def _prepare_root(root: Path) -> None:
    if root.exists() and root.is_symlink():
        raise ValueError("Browser persistence root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)


def _safe_directory(
    root: Path,
    product_id: str,
    run_id: str,
    error_type: type[ValueError],
) -> Path:
    for value in (product_id, run_id):
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise error_type("Browser persistence identity is unsafe")
    product_directory = root / product_id
    directory = product_directory / run_id
    try:
        if product_directory.exists() and product_directory.is_symlink():
            raise error_type("Browser persistence path contains a symlink")
        product_directory.mkdir(exist_ok=True)
        product_directory.chmod(0o700)
        if directory.exists() and directory.is_symlink():
            raise error_type("Browser persistence path contains a symlink")
        directory.mkdir(exist_ok=True)
        directory.chmod(0o700)
    except OSError as error:
        raise error_type("Browser persistence directory is unavailable") from error
    resolved = directory.resolve()
    if root.resolve() not in resolved.parents:
        raise error_type("Browser persistence path escaped its root")
    return resolved


def _atomic_create(path: Path, content: bytes, error_type: type[ValueError]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink():
                raise error_type("Browser persistence target is unsafe")
            if path.read_bytes() != content:
                raise error_type("Immutable browser persistence target already exists")
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (OSError, ValueError) as error:
        if isinstance(error, error_type):
            raise
        raise error_type("Browser persistence write failed") from error
    finally:
        temporary.unlink(missing_ok=True)


def _plan_payload(plan: BrowserJourneyPlan) -> dict[str, object]:
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
        "journeys": [
            {
                "journey_id": journey.journey_id,
                "capability_id": journey.capability_id,
                "title": journey.title,
                "start_path": journey.start_path,
                "timeout_seconds": journey.timeout_seconds,
                "steps": [
                    {
                        "step_id": step.step_id,
                        "action": step.action.value,
                        "locator": None
                        if step.locator is None
                        else {
                            "kind": step.locator.kind.value,
                            "value": step.locator.value,
                            "accessible_name": step.locator.accessible_name,
                            "exact": step.locator.exact,
                        },
                        "input_id": step.input_id,
                        "expected_text": step.expected_text,
                        "expected_path": step.expected_path,
                    }
                    for step in journey.steps
                ],
            }
            for journey in plan.journeys
        ],
        "inputs": [
            {
                "input_id": item.input_id,
                "public_value": item.public_value,
                "secret_reference": item.secret_reference,
            }
            for item in plan.inputs
        ],
        "created_by": plan.created_by,
        "created_at": plan.created_at.isoformat(),
    }


def _plan_from_payload(payload: dict[str, Any]) -> BrowserJourneyPlan:
    journeys = tuple(
        BrowserJourneySpecification(
            journey_id=item["journey_id"],
            capability_id=item["capability_id"],
            title=item["title"],
            start_path=item["start_path"],
            timeout_seconds=item["timeout_seconds"],
            steps=tuple(
                BrowserStep(
                    step_id=step["step_id"],
                    action=BrowserActionKind(step["action"]),
                    locator=None
                    if step["locator"] is None
                    else BrowserLocator(
                        BrowserLocatorKind(step["locator"]["kind"]),
                        step["locator"]["value"],
                        step["locator"]["accessible_name"],
                        step["locator"]["exact"],
                    ),
                    input_id=step["input_id"],
                    expected_text=step["expected_text"],
                    expected_path=step["expected_path"],
                )
                for step in item["steps"]
            ),
        )
        for item in payload["journeys"]
    )
    inputs = tuple(
        BrowserInputBinding(
            item["input_id"], item["public_value"], item["secret_reference"]
        )
        for item in payload["inputs"]
    )
    return BrowserJourneyPlan(
        plan_id=payload["plan_id"],
        run_id=payload["run_id"],
        product_id=payload["product_id"],
        configuration_id=payload["configuration_id"],
        configuration_revision=payload["configuration_revision"],
        configuration_digest=payload["configuration_digest"],
        commit_sha=payload["commit_sha"],
        acceptance_profile_id=payload["acceptance_profile_id"],
        acceptance_profile_version=payload["acceptance_profile_version"],
        acceptance_profile_digest=payload["acceptance_profile_digest"],
        journeys=journeys,
        inputs=inputs,
        created_by=payload["created_by"],
        created_at=datetime.fromisoformat(payload["created_at"]),
    )


def _result_payload(result: BrowserExecutionResult) -> dict[str, object]:
    return {
        "run_id": result.run_id,
        "product_id": result.product_id,
        "plan_id": result.plan_id,
        "plan_digest": result.plan_digest,
        "commit_sha": result.commit_sha,
        "stage": result.stage.value,
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "run_id": item.run_id,
                "capability_id": item.capability_id,
                "journey_id": item.journey_id,
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "commit_sha": item.commit_sha,
                "artifact_uri": item.artifact_uri,
                "digest": item.digest,
                "observed_at": item.observed_at.isoformat(),
                "summary": item.summary,
                "metadata": [list(pair) for pair in item.metadata],
            }
            for item in result.evidence
        ],
        "journey_results": [
            {
                "journey_id": item.journey_id,
                "outcome": item.outcome.value,
                "evidence_ids": list(item.evidence_ids),
                "completed_at": item.completed_at.isoformat(),
            }
            for item in result.journey_results
        ],
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "failure_code": result.failure_code,
    }


def _result_from_payload(payload: dict[str, Any]) -> BrowserExecutionResult:
    evidence = tuple(
        EvidenceArtifact(
            item["evidence_id"],
            item["run_id"],
            item["capability_id"],
            item["journey_id"],
            EvidenceKind(item["kind"]),
            EvidenceOutcome(item["outcome"]),
            item["commit_sha"],
            item["artifact_uri"],
            item["digest"],
            datetime.fromisoformat(item["observed_at"]),
            item["summary"],
            tuple(tuple(pair) for pair in item["metadata"]),
        )
        for item in payload["evidence"]
    )
    results = tuple(
        JourneyResult(
            item["journey_id"],
            EvidenceOutcome(item["outcome"]),
            tuple(item["evidence_ids"]),
            datetime.fromisoformat(item["completed_at"]),
        )
        for item in payload["journey_results"]
    )
    return BrowserExecutionResult(
        payload["run_id"],
        payload["product_id"],
        payload["plan_id"],
        payload["plan_digest"],
        payload["commit_sha"],
        BrowserExecutionStage(payload["stage"]),
        evidence,
        results,
        datetime.fromisoformat(payload["started_at"]),
        datetime.fromisoformat(payload["completed_at"]),
        payload["failure_code"],
    )
