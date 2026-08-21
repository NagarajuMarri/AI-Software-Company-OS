"""Errors for the governed Day 30 workforce orchestration layer."""


class WorkforceOrchestrationError(Exception):
    """Base error for Day 30 orchestration."""


class WorkforceOrchestrationPolicyError(WorkforceOrchestrationError):
    """An orchestration request violates an authority or source boundary."""


class WorkforceOrchestrationNotFound(WorkforceOrchestrationError):
    """A persisted orchestration artifact does not exist."""


class WorkforceOrchestrationConflict(WorkforceOrchestrationError):
    """Write-once orchestration state conflicts with an existing record."""


class WorkforceOrchestrationCorrupt(WorkforceOrchestrationError):
    """Persisted orchestration state is unsafe or corrupt."""
