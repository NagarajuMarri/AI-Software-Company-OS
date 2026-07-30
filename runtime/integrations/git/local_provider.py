"""Local Git adapter built only on validated argument arrays."""

import re
from pathlib import Path

from runtime.integrations.git.exceptions import (
    GitProviderError,
    InvalidBranchNameError,
    InvalidRepositoryError,
    ProtectedBranchError,
)
from runtime.integrations.git.models import GitCommit, GitStatus
from runtime.tools.models import CommandRequest

_BRANCH = re.compile(
    r"^(?![-/.])(?!.*(?:\.\.|//|@\{|[~^:?*\[\\]))"
    r"(?!.*(?:/\.|\.lock(?:/|$)))[A-Za-z0-9._/-]{1,200}(?<![/.])$"
)


class LocalGitProvider:
    def __init__(
        self,
        command_runner,
        workspace_provider,
        workspace_id: str,
        *,
        protected_branches=("main", "master"),
        repository_url_policy=None,
    ) -> None:
        self.runner = command_runner
        self.workspaces = workspace_provider
        self.workspace_id = workspace_id
        self.protected_branches = frozenset(protected_branches)
        self.repository_url_policy = repository_url_policy or (lambda value: False)

    def initialize(self, repository_path) -> None:
        path = self._repo(repository_path, require_git=False)
        self._run(path, "init")

    def clone(self, repository_url: str, destination) -> None:
        if (
            not isinstance(repository_url, str)
            or repository_url.startswith("-")
            or "\0" in repository_url
            or not self.repository_url_policy(repository_url)
        ):
            raise InvalidRepositoryError("Repository URL is not allowed")
        try:
            relative_destination = Path(destination).resolve().relative_to(
                self.workspaces.inspect_workspace(
                    self.workspace_id
                ).local_path
            )
        except ValueError as error:
            raise InvalidRepositoryError(
                "Clone destination escapes workspace"
            ) from error
        destination = self.workspaces.resolve_path(
            self.workspace_id, str(relative_destination)
        )
        if destination.exists():
            raise InvalidRepositoryError("Clone destination already exists")
        if not destination.parent.is_dir():
            raise InvalidRepositoryError("Clone destination parent is missing")
        self._run(destination.parent, "clone", "--", repository_url, str(destination))

    def fetch(self, repository_path, remote="origin") -> None:
        self._run(self._repo(repository_path), "fetch", "--", remote)

    def status(self, repository_path) -> GitStatus:
        path = self._repo(repository_path)
        result = self._run(path, "status", "--porcelain")
        branch = self.current_branch(path)
        changed = tuple(line[3:] for line in result.stdout.splitlines())
        return GitStatus(branch, not changed, changed)

    def current_branch(self, repository_path) -> str:
        return self._run(
            self._repo(repository_path), "branch", "--show-current"
        ).stdout.strip()

    def current_commit(self, repository_path) -> str:
        return self._run(
            self._repo(repository_path), "rev-parse", "HEAD"
        ).stdout.strip()

    def branch_commit(self, repository_path, branch: str) -> str | None:
        self._branch(branch)
        result = self.runner.execute(CommandRequest(
            "git", ("rev-parse", "--verify", f"refs/heads/{branch}"),
            self._repo(repository_path)))
        return result.stdout.strip() if result.exit_code == 0 else None

    def remote_branch_commit(
        self, repository_path, remote: str, branch: str
    ) -> str | None:
        self._branch(branch)
        if not isinstance(remote, str) or not remote or remote.startswith("-"):
            raise GitProviderError("Invalid remote name")
        result = self.runner.execute(CommandRequest(
            "git", ("ls-remote", "--heads", remote, f"refs/heads/{branch}"),
            self._repo(repository_path)))
        if result.exit_code:
            raise GitProviderError("Could not inspect remote branch")
        line = result.stdout.strip()
        return line.split()[0] if line else None

    def commit_parent(self, repository_path, commit_sha: str) -> str:
        return self._revision(
            repository_path, f"{commit_sha}^", "commit parent")

    def commit_message(self, repository_path, commit_sha: str) -> str:
        return self._run(
            self._repo(repository_path), "show", "-s", "--format=%B",
            commit_sha).stdout.strip()

    def commit_changed_paths(
        self, repository_path, commit_sha: str
    ) -> tuple[str, ...]:
        output = self._run(
            self._repo(repository_path), "diff-tree", "--no-commit-id",
            "--name-only", "-r", commit_sha).stdout
        return tuple(line for line in output.splitlines() if line)

    def create_branch(self, repository_path, branch: str) -> None:
        self._branch(branch)
        self._run(self._repo(repository_path), "switch", "-c", branch)

    def switch_branch(
        self, repository_path, branch: str, *, allow_protected=False
    ) -> None:
        self._branch(branch)
        if branch in self.protected_branches and not allow_protected:
            raise ProtectedBranchError("Protected branch write is not allowed")
        self._run(self._repo(repository_path), "switch", branch)

    def add(self, repository_path, paths) -> None:
        if not paths:
            raise GitProviderError("At least one path is required")
        safe = []
        repository = self._repo(repository_path)
        for item in paths:
            resolved = (repository / item).resolve()
            if repository != resolved and repository not in resolved.parents:
                raise InvalidRepositoryError("Git path escapes repository")
            safe.append(str(item))
        self._require_writable_branch(repository)
        self._run(repository, "add", "--", *safe)

    def commit(self, repository_path, message: str) -> GitCommit:
        if (
            not isinstance(message, str)
            or not message.strip()
            or "\0" in message
            or len(message) > 500
        ):
            raise GitProviderError("Invalid commit message")
        repository = self._repo(repository_path)
        self._require_writable_branch(repository)
        self._run(repository, "commit", "-m", message)
        return GitCommit(self.current_commit(repository), self.current_branch(repository))

    def diff(self, repository_path, comparison=None) -> str:
        arguments = ("diff", "--no-ext-diff")
        if comparison:
            if not isinstance(comparison, str) or comparison.startswith("-"):
                raise GitProviderError("Invalid comparison reference")
            arguments += (comparison,)
        return self._run(self._repo(repository_path), *arguments).stdout

    def is_clean(self, repository_path) -> bool:
        return self.status(repository_path).clean

    def push(self, repository_path, remote, branch, *, credential_strategy=None):
        self._branch(branch)
        if branch in self.protected_branches:
            raise ProtectedBranchError("Protected branches cannot be pushed")
        if credential_strategy is not None:
            credential_strategy.prepare()
        try:
            self._run(self._repo(repository_path), "push", "--", remote, branch)
        finally:
            if credential_strategy is not None:
                credential_strategy.cleanup()

    def comparison_reference(self, repository_path, base, head) -> str:
        self._branch(base)
        self._branch(head)
        return f"{base}...{head}"

    def _run(self, path: Path, *arguments):
        result = self.runner.execute(
            CommandRequest("git", tuple(arguments), path)
        )
        if result.exit_code:
            raise GitProviderError(
                f"Git operation failed with exit code {result.exit_code}"
            )
        return result

    def _repo(self, path, *, require_git=True) -> Path:
        resolved = self.workspaces.validate_repository_location(
            self.workspace_id, path
        )
        if require_git and not (resolved / ".git").exists():
            raise InvalidRepositoryError("Path is not a Git repository")
        return resolved

    def _require_writable_branch(self, repository):
        if self.current_branch(repository) in self.protected_branches:
            raise ProtectedBranchError("Protected branch write is not allowed")

    @staticmethod
    def _branch(value):
        if not isinstance(value, str) or not _BRANCH.fullmatch(value):
            raise InvalidBranchNameError("Invalid Git branch name")

    def _revision(self, repository_path, value: str, description: str) -> str:
        if not isinstance(value, str) or value.startswith("-") or "\0" in value:
            raise GitProviderError(f"Invalid {description}")
        return self._run(
            self._repo(repository_path), "rev-parse", value).stdout.strip()
