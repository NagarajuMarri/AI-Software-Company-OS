"""Typed managed-product planning failures."""

from runtime.exceptions import RuntimeDomainError


class PlanningError(RuntimeDomainError):
    pass


class PlanningValidationError(PlanningError):
    pass


class PlanningNotFoundError(PlanningError):
    pass


class PlanningConflictError(PlanningError):
    pass


class PlanningProviderError(PlanningError):
    pass


class PlanningStateCorruptError(PlanningError):
    pass


class UnsupportedPlanningSchemaError(PlanningError):
    pass


class PlanningStorageError(PlanningError):
    pass


class KnowledgeStaleError(PlanningError):
    pass


class ProposalLifecycleError(PlanningError):
    pass
