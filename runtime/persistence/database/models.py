"""Database persistence value models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RuntimeLease:
    runtime_id: str
    owner_id: str
    lease_token: str
    acquired_at: datetime
    renewed_at: datetime
    expires_at: datetime
    fencing_token: int


@dataclass(frozen=True)
class RuntimeInstance:
    runtime_id: str
    schema_version: int
    current_state_version: int
    latest_checkpoint_id: str | None
    latest_event_position: int
    durability_status: str
    created_at: datetime
    updated_at: datetime
