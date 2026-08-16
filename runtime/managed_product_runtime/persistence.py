"""Revisioned, integrity-checked managed-product runtime configuration stores."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from threading import Lock, RLock
from typing import Any, Iterator, Protocol, runtime_checkable

from runtime.managed_product_runtime.errors import (
    RuntimeConfigurationConflictError,
    RuntimeConfigurationCorruptError,
    RuntimeConfigurationNotFoundError,
)
from runtime.managed_product_runtime.models import (
    CommandSpec,
    ManagedProductRuntimeConfiguration,
    ManagedRuntimeService,
    OneShotCommand,
    ReadinessProbe,
    RuntimeEnvironmentVariable,
    SecretEnvironmentReference,
    configuration_digest,
)


_STORE_SCHEMA_VERSION = 1
_SAFE_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PROCESS_LOCKS: dict[str, RLock] = {}
_PROCESS_LOCKS_GUARD = Lock()

_fcntl: Any
try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised on non-POSIX hosts
    _fcntl = None


@runtime_checkable
class RuntimeConfigurationStore(Protocol):
    """Provider-neutral immutable-revision storage contract."""

    def save(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        *,
        expected_revision: int | None = None,
    ) -> ManagedProductRuntimeConfiguration: ...

    def get(
        self, project_id: str, configuration_id: str
    ) -> ManagedProductRuntimeConfiguration: ...

    def get_revision(
        self, project_id: str, configuration_id: str, revision: int
    ) -> ManagedProductRuntimeConfiguration: ...

    def list_for_project(
        self, project_id: str
    ) -> tuple[ManagedProductRuntimeConfiguration, ...]: ...

    def list_revisions(
        self, project_id: str, configuration_id: str
    ) -> tuple[ManagedProductRuntimeConfiguration, ...]: ...


class InMemoryRuntimeConfigurationStore:
    """Thread-safe deterministic store used for composition and tests."""

    def __init__(self) -> None:
        self._history: dict[
            tuple[str, str], dict[int, ManagedProductRuntimeConfiguration]
        ] = {}
        self._lock = RLock()

    def save(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        *,
        expected_revision: int | None = None,
    ) -> ManagedProductRuntimeConfiguration:
        _configuration(configuration)
        with self._lock:
            key = (configuration.project_id, configuration.configuration_id)
            history = self._history.get(key, {})
            current = history[max(history)] if history else None
            idempotent = _validate_transition(
                configuration, current, expected_revision=expected_revision
            )
            if idempotent:
                return current  # type: ignore[return-value]
            history = dict(history)
            history[configuration.revision] = configuration
            self._history[key] = history
            return configuration

    def get(
        self, project_id: str, configuration_id: str
    ) -> ManagedProductRuntimeConfiguration:
        key = (_safe_identity(project_id), _safe_identity(configuration_id))
        with self._lock:
            history = self._history.get(key)
            if not history:
                raise _not_found(project_id, configuration_id)
            return history[max(history)]

    def get_revision(
        self, project_id: str, configuration_id: str, revision: int
    ) -> ManagedProductRuntimeConfiguration:
        key = (_safe_identity(project_id), _safe_identity(configuration_id))
        _revision(revision)
        with self._lock:
            try:
                return self._history[key][revision]
            except KeyError as error:
                raise RuntimeConfigurationNotFoundError(
                    f"Runtime configuration {project_id!r}/{configuration_id!r} "
                    f"revision {revision} does not exist"
                ) from error

    def list_for_project(
        self, project_id: str
    ) -> tuple[ManagedProductRuntimeConfiguration, ...]:
        _safe_identity(project_id)
        with self._lock:
            return tuple(
                self._history[key][max(self._history[key])]
                for key in sorted(self._history)
                if key[0] == project_id
            )

    def list_revisions(
        self, project_id: str, configuration_id: str
    ) -> tuple[ManagedProductRuntimeConfiguration, ...]:
        key = (_safe_identity(project_id), _safe_identity(configuration_id))
        with self._lock:
            history = self._history.get(key)
            if not history:
                raise _not_found(project_id, configuration_id)
            return tuple(history[number] for number in sorted(history))


class FileRuntimeConfigurationStore:
    """Atomic POSIX file store with immutable snapshots and optimistic updates."""

    def __init__(self, root: str | Path) -> None:
        if _fcntl is None:
            raise RuntimeError(
                "FileRuntimeConfigurationStore requires POSIX advisory file locking"
            )
        candidate = Path(root)
        if not str(candidate):
            raise ValueError("Runtime configuration store root is required")
        self.root = candidate.resolve()

    def save(
        self,
        configuration: ManagedProductRuntimeConfiguration,
        *,
        expected_revision: int | None = None,
    ) -> ManagedProductRuntimeConfiguration:
        _configuration(configuration)
        directory = self._directory(
            configuration.project_id, configuration.configuration_id
        )
        directory.mkdir(parents=True, exist_ok=True)
        with self._exclusive_lock(directory):
            current = self._load_current_if_present(directory, validate_history=False)
            self._validate_history_for_save(directory, current, configuration)
            idempotent = _validate_transition(
                configuration, current, expected_revision=expected_revision
            )
            if idempotent:
                return current  # type: ignore[return-value]

            revision_path = self._revision_path(directory, configuration.revision)
            if revision_path.exists():
                orphan = self._load(
                    revision_path,
                    expected_project_id=configuration.project_id,
                    expected_configuration_id=configuration.configuration_id,
                )
                if orphan != configuration:
                    raise RuntimeConfigurationConflictError(
                        "Runtime configuration revision history is immutable"
                    )
            else:
                self._atomic_write(revision_path, configuration, replace=False)
            self._atomic_write(directory / "current.json", configuration, replace=True)
            return configuration

    def get(
        self, project_id: str, configuration_id: str
    ) -> ManagedProductRuntimeConfiguration:
        directory = self._directory(project_id, configuration_id)
        current = self._load_current_if_present(directory, validate_history=True)
        if current is None:
            if (directory / "revisions").exists():
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration history has no current pointer"
                )
            raise _not_found(project_id, configuration_id)
        return current

    def get_revision(
        self, project_id: str, configuration_id: str, revision: int
    ) -> ManagedProductRuntimeConfiguration:
        directory = self._directory(project_id, configuration_id)
        _revision(revision)
        self.get(project_id, configuration_id)
        path = self._revision_path(directory, revision)
        if not path.exists():
            raise RuntimeConfigurationNotFoundError(
                f"Runtime configuration {project_id!r}/{configuration_id!r} "
                f"revision {revision} does not exist"
            )
        value = self._load(
            path,
            expected_project_id=project_id,
            expected_configuration_id=configuration_id,
        )
        if value.revision != revision:
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration revision path does not match its content"
            )
        return value

    def list_for_project(
        self, project_id: str
    ) -> tuple[ManagedProductRuntimeConfiguration, ...]:
        project_root = self.root / _safe_identity(project_id)
        if not project_root.exists():
            return ()
        values: list[ManagedProductRuntimeConfiguration] = []
        for path in sorted(project_root.iterdir(), key=lambda item: item.name):
            if path.is_dir():
                values.append(self.get(project_id, _safe_identity(path.name)))
        return tuple(values)

    def list_revisions(
        self, project_id: str, configuration_id: str
    ) -> tuple[ManagedProductRuntimeConfiguration, ...]:
        directory = self._directory(project_id, configuration_id)
        revision_root = directory / "revisions"
        if not revision_root.exists():
            raise _not_found(project_id, configuration_id)
        values: list[ManagedProductRuntimeConfiguration] = []
        for path in sorted(revision_root.glob("*.json")):
            if not re.fullmatch(r"[0-9]{8}\.json", path.name):
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration revision directory contains an unsafe entry"
                )
            revision = int(path.stem)
            value = self._load(
                path,
                expected_project_id=project_id,
                expected_configuration_id=configuration_id,
            )
            if value.revision != revision:
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration revision path does not match its content"
                )
            values.append(value)
        if not values:
            raise _not_found(project_id, configuration_id)
        if tuple(item.revision for item in values) != tuple(range(1, len(values) + 1)):
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration revision history is not contiguous"
            )
        current = self._load_current_if_present(directory, validate_history=False)
        if current is None:
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration history has no current pointer"
            )
        if values[-1] != current:
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration current pointer is inconsistent"
            )
        self._validate_history(directory, current)
        return tuple(values)

    def _directory(self, project_id: str, configuration_id: str) -> Path:
        project = _safe_identity(project_id)
        configuration = _safe_identity(configuration_id)
        directory = self.root / project / configuration
        try:
            directory.resolve().relative_to(self.root)
        except ValueError as error:
            raise ValueError("Unsafe runtime configuration identity") from error
        return directory

    @staticmethod
    def _revision_path(directory: Path, revision: int) -> Path:
        _revision(revision)
        return directory / "revisions" / f"{revision:08d}.json"

    def _load_current_if_present(
        self, directory: Path, *, validate_history: bool
    ) -> ManagedProductRuntimeConfiguration | None:
        target = directory / "current.json"
        if not target.exists():
            return None
        value = self._load(
            target,
            expected_project_id=directory.parent.name,
            expected_configuration_id=directory.name,
        )
        if validate_history:
            self._validate_history(directory, value)
        return value

    def _validate_history(
        self,
        directory: Path,
        current: ManagedProductRuntimeConfiguration,
    ) -> None:
        revision_root = directory / "revisions"
        if not revision_root.is_dir():
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration has no immutable revision history"
            )
        entries = self._revision_entries(revision_root)
        expected_names = [f"{number:08d}.json" for number in range(1, current.revision + 1)]
        if [item.name for item in entries] != expected_names:
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration revision history is not contiguous"
            )
        previous: ManagedProductRuntimeConfiguration | None = None
        for number, path in enumerate(entries, start=1):
            value = self._load(
                path,
                expected_project_id=current.project_id,
                expected_configuration_id=current.configuration_id,
            )
            if value.revision != number or (
                previous is not None and value.supersedes_digest != previous.digest
            ):
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration revision chain cannot be trusted"
                )
            previous = value
        if previous != current:
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration current pointer is inconsistent"
            )

    def _validate_history_for_save(
        self,
        directory: Path,
        current: ManagedProductRuntimeConfiguration | None,
        candidate: ManagedProductRuntimeConfiguration,
    ) -> None:
        revision_root = directory / "revisions"
        if not revision_root.exists():
            if current is not None:
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration has no immutable revision history"
                )
            return
        if not revision_root.is_dir():
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration revision history is unsafe"
            )
        entries = self._revision_entries(revision_root)
        if current is None:
            if not entries:
                return
            expected_orphan = [f"{candidate.revision:08d}.json"]
            if candidate.revision != 1 or [item.name for item in entries] != expected_orphan:
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration history has no trustworthy current pointer"
                )
            orphan = self._load(
                entries[0],
                expected_project_id=candidate.project_id,
                expected_configuration_id=candidate.configuration_id,
            )
            if orphan != candidate:
                raise RuntimeConfigurationConflictError(
                    "Runtime configuration orphan revision conflicts with the candidate"
                )
            return

        committed_names = [
            f"{number:08d}.json" for number in range(1, current.revision + 1)
        ]
        actual_names = [item.name for item in entries]
        allowed_names = committed_names
        has_candidate_orphan = (
            candidate.revision == current.revision + 1
            and actual_names == committed_names + [f"{candidate.revision:08d}.json"]
        )
        if actual_names != allowed_names and not has_candidate_orphan:
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration revision history is not contiguous"
            )
        self._validate_committed_entries(entries[: current.revision], current)
        if has_candidate_orphan:
            orphan = self._load(
                entries[-1],
                expected_project_id=candidate.project_id,
                expected_configuration_id=candidate.configuration_id,
            )
            if orphan != candidate:
                raise RuntimeConfigurationConflictError(
                    "Runtime configuration orphan revision conflicts with the candidate"
                )

    def _validate_committed_entries(
        self,
        entries: list[Path],
        current: ManagedProductRuntimeConfiguration,
    ) -> None:
        previous: ManagedProductRuntimeConfiguration | None = None
        for number, path in enumerate(entries, start=1):
            value = self._load(
                path,
                expected_project_id=current.project_id,
                expected_configuration_id=current.configuration_id,
            )
            if value.revision != number or (
                previous is not None and value.supersedes_digest != previous.digest
            ):
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration revision chain cannot be trusted"
                )
            previous = value
        if previous != current:
            raise RuntimeConfigurationCorruptError(
                "Runtime configuration current pointer is inconsistent"
            )

    @staticmethod
    def _revision_entries(revision_root: Path) -> list[Path]:
        snapshots: list[Path] = []
        internal_temporary = re.compile(r"^\.[0-9]{8}\.json\..+\.tmp$")
        for path in sorted(revision_root.iterdir(), key=lambda item: item.name):
            if re.fullmatch(r"[0-9]{8}\.json", path.name) and path.is_file():
                snapshots.append(path)
            elif internal_temporary.fullmatch(path.name) and path.is_file():
                continue
            else:
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration revision directory contains an unsafe entry"
                )
        return snapshots

    @contextmanager
    def _exclusive_lock(self, directory: Path) -> Iterator[None]:
        key = str(directory.resolve())
        with _PROCESS_LOCKS_GUARD:
            process_lock = _PROCESS_LOCKS.setdefault(key, RLock())
        with process_lock:
            if _fcntl is None:
                raise RuntimeError(
                    "FileRuntimeConfigurationStore requires POSIX advisory file locking"
                )
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                _fcntl.flock(descriptor, _fcntl.LOCK_EX)
                yield
            finally:
                _fcntl.flock(descriptor, _fcntl.LOCK_UN)
                os.close(descriptor)

    def _atomic_write(
        self,
        target: Path,
        configuration: ManagedProductRuntimeConfiguration,
        *,
        replace: bool,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not replace and target.exists():
            raise RuntimeConfigurationConflictError(
                "Runtime configuration revision history is immutable"
            )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            payload = _envelope(configuration)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if not replace and target.exists():
                raise RuntimeConfigurationConflictError(
                    "Runtime configuration revision history is immutable"
                )
            os.replace(temporary, target)
            self._fsync_directory(target.parent)
        except Exception:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _load(
        path: Path,
        *,
        expected_project_id: str | None = None,
        expected_configuration_id: str | None = None,
    ) -> ManagedProductRuntimeConfiguration:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version") != _STORE_SCHEMA_VERSION
                or not isinstance(payload.get("digest"), str)
                or not isinstance(payload.get("configuration"), dict)
                or set(payload) != {"schema_version", "digest", "configuration"}
            ):
                raise ValueError("unsupported configuration envelope")
            value = _decode_configuration(payload["configuration"])
            if payload["digest"] != configuration_digest(value):
                raise ValueError("configuration digest mismatch")
            if (
                expected_project_id is not None
                and value.project_id != expected_project_id
            ) or (
                expected_configuration_id is not None
                and value.configuration_id != expected_configuration_id
            ):
                raise RuntimeConfigurationCorruptError(
                    "Runtime configuration identity does not match its storage path"
                )
            return value
        except RuntimeConfigurationCorruptError:
            raise
        except Exception as error:
            raise RuntimeConfigurationCorruptError(
                f"Runtime configuration snapshot {path.name!r} cannot be trusted"
            ) from error


def _validate_transition(
    candidate: ManagedProductRuntimeConfiguration,
    current: ManagedProductRuntimeConfiguration | None,
    *,
    expected_revision: int | None,
) -> bool:
    if expected_revision is not None:
        _revision(expected_revision)
    if current is None:
        if expected_revision is not None or candidate.revision != 1:
            raise RuntimeConfigurationConflictError(
                "New runtime configuration must start at revision 1 without an expectation"
            )
        return False
    if candidate == current:
        return True
    if expected_revision != current.revision:
        raise RuntimeConfigurationConflictError(
            "Runtime configuration was changed by another writer"
        )
    if candidate.revision != current.revision + 1:
        raise RuntimeConfigurationConflictError(
            "Runtime configuration revisions must be contiguous"
        )
    if candidate.project_id != current.project_id or (
        candidate.configuration_id != current.configuration_id
    ):
        raise RuntimeConfigurationConflictError(
            "Runtime configuration identity is immutable"
        )
    if candidate.repository_url != current.repository_url:
        raise RuntimeConfigurationConflictError(
            "Runtime configuration repository identity is immutable"
        )
    if candidate.supersedes_digest != current.digest:
        raise RuntimeConfigurationConflictError(
            "Runtime configuration revision does not bind its predecessor"
        )
    return False


def _configuration(value: object) -> None:
    if not isinstance(value, ManagedProductRuntimeConfiguration):
        raise TypeError("configuration must be a ManagedProductRuntimeConfiguration")


def _safe_identity(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTITY.fullmatch(value):
        raise ValueError("Unsafe runtime configuration identity")
    return value


def _revision(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1_000_000:
        raise ValueError("Runtime configuration revision must be positive")


def _not_found(project_id: str, configuration_id: str) -> RuntimeConfigurationNotFoundError:
    return RuntimeConfigurationNotFoundError(
        f"Runtime configuration {project_id!r}/{configuration_id!r} does not exist"
    )


def _envelope(configuration: ManagedProductRuntimeConfiguration) -> dict[str, object]:
    value = asdict(configuration)
    value["created_at"] = configuration.created_at.isoformat()
    return {
        "schema_version": _STORE_SCHEMA_VERSION,
        "digest": configuration_digest(configuration),
        "configuration": value,
    }


def _decode_configuration(data: dict[str, object]) -> ManagedProductRuntimeConfiguration:
    value = dict(data)
    value["created_at"] = datetime.fromisoformat(_required_string(value, "created_at"))
    value["allowed_origins"] = tuple(_required_string_list(value, "allowed_origins"))
    value["environment_allow_list"] = tuple(
        _required_string_list(value, "environment_allow_list")
    )
    value["migration_commands"] = tuple(
        _one_shot(item) for item in _required_list(value, "migration_commands")
    )
    value["services"] = tuple(
        _service(item) for item in _required_list(value, "services")
    )
    value["environment"] = tuple(
        RuntimeEnvironmentVariable(**_mapping(item))
        for item in _required_list(value, "environment")
    )
    value["secret_references"] = tuple(
        SecretEnvironmentReference(**_mapping(item))
        for item in _required_list(value, "secret_references")
    )
    return ManagedProductRuntimeConfiguration(**value)  # type: ignore[arg-type]


def _one_shot(value: object) -> OneShotCommand:
    data = _mapping(value)
    data["command"] = _command(data["command"])
    return OneShotCommand(**data)


def _service(value: object) -> ManagedRuntimeService:
    data = _mapping(value)
    data["start_command"] = _command(data["start_command"])
    probe = _mapping(data["readiness_probe"])
    probe["expected_status_codes"] = tuple(probe["expected_status_codes"])
    data["readiness_probe"] = ReadinessProbe(**probe)
    data["stop_command"] = _one_shot(data["stop_command"])
    return ManagedRuntimeService(**data)


def _command(value: object) -> CommandSpec:
    data = _mapping(value)
    data["arguments"] = tuple(data.get("arguments", ()))
    return CommandSpec(**data)


def _mapping(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Runtime configuration member must be an object")
    return dict(value)


def _required_list(data: dict[str, object], key: str) -> list:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Runtime configuration {key} must be a list")
    return value


def _required_string_list(data: dict[str, object], key: str) -> list[str]:
    value = _required_list(data, key)
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"Runtime configuration {key} must contain text")
    return value


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Runtime configuration {key} must be text")
    return value
