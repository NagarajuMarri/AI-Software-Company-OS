import os

import pytest

from runtime.tools.exceptions import WorkspaceSecurityError
from runtime.tools.workspace import LocalWorkspaceProvider


def test_workspace_creation_resolution_and_cleanup(tmp_path):
    provider = LocalWorkspaceProvider(tmp_path)
    workspace = provider.create_workspace("one")
    task = provider.allocate_task_directory("one", "task-1")
    assert task == workspace.local_path / "tasks" / "task-1"
    provider.clean_workspace("one")
    assert not workspace.local_path.exists()


def test_traversal_and_duplicate_workspace_are_rejected(tmp_path):
    provider = LocalWorkspaceProvider(tmp_path)
    provider.create_workspace("one")
    with pytest.raises(WorkspaceSecurityError):
        provider.resolve_path("one", "../../escape")
    with pytest.raises(FileExistsError):
        provider.create_workspace("one")


def test_symlink_escape_is_rejected_where_supported(tmp_path):
    provider = LocalWorkspaceProvider(tmp_path / "root")
    workspace = provider.create_workspace("one")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace.local_path / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    with pytest.raises(WorkspaceSecurityError):
        provider.resolve_path("one", "link/file")
