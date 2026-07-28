"""Safe external-tool failures."""


class ToolExecutionError(RuntimeError):
    pass


class InvalidCommandError(ToolExecutionError):
    pass


class CommandTimeoutError(ToolExecutionError):
    pass


class CommandCancelledError(ToolExecutionError):
    pass


class WorkspaceSecurityError(ToolExecutionError):
    pass


class WorkspaceNotFoundError(ToolExecutionError):
    pass
