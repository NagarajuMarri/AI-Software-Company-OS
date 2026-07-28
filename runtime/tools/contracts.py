"""Provider-neutral external-tool contracts."""

from typing import Protocol, runtime_checkable

from runtime.tools.models import CommandRequest, CommandResult, Workspace


@runtime_checkable
class CommandRunner(Protocol):
    def execute(self, request: CommandRequest, *, cancellation=None) -> CommandResult:
        ...


@runtime_checkable
class WorkspaceProvider(Protocol):
    def create_workspace(self, workspace_id: str) -> Workspace:
        ...

    def resolve_path(self, workspace_id: str, relative_path: str = ""):
        ...
