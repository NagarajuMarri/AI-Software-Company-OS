from __future__ import annotations

from enum import Enum


class LifecycleState(str, Enum):
    """Enumeration of supported lifecycle states for runtime work items and artifacts."""

    CREATED = "CREATED"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    RELEASED = "RELEASED"
