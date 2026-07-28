from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re


class ProviderHealthStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"
    DISABLED = "DISABLED"


@dataclass
class ProviderHealthState:
    provider_id: str
    capability: str
    status: ProviderHealthStatus
    consecutive_successes: int
    consecutive_failures: int
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_failure_category: str | None
    last_failure_code: str | None
    open_until: datetime | None
    half_open_probe_count: int
    current_in_flight: int
    maximum_in_flight: int
    updated_at: datetime
    version: int = 0
    operator_disabled: bool = False

    def __post_init__(self):
        safe = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
        if not safe.fullmatch(self.provider_id) or not safe.fullmatch(self.capability):
            raise ValueError("Invalid provider identity")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("Provider timestamps must be timezone-aware")
        counters = (
            self.consecutive_successes, self.consecutive_failures,
            self.half_open_probe_count, self.current_in_flight,
        )
        if any(value < 0 for value in counters) or self.maximum_in_flight < 1:
            raise ValueError("Invalid provider health counters")
