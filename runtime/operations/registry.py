from runtime.operations.exceptions import (
    DuplicateOperationHandlerError, UnknownOperationHandlerError,
)


class OperationHandlerRegistry:
    def __init__(self): self._handlers = {}
    def register(self, handler):
        if handler.operation_type in self._handlers:
            raise DuplicateOperationHandlerError(handler.operation_type)
        self._handlers[handler.operation_type] = handler
        return handler
    def get(self, operation_type):
        try: return self._handlers[operation_type]
        except KeyError as error:
            raise UnknownOperationHandlerError(operation_type) from error
    def list(self): return tuple(self._handlers[key] for key in sorted(self._handlers))


DEFAULT_OPERATION_TYPES = (
    "ADD_PULL_REQUEST_COMMENT",
    "CANCEL_CODING_AGENT_TASK",
    "COMMIT_GIT_CHANGES",
    "CREATE_DRAFT_PULL_REQUEST",
    "CREATE_GIT_BRANCH",
    "FETCH_CI_STATUS",
    "PUSH_GIT_BRANCH",
    "SUBMIT_CODING_AGENT_TASK",
    "UPDATE_PULL_REQUEST",
)


def default_handler_registry():
    from runtime.operations.handlers import DeterministicOperationHandler

    registry = OperationHandlerRegistry()
    for operation_type in DEFAULT_OPERATION_TYPES:
        registry.register(DeterministicOperationHandler(operation_type))
    return registry
