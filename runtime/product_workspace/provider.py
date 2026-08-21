"""Specialized no-network Git worktree provider for ASCOS Day 31."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
from typing import Protocol

from runtime.product_workspace.errors import (
    ProductWorkspacePolicyError,
    ProductWorkspaceReconciliationRequired,
)
from runtime.product_workspace.models import (
    ProductWorkspaceAuthority,
    ProductWorkspaceWorkOrder,
    WorkspacePreparationObservation,
)


class ProductWorkspaceProvider(Protocol):
    """Prepare one exact-base isolated workspace through a bounded adapter."""

    provider_id: str

    def prepare(
        self,
        source_repository: Path,
        work_order: ProductWorkspaceWorkOrder,
        authority: ProductWorkspaceAuthority,
    ) -> WorkspacePreparationObservation: ...


class LocalGitWorktreeProvider:
    """Create one local linked worktree without network or general shell access."""

    provider_id = "local-git-worktree-v1"

    def __init__(self, workspace_root: Path, *, git_executable: str = "git") -> None:
        if not isinstance(workspace_root, Path):
            raise TypeError("Product workspace root must be a Path")
        if git_executable != "git":
            raise ProductWorkspacePolicyError("Only the configured Git executable is supported")
        self._root = workspace_root.absolute()
        self._git = git_executable
        self.execution_count = 0
        self.command_count = 0

    @property
    def root(self) -> Path:
        return self._root

    def prepare(
        self,
        source_repository: Path,
        work_order: ProductWorkspaceWorkOrder,
        authority: ProductWorkspaceAuthority,
    ) -> WorkspacePreparationObservation:
        if not isinstance(source_repository, Path):
            raise ProductWorkspacePolicyError("Product source repository must be a Path")
        self.execution_count += 1
        self.command_count = 0
        self._prepare_root()
        source = source_repository.absolute()
        self._require_real_directory(source, "source repository")
        if source.resolve() != source:
            raise ProductWorkspacePolicyError("Product source path contains a symbolic link")
        target = self._root / work_order.workspace_id
        if target.parent != self._root or os.path.lexists(target):
            raise ProductWorkspaceReconciliationRequired(
                "Product workspace destination already exists or is unsafe"
            )

        top = self._run(source, ("rev-parse", "--show-toplevel")).strip()
        if Path(top).resolve() != source:
            raise ProductWorkspacePolicyError("Product source is not the exact repository root")
        unsafe_config = self._run(
            source,
            (
                "config",
                "--local",
                "--name-only",
                "--get-regexp",
                r"^(filter\.|core\.hooksPath$|core\.fsmonitor$|credential\.|url\.)",
            ),
            allowed_returncodes=(0, 1),
        ).strip()
        if unsafe_config:
            raise ProductWorkspacePolicyError(
                "Product repository has executable, credential, or URL-rewrite Git configuration"
            )
        status_before = self._run(
            source, ("status", "--porcelain=v1", "--untracked-files=all")
        )
        branch_before = self._run(source, ("branch", "--show-current")).strip()
        head_before = self._run(source, ("rev-parse", "HEAD")).strip()
        tree_before = self._run(source, ("rev-parse", "HEAD^{tree}")).strip()
        remote_identity = self._run(source, ("remote", "get-url", "origin")).strip()
        base_commit = self._run(
            source, ("rev-parse", "--verify", f"refs/heads/{work_order.base_branch}^{{commit}}")
        ).strip()
        branch_exists = self._run(
            source,
            ("show-ref", "--verify", "--quiet", f"refs/heads/{work_order.feature_branch}"),
            allowed_returncodes=(0, 1),
            include_returncode=True,
        )
        tree_listing = self._run(
            source,
            ("ls-tree", "-r", "-z", "--full-tree", work_order.expected_base_commit),
        )

        if status_before:
            raise ProductWorkspacePolicyError("Product source repository is not clean")
        if branch_before != work_order.base_branch:
            raise ProductWorkspacePolicyError("Product source is not on the approved base branch")
        if head_before != work_order.expected_base_commit or base_commit != head_before:
            raise ProductWorkspacePolicyError("Product source does not match the approved base commit")
        if remote_identity != work_order.repository_identity:
            raise ProductWorkspacePolicyError("Product repository identity does not match")
        if branch_exists != "1":
            raise ProductWorkspaceReconciliationRequired(
                "Product feature branch already exists and will not be reset"
            )
        self._validate_tree(tree_listing)

        try:
            self._run(
                source,
                (
                    "worktree",
                    "add",
                    "-b",
                    work_order.feature_branch,
                    str(target),
                    work_order.expected_base_commit,
                ),
            )
        except ProductWorkspacePolicyError as error:
            if os.path.lexists(target):
                raise ProductWorkspaceReconciliationRequired(
                    "Product workspace creation left an uncertain destination"
                ) from error
            raise

        self._require_real_directory(target, "created product workspace")
        workspace_status = self._run(
            target, ("status", "--porcelain=v1", "--untracked-files=all")
        )
        workspace_branch = self._run(target, ("branch", "--show-current")).strip()
        workspace_head = self._run(target, ("rev-parse", "HEAD")).strip()
        workspace_tree = self._run(target, ("rev-parse", "HEAD^{tree}")).strip()
        status_after = self._run(
            source, ("status", "--porcelain=v1", "--untracked-files=all")
        )
        branch_after = self._run(source, ("branch", "--show-current")).strip()
        head_after = self._run(source, ("rev-parse", "HEAD")).strip()
        tree_after = self._run(source, ("rev-parse", "HEAD^{tree}")).strip()

        if not (
            workspace_status == ""
            and workspace_branch == work_order.feature_branch
            and workspace_head == head_before
            and workspace_tree == tree_before
            and status_after == ""
            and branch_after == branch_before
            and head_after == head_before
            and tree_after == tree_before
        ):
            raise ProductWorkspaceReconciliationRequired(
                "Product workspace or approved source diverged during preparation"
            )
        if self.command_count > authority.max_tool_calls:
            raise ProductWorkspaceReconciliationRequired(
                "Product workspace Git operation budget was exceeded"
            )
        return WorkspacePreparationObservation(
            provider_id=self.provider_id,
            workspace_relative_path=work_order.workspace_id,
            source_branch_before=branch_before,
            source_branch_after=branch_after,
            source_head_before=head_before,
            source_head_after=head_after,
            source_tree_before=tree_before,
            source_tree_after=tree_after,
            workspace_branch=workspace_branch,
            workspace_head=workspace_head,
            workspace_tree=workspace_tree,
            source_clean_before=True,
            source_clean_after=True,
            workspace_clean=True,
            branch_created=True,
            workspace_created=True,
            git_command_count=self.command_count,
            network_call_count=0,
            general_command_count=0,
            product_file_write_count=0,
            unrelated_path_change_count=0,
        )

    def _prepare_root(self) -> None:
        if os.path.lexists(self._root) and self._root.is_symlink():
            raise ProductWorkspacePolicyError("Product workspace root cannot be a symbolic link")
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._require_real_directory(self._root, "workspace root")
        if self._root.resolve() != self._root:
            raise ProductWorkspacePolicyError("Product workspace root contains a symbolic link")

    @staticmethod
    def _require_real_directory(path: Path, label: str) -> None:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise ProductWorkspacePolicyError(f"Product {label} does not exist") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise ProductWorkspacePolicyError(f"Product {label} is unsafe")

    @staticmethod
    def _validate_tree(listing: str) -> None:
        records = tuple(item for item in listing.split("\0") if item)
        if not records:
            raise ProductWorkspacePolicyError("Product source tree is empty")
        for record in records:
            try:
                metadata, path = record.split("\t", 1)
                mode, kind, _sha = metadata.split(" ", 2)
            except ValueError as error:
                raise ProductWorkspacePolicyError("Product source tree is malformed") from error
            if mode in {"120000", "160000"} or kind != "blob":
                raise ProductWorkspacePolicyError(
                    "Product source tree contains a symlink, submodule, or special entry"
                )
            if path == ".git" or path.startswith(".git/"):
                raise ProductWorkspacePolicyError("Product source tree contains protected metadata")

    def _run(
        self,
        cwd: Path,
        arguments: tuple[str, ...],
        *,
        allowed_returncodes: tuple[int, ...] = (0,),
        include_returncode: bool = False,
    ) -> str:
        command = (
            self._git,
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "credential.helper=",
            *arguments,
        )
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "LC_ALL": "C.UTF-8",
        }
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            check=False,
        )
        self.command_count += 1
        if result.returncode not in allowed_returncodes:
            raise ProductWorkspacePolicyError("Bounded local Git operation failed")
        if len(result.stdout.encode()) > 2_000_000:
            raise ProductWorkspacePolicyError("Bounded local Git output exceeded its limit")
        if include_returncode:
            return str(result.returncode)
        return result.stdout
