"""Immutable values for exact-SHA managed-product environment verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class EnvironmentStage(str, Enum):
    PREPARING = "PREPARING"
    MIGRATING = "MIGRATING"
    STARTING = "STARTING"
    READY = "READY"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class EnvironmentObservationKind(str, Enum):
    SOURCE = "SOURCE"
    MIGRATION = "MIGRATION"
    SERVICE_STARTUP = "SERVICE_STARTUP"
    READINESS = "READINESS"
    SERVICE_STOP = "SERVICE_STOP"
    CLEANUP = "CLEANUP"


class EnvironmentObservationOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class EnvironmentExecutionRequest:
    run_id: str
    project_id: str
    configuration_id: str
    configuration_revision: int
    configuration_digest: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.run_id, "environment run ID"),
            (self.project_id, "environment project ID"),
            (self.configuration_id, "environment configuration ID"),
        ):
            _identifier(value, label)
        if (
            isinstance(self.configuration_revision, bool)
            or not isinstance(self.configuration_revision, int)
            or self.configuration_revision < 1
        ):
            raise ValueError("Environment configuration revision must be positive")
        _digest(self.configuration_digest, "environment configuration digest")


@dataclass(frozen=True)
class EnvironmentExecutionPolicy:
    allowed_repository_hosts: frozenset[str]
    allowed_executables: frozenset[str]
    allowed_origins: frozenset[str]
    allowed_environment_names: frozenset[str]
    allowed_secret_references: frozenset[str] = frozenset()
    allowed_secret_reference_prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for values, label in (
            (self.allowed_repository_hosts, "repository hosts"),
            (self.allowed_executables, "executables"),
            (self.allowed_origins, "origins"),
            (self.allowed_environment_names, "environment names"),
        ):
            if not isinstance(values, frozenset) or not values:
                raise ValueError(f"Environment policy {label} must be a non-empty frozenset")
            if any(
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or _has_control(value)
                for value in values
            ):
                raise ValueError(f"Environment policy {label} contains an unsafe value")
        if not isinstance(self.allowed_secret_references, frozenset) or any(
            not isinstance(value, str) or not _IDENTIFIER.fullmatch(value)
            for value in self.allowed_secret_references
        ):
            raise ValueError("Environment policy secret references are unsafe")
        if (
            not isinstance(self.allowed_secret_reference_prefixes, tuple)
            or len(self.allowed_secret_reference_prefixes)
            != len(set(self.allowed_secret_reference_prefixes))
            or any(
                not isinstance(value, str)
                or not value
                or len(value) > 128
                or not value.endswith((".", "-", "_"))
                or _has_control(value)
                for value in self.allowed_secret_reference_prefixes
            )
        ):
            raise ValueError("Environment policy secret-reference prefixes are unsafe")


@dataclass(frozen=True)
class EnvironmentObservation:
    kind: EnvironmentObservationKind
    subject_id: str
    outcome: EnvironmentObservationOutcome
    started_at: datetime
    completed_at: datetime
    summary: str
    output_digest: str
    exit_code: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EnvironmentObservationKind):
            raise ValueError("Environment observation kind is invalid")
        if not isinstance(self.outcome, EnvironmentObservationOutcome):
            raise ValueError("Environment observation outcome is invalid")
        _identifier(self.subject_id, "environment observation subject")
        _utc(self.started_at, "environment observation started_at")
        _utc(self.completed_at, "environment observation completed_at")
        if self.completed_at < self.started_at:
            raise ValueError("Environment observation time cannot move backwards")
        if (
            not isinstance(self.summary, str)
            or not self.summary
            or len(self.summary) > 512
            or _has_control(self.summary)
        ):
            raise ValueError("Environment observation summary must be bounded text")
        _digest(self.output_digest, "environment observation output digest")
        if self.exit_code is not None and (
            isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)
        ):
            raise ValueError("Environment observation exit code is invalid")


@dataclass(frozen=True)
class PreparedEnvironment:
    workspace_id: str
    path: Path
    observed_commit_sha: str

    def __post_init__(self) -> None:
        _identifier(self.workspace_id, "environment workspace ID")
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("Prepared environment path must be absolute")
        _sha(self.observed_commit_sha, "prepared environment commit")


@dataclass(frozen=True)
class ManagedProductEnvironmentResult:
    run_id: str
    project_id: str
    configuration_id: str
    configuration_revision: int
    configuration_digest: str
    commit_sha: str
    stage: EnvironmentStage
    observations: tuple[EnvironmentObservation, ...]
    started_at: datetime
    completed_at: datetime
    failure_code: str | None = None
    workspace_retained: bool = False

    def __post_init__(self) -> None:
        EnvironmentExecutionRequest(
            self.run_id,
            self.project_id,
            self.configuration_id,
            self.configuration_revision,
            self.configuration_digest,
        )
        _sha(self.commit_sha, "environment result commit")
        if not isinstance(self.stage, EnvironmentStage) or self.stage in {
            EnvironmentStage.PREPARING,
            EnvironmentStage.MIGRATING,
            EnvironmentStage.STARTING,
            EnvironmentStage.READY,
            EnvironmentStage.STOPPING,
        }:
            raise ValueError("Environment result must be terminal")
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, EnvironmentObservation) for item in self.observations
        ):
            raise ValueError("Environment result observations must be a tuple")
        _utc(self.started_at, "environment result started_at")
        _utc(self.completed_at, "environment result completed_at")
        if self.completed_at < self.started_at:
            raise ValueError("Environment result time cannot move backwards")
        if self.stage is EnvironmentStage.STOPPED:
            if self.failure_code is not None or self.workspace_retained:
                raise ValueError("Successful environment verification cannot retain failure state")
        else:
            _identifier(self.failure_code, "environment failure code")
        if self.stage is EnvironmentStage.RECONCILIATION_REQUIRED and not self.workspace_retained:
            raise ValueError("Reconciliation-required environment must retain its workspace")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["stage"] = self.stage.value
        payload["started_at"] = self.started_at.isoformat()
        payload["completed_at"] = self.completed_at.isoformat()
        payload["observations"] = [
            {
                **asdict(item),
                "kind": item.kind.value,
                "outcome": item.outcome.value,
                "started_at": item.started_at.isoformat(),
                "completed_at": item.completed_at.isoformat(),
            }
            for item in self.observations
        ]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def empty_output_digest() -> str:
    return hashlib.sha256(b"").hexdigest()


def _identifier(value: str | None, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")


def _sha(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} requires a lowercase full commit SHA")


def _digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} requires a lowercase SHA-256 digest")


def _utc(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must use UTC")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
