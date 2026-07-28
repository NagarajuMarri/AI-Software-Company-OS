from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re


class WorkerStatus(str, Enum):
    STARTING = "STARTING"
    IDLE = "IDLE"
    CLAIMING = "CLAIMING"
    DISPATCHING = "DISPATCHING"
    RECONCILING = "RECONCILING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    UNHEALTHY = "UNHEALTHY"
    STALE = "STALE"
    FAILED = "FAILED"


@dataclass
class WorkerRegistration:
    worker_id: str
    worker_instance_id: str
    process_id: int
    node_reference: str
    runtime_id: str
    worker_type: str
    supported_operation_types: tuple[str, ...]
    supported_provider_capabilities: tuple[str, ...]
    status: WorkerStatus
    started_at: datetime
    registered_at: datetime
    last_heartbeat_at: datetime
    heartbeat_expires_at: datetime
    stopped_at: datetime | None = None
    current_operation_id: str | None = None
    version: int = 0
    build_reference: str | None = None
    correlation_id: str | None = None
    shutdown_requested: bool = False

    def __post_init__(self):
        identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
        for value in (
            self.worker_id, self.worker_instance_id, self.node_reference,
            self.runtime_id, self.worker_type,
        ):
            if not isinstance(value, str) or not identifier.fullmatch(value):
                raise ValueError("Invalid worker registration identity")
        if self.process_id < 0:
            raise ValueError("Invalid process identifier")
        for values in (
            self.supported_operation_types,
            self.supported_provider_capabilities,
        ):
            if not values or any(not identifier.fullmatch(item) for item in values):
                raise ValueError("Invalid worker capabilities")
        for value in (
            self.started_at, self.registered_at, self.last_heartbeat_at,
            self.heartbeat_expires_at,
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Worker timestamps must be timezone-aware")


@dataclass(frozen=True)
class WorkerConfiguration:
    runtime_id: str
    worker_id_prefix: str
    persistence_reference: str
    supported_operation_types: tuple[str, ...]
    supported_provider_ids: tuple[str, ...]
    polling_interval_seconds: float = 1.0
    heartbeat_interval_seconds: float = 5.0
    heartbeat_timeout_seconds: float = 15.0
    claim_duration_seconds: float = 30.0
    claim_renewal_interval_seconds: float = 10.0
    maximum_operations: int = 100
    maximum_runtime_seconds: float = 3600.0
    shutdown_grace_seconds: float = 10.0
    maximum_idle_cycles: int = 10
    log_level: str = "INFO"

    def __post_init__(self):
        identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
        if not identifier.fullmatch(self.runtime_id) or not identifier.fullmatch(
            self.worker_id_prefix
        ):
            raise ValueError("Invalid worker configuration identity")
        if any(
            marker in self.persistence_reference.lower()
            for marker in ("password=", "token=", "secret=", "@")
        ):
            raise ValueError(
                "Persistence configuration must be a safe reference"
            )
        if not (
            0 < self.heartbeat_interval_seconds
            < self.heartbeat_timeout_seconds
        ):
            raise ValueError("Heartbeat timeout must exceed interval")
        if not (
            0 < self.claim_renewal_interval_seconds
            < self.claim_duration_seconds
        ):
            raise ValueError("Claim renewal must precede expiry")
        if (
            self.polling_interval_seconds < 0
            or not 1 <= self.maximum_operations <= 10_000
            or not 1 <= self.maximum_idle_cycles <= 10_000
            or self.maximum_runtime_seconds <= 0
            or self.shutdown_grace_seconds < 0
        ):
            raise ValueError("Worker limits are invalid")


@dataclass(frozen=True)
class WorkerHealth:
    healthy: bool
    last_successful_cycle: datetime | None
    active_claims: int
    backlog: int
    dead_letters: int
    reconciliation_required: int
