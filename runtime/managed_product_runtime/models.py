"""Immutable, secret-safe managed-product runtime configuration values."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import ipaddress
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from urllib.parse import urlparse


MAX_ARGUMENTS = 32
MAX_COMMANDS = 20
MAX_SERVICES = 10
MAX_ENVIRONMENT_NAMES = 100
MAX_SECRET_REFERENCES = 50
MAX_ALLOWED_ORIGINS = 20
MAX_CONFIGURATION_BYTES = 64_000

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_EXECUTABLE = re.compile(r"^[A-Za-z0-9_.+-]{1,128}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_SECRET_NAME = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|CREDENTIAL|PRIVATE_?KEY|"
    r"ACCESS_?KEY|AUTHORIZATION|AUTH_?HEADER|DATABASE_URL|DSN|"
    r"CONNECTION_STRING|SESSION_COOKIE)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"Bearer\s+[A-Za-z0-9._-]{12,}|Basic\s+[A-Za-z0-9+/=]{8,})",
    re.I,
)
_SHELL_EXECUTABLES = {
    "bash",
    "cmd",
    "cmd.exe",
    "dash",
    "fish",
    "ksh",
    "powershell",
    "powershell.exe",
    "pwsh",
    "sh",
    "zsh",
}
_INTERPRETER_CODE_FLAGS = {"-c", "-e", "--eval"}
_SHELL_TOKENS = {"&&", "||", ";", "|", ">", ">>", "<", "2>", "2>&1"}


@dataclass(frozen=True)
class CommandSpec:
    executable: str
    arguments: tuple[str, ...] = ()
    working_directory: str = "."

    def __post_init__(self) -> None:
        if (
            not isinstance(self.executable, str)
            or not _EXECUTABLE.fullmatch(self.executable)
            or self.executable.casefold() in _SHELL_EXECUTABLES
        ):
            raise ValueError("Runtime command executable is unsafe")
        if not isinstance(self.arguments, tuple) or len(self.arguments) > MAX_ARGUMENTS:
            raise ValueError("Runtime command arguments must be a bounded tuple")
        lowered_executable = self.executable.casefold().removesuffix(".exe")
        for argument in self.arguments:
            if (
                not isinstance(argument, str)
                or len(argument) > 2_048
                or _has_control(argument)
                or argument in _SHELL_TOKENS
                or _looks_secret(argument)
                or _secret_option(argument)
                or _unsafe_argument_path(argument)
            ):
                raise ValueError("Runtime command argument is unsafe")
        if (
            self.arguments
            and (
                lowered_executable.startswith("python")
                or lowered_executable in {"node", "perl", "ruby"}
            )
            and self.arguments[0].casefold() in _INTERPRETER_CODE_FLAGS
        ):
            raise ValueError("Inline interpreter commands are prohibited")
        _relative_directory(self.working_directory)


@dataclass(frozen=True)
class OneShotCommand:
    command_id: str
    command: CommandSpec
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        _identifier(self.command_id, "runtime command ID")
        if not isinstance(self.command, CommandSpec):
            raise ValueError("Runtime command requires a CommandSpec")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 1_800
        ):
            raise ValueError("Runtime command timeout is outside policy")


@dataclass(frozen=True)
class ReadinessProbe:
    probe_id: str
    url: str
    expected_status_codes: tuple[int, ...] = (200,)
    timeout_seconds: int = 60
    interval_seconds: int = 1

    def __post_init__(self) -> None:
        _identifier(self.probe_id, "readiness probe ID")
        _endpoint_url(self.url, "readiness URL")
        if (
            not isinstance(self.expected_status_codes, tuple)
            or not self.expected_status_codes
            or self.expected_status_codes != tuple(sorted(set(self.expected_status_codes)))
            or any(
                isinstance(status, bool)
                or not isinstance(status, int)
                or not 200 <= status <= 399
                for status in self.expected_status_codes
            )
        ):
            raise ValueError("Readiness status codes must be unique 2xx/3xx values")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 600
            or isinstance(self.interval_seconds, bool)
            or not isinstance(self.interval_seconds, int)
            or not 1 <= self.interval_seconds <= 30
            or self.interval_seconds > self.timeout_seconds
        ):
            raise ValueError("Readiness timing is outside policy")


@dataclass(frozen=True)
class ManagedRuntimeService:
    service_id: str
    start_command: CommandSpec
    readiness_probe: ReadinessProbe
    stop_command: OneShotCommand
    startup_timeout_seconds: int = 120
    shutdown_timeout_seconds: int = 30

    def __post_init__(self) -> None:
        _identifier(self.service_id, "runtime service ID")
        if not isinstance(self.start_command, CommandSpec):
            raise ValueError("Runtime service requires a start command")
        if not isinstance(self.readiness_probe, ReadinessProbe):
            raise ValueError("Runtime service requires a readiness probe")
        if not isinstance(self.stop_command, OneShotCommand):
            raise ValueError("Runtime service requires a safe stop command")
        for value, label, maximum in (
            (self.startup_timeout_seconds, "startup", 600),
            (self.shutdown_timeout_seconds, "shutdown", 300),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= maximum
            ):
                raise ValueError(f"Runtime service {label} timeout is outside policy")


@dataclass(frozen=True)
class RuntimeEnvironmentVariable:
    name: str
    value: str

    def __post_init__(self) -> None:
        _environment_name(self.name)
        if _SECRET_NAME.search(self.name):
            raise ValueError("Sensitive environment names require secret references")
        if (
            not isinstance(self.value, str)
            or len(self.value) > 2_048
            or _has_control(self.value)
            or _looks_secret(self.value)
        ):
            raise ValueError("Runtime environment value is unsafe")


@dataclass(frozen=True)
class SecretEnvironmentReference:
    target_environment: str
    reference: str

    def __post_init__(self) -> None:
        _environment_name(self.target_environment)
        if (
            not isinstance(self.reference, str)
            or not _IDENTIFIER.fullmatch(self.reference)
            or _looks_secret(self.reference)
        ):
            raise ValueError("Secret must be supplied by an opaque safe reference")


@dataclass(frozen=True)
class ManagedProductRuntimeConfiguration:
    configuration_id: str
    project_id: str
    revision: int
    repository_url: str
    branch: str
    commit_sha: str
    frontend_url: str
    backend_url: str
    allowed_origins: tuple[str, ...]
    migration_commands: tuple[OneShotCommand, ...]
    services: tuple[ManagedRuntimeService, ...]
    environment_allow_list: tuple[str, ...]
    environment: tuple[RuntimeEnvironmentVariable, ...]
    secret_references: tuple[SecretEnvironmentReference, ...]
    acceptance_profile_id: str
    acceptance_profile_version: str
    acceptance_profile_digest: str
    created_by: str
    created_at: datetime
    supersedes_digest: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _identifier(self.configuration_id, "runtime configuration ID")
        _identifier(self.project_id, "runtime project ID")
        _identifier(self.acceptance_profile_id, "acceptance profile ID")
        _bounded_text(self.acceptance_profile_version, "acceptance profile version", 128)
        _bounded_text(self.created_by, "runtime configuration actor", 256)
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or not 1 <= self.revision <= 1_000_000
        ):
            raise ValueError("Runtime configuration revision must be positive")
        if self.schema_version != 1:
            raise ValueError("Unsupported runtime configuration schema")
        _repository_url(self.repository_url)
        _branch(self.branch)
        _sha(self.commit_sha, "runtime configuration commit")
        _endpoint_url(self.frontend_url, "frontend URL")
        _endpoint_url(self.backend_url, "backend URL")
        _digest(self.acceptance_profile_digest, "acceptance profile digest")
        _utc(self.created_at, "runtime configuration created_at")
        if self.revision == 1:
            if self.supersedes_digest is not None:
                raise ValueError("Initial runtime configuration cannot supersede a revision")
        else:
            if self.supersedes_digest is None:
                raise ValueError("Revised runtime configuration requires a prior digest")
            _digest(self.supersedes_digest, "superseded configuration digest")

        if (
            not isinstance(self.allowed_origins, tuple)
            or not self.allowed_origins
            or len(self.allowed_origins) > MAX_ALLOWED_ORIGINS
        ):
            raise ValueError("Runtime configuration requires bounded allowed origins")
        normalized_origins = tuple(sorted({_origin(value) for value in self.allowed_origins}))
        if self.allowed_origins != normalized_origins:
            raise ValueError("Allowed origins must be unique, canonical, and sorted")
        endpoint_origins = {
            endpoint_origin(self.frontend_url),
            endpoint_origin(self.backend_url),
        }
        if not endpoint_origins <= set(self.allowed_origins):
            raise ValueError("Frontend and backend origins must be explicitly allowed")

        if (
            not isinstance(self.migration_commands, tuple)
            or len(self.migration_commands) > MAX_COMMANDS
        ):
            raise ValueError("Migration commands must be a bounded tuple")
        if (
            not isinstance(self.services, tuple)
            or not self.services
            or len(self.services) > MAX_SERVICES
        ):
            raise ValueError("Runtime configuration requires bounded services")
        for command in self.migration_commands:
            if not isinstance(command, OneShotCommand):
                raise ValueError("Migration commands require OneShotCommand values")
        for service in self.services:
            if not isinstance(service, ManagedRuntimeService):
                raise ValueError("Runtime services require ManagedRuntimeService values")

        _unique(
            tuple(command.command_id for command in self.migration_commands)
            + tuple(service.stop_command.command_id for service in self.services),
            "runtime command IDs",
        )
        _unique(tuple(service.service_id for service in self.services), "runtime service IDs")
        _unique(
            tuple(service.readiness_probe.probe_id for service in self.services),
            "readiness probe IDs",
        )
        if any(
            endpoint_origin(service.readiness_probe.url) not in self.allowed_origins
            for service in self.services
        ):
            raise ValueError("Readiness probes must use an explicitly allowed origin")

        if (
            not isinstance(self.environment_allow_list, tuple)
            or len(self.environment_allow_list) > MAX_ENVIRONMENT_NAMES
        ):
            raise ValueError("Environment allow-list must be a bounded tuple")
        for name in self.environment_allow_list:
            _environment_name(name)
        if self.environment_allow_list != tuple(sorted(set(self.environment_allow_list))):
            raise ValueError("Environment allow-list must be unique and sorted")
        if (
            not isinstance(self.environment, tuple)
            or len(self.environment) > MAX_ENVIRONMENT_NAMES
            or not isinstance(self.secret_references, tuple)
            or len(self.secret_references) > MAX_SECRET_REFERENCES
        ):
            raise ValueError("Runtime environment declarations are outside policy")
        if any(not isinstance(item, RuntimeEnvironmentVariable) for item in self.environment):
            raise ValueError("Public environment requires RuntimeEnvironmentVariable values")
        if any(not isinstance(item, SecretEnvironmentReference) for item in self.secret_references):
            raise ValueError("Secrets require SecretEnvironmentReference values")
        public_names = tuple(item.name for item in self.environment)
        secret_names = tuple(item.target_environment for item in self.secret_references)
        if self.environment != tuple(sorted(self.environment, key=lambda item: item.name)):
            raise ValueError("Public environment declarations must be sorted")
        if self.secret_references != tuple(
            sorted(self.secret_references, key=lambda item: item.target_environment)
        ):
            raise ValueError("Secret references must be sorted")
        _unique(public_names, "public environment names", allow_empty=True)
        _unique(secret_names, "secret environment names", allow_empty=True)
        if set(public_names) & set(secret_names):
            raise ValueError("Public and secret environment declarations cannot overlap")
        if set(self.environment_allow_list) != set(public_names) | set(secret_names):
            raise ValueError("Environment allow-list must exactly cover declared values")

        encoded = _canonical_configuration(self)
        if len(encoded) > MAX_CONFIGURATION_BYTES:
            raise ValueError("Runtime configuration exceeds its size limit")

    @property
    def digest(self) -> str:
        return configuration_digest(self)


def configuration_digest(configuration: ManagedProductRuntimeConfiguration) -> str:
    if not isinstance(configuration, ManagedProductRuntimeConfiguration):
        raise TypeError("configuration must be a ManagedProductRuntimeConfiguration")
    return hashlib.sha256(_canonical_configuration(configuration)).hexdigest()


def endpoint_origin(value: str) -> str:
    parsed = _endpoint_url(value, "runtime endpoint")
    host = parsed.hostname or ""
    rendered_host = f"[{host}]" if ":" in host else host
    port = parsed.port
    default = (parsed.scheme == "http" and port == 80) or (
        parsed.scheme == "https" and port == 443
    )
    suffix = "" if port is None or default else f":{port}"
    return f"{parsed.scheme}://{rendered_host}{suffix}"


def repository_key(value: str) -> str:
    _repository_url(value)
    return value.rstrip("/").removesuffix(".git").casefold()


def _canonical_configuration(configuration: ManagedProductRuntimeConfiguration) -> bytes:
    payload = asdict(configuration)
    payload["created_at"] = configuration.created_at.isoformat()
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")


def _bounded_text(value: str, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or _has_control(value)
    ):
        raise ValueError(f"{label} must be bounded text")


def _environment_name(value: str) -> None:
    if not isinstance(value, str) or not _ENVIRONMENT_NAME.fullmatch(value):
        raise ValueError("Environment name is invalid")


def _relative_directory(value: str) -> None:
    if not isinstance(value, str) or not value or "\\" in value or _has_control(value):
        raise ValueError("Runtime working directory is unsafe")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or any(part.casefold() == ".git" for part in posix.parts)
        or value != str(posix)
    ):
        raise ValueError("Runtime working directory is unsafe")


def _branch(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or _has_control(value)
        or "\\" in value
        or value.startswith(("-", "/", "."))
        or value.endswith(("/", "."))
        or "//" in value
        or ".." in value
        or "@{" in value
        or value == "@"
        or any(character in value for character in " ~^:?*[")
        or any(
            part in {"", ".", ".."}
            or part.startswith(".")
            or part.endswith((".", ".lock"))
            for part in value.split("/")
        )
    ):
        raise ValueError("Runtime branch is not a safe Git reference")


def _sha(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} requires a full lowercase hexadecimal SHA")


def _digest(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} requires a lowercase SHA-256 digest")


def _repository_url(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2_048
        or value.startswith("-")
        or _has_control(value)
        or "\\" in value
        or "%" in value
    ):
        raise ValueError("Runtime repository URL is unsafe")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https", "ssh"}
        or not parsed.hostname
        or parsed.password is not None
        or (parsed.scheme in {"http", "https"} and parsed.username is not None)
        or parsed.query
        or parsed.fragment
        or parsed.params
        or not parsed.path.strip("/")
    ):
        raise ValueError("Runtime repository URL is unsafe")
    _url_path(parsed.path, "Runtime repository URL")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Runtime repository port is invalid") from error
    if port == 0:
        raise ValueError("Runtime repository port is invalid")
    if parsed.scheme == "http" and not _loopback(parsed.hostname):
        raise ValueError("External runtime repository requires HTTPS")


def _endpoint_url(value: str, label: str):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2_048
        or _has_control(value)
        or "\\" in value
        or "%" in value
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{label} is unsafe")
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.params
    ):
        raise ValueError(f"{label} is unsafe")
    _url_path(parsed.path, label)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"{label} has an invalid port") from error
    if port == 0:
        raise ValueError(f"{label} has an invalid port")
    if parsed.hostname in {"0.0.0.0", "::"}:
        raise ValueError(f"{label} cannot target an unspecified host")
    if parsed.scheme == "http" and not _loopback(parsed.hostname):
        raise ValueError(f"{label} requires HTTPS outside loopback")
    return parsed


def _origin(value: str) -> str:
    parsed = _endpoint_url(value, "allowed origin")
    if parsed.path not in {"", "/"} or parsed.params:
        raise ValueError("Allowed origin cannot contain a path")
    return endpoint_origin(value)


def _url_path(path: str, label: str) -> None:
    segments = path.split("/")
    if "//" in path or any(segment in {".", ".."} for segment in segments):
        raise ValueError(f"{label} path is not canonical")


def _loopback(hostname: str) -> bool:
    if hostname.casefold() == "localhost" or hostname.casefold().endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _looks_secret(value: str) -> bool:
    if _SECRET_VALUE.search(value):
        return True
    lowered = value.casefold()
    if any(
        marker in lowered
        for marker in (
            "password=",
            "token=",
            "secret=",
            "client_secret=",
            "api_key=",
            "access_key=",
            "authorization=",
        )
    ):
        return True
    if "://" in value:
        parsed = urlparse(value)
        if parsed.username is not None or parsed.password is not None:
            return True
    return False


def _secret_option(value: str) -> bool:
    option = value.split("=", 1)[0]
    if not option.startswith("-"):
        return False
    normalized = option.lstrip("-").replace("-", "_")
    return bool(_SECRET_NAME.search(normalized))


def _unsafe_argument_path(value: str) -> bool:
    candidate = value.split("=", 1)[1] if value.startswith("-") and "=" in value else value
    lowered = candidate.casefold()
    posix = PurePosixPath(candidate)
    windows = PureWindowsPath(candidate)
    return (
        candidate.startswith(("/", "~"))
        or "\\" in candidate
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
        or any(marker in lowered for marker in ("%2e", "%2f", "%5c"))
    )


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _unique(values: tuple[str, ...], label: str, *, allow_empty: bool = False) -> None:
    if (not values and not allow_empty) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _utc(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must use UTC")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")
