import subprocess

import pytest

from runtime.integrations.git.exceptions import (
    InvalidBranchNameError, ProtectedBranchError,
)
from runtime.integrations.git.local_provider import LocalGitProvider
from runtime.tools import LocalCommandRunner, LocalWorkspaceProvider


def setup_git(tmp_path):
    spaces = LocalWorkspaceProvider(tmp_path)
    workspace = spaces.create_workspace("git")
    runner = LocalCommandRunner(
        workspace.local_path, allowed_executables={"git"}
    )
    provider = LocalGitProvider(runner, spaces, "git")
    provider.initialize(workspace.local_path)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=workspace.local_path, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=workspace.local_path, check=True,
    )
    provider.create_branch(workspace.local_path, "agent/task")
    return provider, workspace.local_path


def test_git_branch_add_commit_and_status(tmp_path):
    provider, repository = setup_git(tmp_path)
    (repository / "change.txt").write_text("safe", encoding="utf-8")
    provider.add(repository, ["change.txt"])
    commit = provider.commit(repository, "Safe change")
    assert commit.branch == "agent/task"
    assert len(commit.sha) == 40 and provider.is_clean(repository)


def test_protected_branch_write_and_malicious_branch_rejected(tmp_path):
    provider, repository = setup_git(tmp_path)
    with pytest.raises(InvalidBranchNameError):
        provider.create_branch(repository, "bad;touch injected")
    with pytest.raises(ProtectedBranchError):
        provider.switch_branch(repository, "main")


def test_clone_requires_repository_allowlist(tmp_path):
    provider, repository = setup_git(tmp_path)
    with pytest.raises(Exception, match="allowed"):
        provider.clone("https://evil.invalid/repo.git", repository / "clone")
