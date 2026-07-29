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


class DuplicateProjectError(RuntimeDomainError):
    """Raised when a project identity or repository is already registered."""


class ProjectNotFoundError(RuntimeDomainError):
    """Raised when a managed project cannot be found."""


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


class ExecutorNotFoundError(RuntimeDomainError):
    """Raised when an executor cannot be found."""


class DuplicateExecutorError(RuntimeDomainError):
    """Raised when an executor identifier is already registered."""


class ExecutionNotFoundError(RuntimeDomainError):
    """Raised when an execution cannot be found."""


class DuplicateExecutionError(RuntimeDomainError):
    """Raised when an execution identifier already exists."""


class InvalidExecutionStateTransitionError(RuntimeDomainError):
    """Raised when an execution state change is not allowed."""


class ExecutionFailedError(RuntimeDomainError):
    """Raised after a failed execution has been recorded."""


class RecoveryNotFoundError(RuntimeDomainError):
    """Raised when a recovery record cannot be found."""


class DuplicateRecoveryError(RuntimeDomainError):
    """Raised when a recovery record identifier already exists."""


class InvalidRecoveryActionError(RuntimeDomainError):
    """Raised when a recovery action value is invalid."""


class ExecutionNotRecoverableError(RuntimeDomainError):
    """Raised when execution state does not permit recovery."""


class EventNotFoundError(RuntimeDomainError):
    """Raised when a runtime event cannot be found."""


class DuplicateEventError(RuntimeDomainError):
    """Raised when a runtime event identifier already exists."""


class InvalidEventTypeError(RuntimeDomainError):
    """Raised when an event type value is invalid."""


class EventPublicationError(RuntimeDomainError):
    """Raised when a runtime event cannot be persisted."""


class TransactionAlreadyCompletedError(RuntimeDomainError):
    """Raised when a completed transaction is reused."""


class NestedTransactionError(RuntimeDomainError):
    """Raised when an explicit transaction is nested."""


class TransactionCommitError(EventPublicationError):
    """Raised when an atomic transaction cannot commit."""


class TransactionRollbackError(RuntimeDomainError):
    """Raised when transaction state cannot be restored."""


class RuntimeCompositionError(RuntimeDomainError):
    """Raised when runtime container configuration is invalid."""


class WorkflowNotFoundError(RuntimeDomainError):
    """Raised when a software delivery workflow cannot be found."""


class DuplicateWorkflowError(RuntimeDomainError):
    """Raised when a workflow or request identifier already exists."""


class InvalidWorkflowTransitionError(RuntimeDomainError):
    """Raised when a workflow stage transition is not permitted."""


class WorkflowExecutionError(ExecutionFailedError):
    """Raised after a failed workflow execution has been recorded."""


class WorkflowApprovalError(RuntimeDomainError):
    """Raised when explicit approval requirements are not satisfied."""


class WorkflowReleaseError(RuntimeDomainError):
    """Raised when release requirements are not satisfied."""
