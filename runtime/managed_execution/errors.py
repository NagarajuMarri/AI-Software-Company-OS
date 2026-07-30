"""Typed failures for the managed-product execution bridge."""

from runtime.exceptions import RuntimeDomainError


class ManagedExecutionError(RuntimeDomainError):
    pass


class ExecutionValidationError(ManagedExecutionError):
    pass


class ExecutionConflictError(ManagedExecutionError):
    pass


class ExecutionApprovalError(ManagedExecutionError):
    pass


class ExecutionPolicyError(ManagedExecutionError):
    pass


class ExecutionNotFoundError(ManagedExecutionError):
    pass


class ExecutionStorageError(ManagedExecutionError):
    pass


class ExecutionStateCorruptError(ManagedExecutionError):
    pass


class UnsupportedExecutionSchemaError(ManagedExecutionError):
    pass


class ExecutionReconciliationError(ExecutionConflictError):
    pass
