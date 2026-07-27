"""Domain-specific exceptions raised by the runtime."""


class RuntimeDomainError(Exception):
    """Base class for runtime domain failures."""


class ValidationError(RuntimeDomainError):
    """Raised when a runtime model contains invalid data."""


class DuplicateWorkPackageError(RuntimeDomainError):
    """Raised when a work package identifier is already registered."""


class DuplicateWorkItemError(RuntimeDomainError):
    """Raised when a work item identifier already exists in a package."""


class DuplicateArtifactError(RuntimeDomainError):
    """Raised when an artifact identifier is already registered or attached."""


class WorkPackageNotFoundError(RuntimeDomainError):
    """Raised when a work package cannot be found."""


class WorkItemNotFoundError(RuntimeDomainError):
    """Raised when a work item cannot be found."""


class ArtifactNotFoundError(RuntimeDomainError):
    """Raised when an artifact cannot be found."""


class InvalidLifecycleTransitionError(RuntimeDomainError):
    """Raised when a lifecycle state change is not allowed."""


class DuplicateAgentError(RuntimeDomainError):
    """Raised when an agent identifier is already registered."""


class AgentNotFoundError(RuntimeDomainError):
    """Raised when an agent cannot be found."""


class InvalidAgentStateTransitionError(RuntimeDomainError):
    """Raised when an agent state change is not allowed."""


class AssignmentNotFoundError(RuntimeDomainError):
    """Raised when an assignment cannot be found."""


class DuplicateActiveAssignmentError(RuntimeDomainError):
    """Raised when a work item already has an active assignment."""


class NoEligibleAgentError(RuntimeDomainError):
    """Raised when no agent satisfies assignment requirements."""


class InvalidAssignmentStateTransitionError(RuntimeDomainError):
    """Raised when an assignment state change is not allowed."""


class AgentCapacityError(RuntimeDomainError):
    """Raised when matching agents have no remaining task capacity."""
