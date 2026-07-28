from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WorkerHealth:
    healthy: bool
    last_successful_cycle: datetime | None
    active_claims: int
    backlog: int
    dead_letters: int
    reconciliation_required: int
