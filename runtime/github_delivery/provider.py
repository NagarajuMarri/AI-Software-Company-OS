"""Specialized commit, push, and draft-PR provider for ASCOS Day 33."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
from typing import Protocol

from runtime.github_delivery.errors import (
    GitHubDeliveryPolicyError,
    GitHubDeliveryReconciliationRequired,
)
from runtime.github_delivery.models import (
    DraftPullRequestReceipt,
    GitHubDeliveryAuthority,
    GitHubDeliveryObservation,
    GitHubDeliveryWorkOrder,
)


class DraftPullRequestGateway(Protocol):
    """A scoped GitHub gateway that can query and create draft PRs only."""

    def find(
        self,
        *,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
    ) -> DraftPullRequestReceipt | None: ...

    def create(
        self,
        *,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
        base_commit: str,
        head_commit: str,
        title: str,
        body: str,
        body_digest: str,
        draft: bool,
    ) -> DraftPullRequestReceipt: ...


class DeterministicDraftPullRequestGateway:
    """Closed generic-fixture gateway used for exact runtime verification."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], DraftPullRequestReceipt] = {}
        self.query_count = 0
        self.create_count = 0

    def find(
        self,
        *,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
    ) -> DraftPullRequestReceipt | None:
        self.query_count += 1
        return self._records.get((repository_full_name, base_branch, head_branch))

    def create(
        self,
        *,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
        base_commit: str,
        head_commit: str,
        title: str,
        body: str,
        body_digest: str,
        draft: bool,
    ) -> DraftPullRequestReceipt:
        del body
        if not draft:
            raise GitHubDeliveryPolicyError("Only a draft pull request may be created")
        key = (repository_full_name, base_branch, head_branch)
        if key in self._records:
            raise GitHubDeliveryReconciliationRequired("A matching pull request already exists")
        self.create_count += 1
        receipt = DraftPullRequestReceipt(
            number=self.create_count,
            url=f"https://github.com/{repository_full_name}/pull/{self.create_count}",
            repository_full_name=repository_full_name,
            base_branch=base_branch,
            head_branch=head_branch,
            base_commit=base_commit,
            head_commit=head_commit,
            title=title,
            body_digest=body_digest,
            draft=True,
            state="OPEN",
            merged=False,
        )
        self._records[key] = receipt
        return receipt

    def seed(self, receipt: DraftPullRequestReceipt) -> None:
        key = (receipt.repository_full_name, receipt.base_branch, receipt.head_branch)
        self._records[key] = receipt


class GitHubDeliveryProvider(Protocol):
    """Deliver one exact reviewed workspace through bounded Git and GitHub tools."""

    provider_id: str

    def deliver(
        self,
        workspace: Path,
        work_order: GitHubDeliveryWorkOrder,
        authority: GitHubDeliveryAuthority,
    ) -> GitHubDeliveryObservation: ...


class ControlledGitHubDeliveryProvider:
    """Perform one reviewed commit, non-force push, and draft-PR creation."""

    provider_id = "controlled-github-delivery-v1"

    def __init__(
        self,
        gateway: DraftPullRequestGateway,
        *,
        push_remote: str | Path = "origin",
        git_executable: str = "git",
    ) -> None:
        if git_executable != "git":
            raise GitHubDeliveryPolicyError("Only the configured Git executable is supported")
        if not callable(getattr(gateway, "find", None)) or not callable(
            getattr(gateway, "create", None)
        ):
            raise TypeError("Draft pull-request gateway is invalid")
        self._push_remote: str | Path
        if isinstance(push_remote, str):
            if push_remote != "origin":
                raise GitHubDeliveryPolicyError("Named delivery remote must be origin")
            self._push_remote = push_remote
        elif isinstance(push_remote, Path):
            self._push_remote = push_remote.absolute()
        else:
            raise TypeError("Delivery push remote is invalid")
        self._gateway = gateway
        self._git = git_executable
        self.execution_count = 0
        self.command_count = 0
        self.controlled_network_call_count = 0

    def deliver(
        self,
        workspace: Path,
        work_order: GitHubDeliveryWorkOrder,
        authority: GitHubDeliveryAuthority,
    ) -> GitHubDeliveryObservation:
        if not isinstance(workspace, Path):
            raise GitHubDeliveryPolicyError("Delivery workspace must be a Path")
        if not isinstance(work_order, GitHubDeliveryWorkOrder) or not isinstance(
            authority, GitHubDeliveryAuthority
        ):
            raise GitHubDeliveryPolicyError("Delivery request is invalid")
        self.execution_count += 1
        self.command_count = 0
        self.controlled_network_call_count = 0
        root = workspace.absolute()
        self._require_real_directory(root)
        if root.resolve() != root:
            raise GitHubDeliveryPolicyError("Delivery workspace path contains a symbolic link")
        self._validate_transport()

        remote_before = self._remote_head(root, work_order.feature_branch)
        if remote_before is not None:
            raise GitHubDeliveryReconciliationRequired(
                "The product feature branch already exists remotely"
            )
        existing = self._gateway.find(
            repository_full_name=work_order.repository_full_name,
            base_branch=work_order.base_branch,
            head_branch=work_order.feature_branch,
        )
        self.controlled_network_call_count += 1
        if existing is not None:
            raise GitHubDeliveryReconciliationRequired(
                "A matching product pull request already exists"
            )

        mutation_started = False
        committed = False
        pushed = False
        try:
            mutation_started = True
            self._run(root, ("add", "--", *work_order.reviewed_paths))
            staged = self._zpaths(
                self._run(root, ("diff", "--cached", "--name-only", "-z"))
            )
            if staged != work_order.reviewed_paths:
                raise GitHubDeliveryReconciliationRequired(
                    "The Git index does not contain the exact reviewed paths"
                )
            self._run(
                root,
                (
                    "-c",
                    "user.name=ASCOS Controlled Delivery",
                    "-c",
                    "user.email=delivery@ascos.invalid",
                    "commit",
                    "--no-gpg-sign",
                    "--no-verify",
                    "-m",
                    work_order.commit_message,
                ),
            )
            committed = True
            commit_sha = self._run(root, ("rev-parse", "HEAD")).strip()
            commit_parent = self._run(root, ("rev-parse", "HEAD^" )).strip()
            commit_tree = self._run(root, ("rev-parse", "HEAD^{tree}")).strip()
            committed_paths = self._zpaths(
                self._run(
                    root,
                    ("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD"),
                )
            )
            if commit_parent != work_order.base_commit or committed_paths != staged:
                raise GitHubDeliveryReconciliationRequired(
                    "The created commit is not the exact reviewed single-parent commit"
                )

            ref = f"refs/heads/{work_order.feature_branch}"
            self._run(
                root,
                ("push", "--porcelain", self._remote_argument(), f"{ref}:{ref}"),
                network=True,
            )
            pushed = True
            remote_after = self._remote_head(root, work_order.feature_branch)
            if remote_after != commit_sha:
                raise GitHubDeliveryReconciliationRequired(
                    "The remote feature branch does not match the reviewed commit"
                )
            receipt = self._gateway.create(
                repository_full_name=work_order.repository_full_name,
                base_branch=work_order.base_branch,
                head_branch=work_order.feature_branch,
                base_commit=work_order.base_commit,
                head_commit=commit_sha,
                title=work_order.pull_request_title,
                body=work_order.pull_request_body,
                body_digest=work_order.pull_request_body_digest,
                draft=True,
            )
            self.controlled_network_call_count += 1
        except GitHubDeliveryReconciliationRequired:
            raise
        except Exception as error:
            if mutation_started or committed or pushed:
                raise GitHubDeliveryReconciliationRequired(
                    "Controlled delivery stopped after a repository effect"
                ) from error
            if isinstance(error, GitHubDeliveryPolicyError):
                raise
            raise GitHubDeliveryPolicyError("Controlled delivery failed before mutation") from error

        if self.command_count > authority.max_git_commands:
            raise GitHubDeliveryReconciliationRequired("Delivery Git-command budget was exceeded")
        if self.controlled_network_call_count > authority.max_controlled_network_calls:
            raise GitHubDeliveryReconciliationRequired(
                "Delivery controlled-network budget was exceeded"
            )
        return GitHubDeliveryObservation(
            provider_id=self.provider_id,
            staged_paths=staged,
            committed_paths=committed_paths,
            commit_parent=commit_parent,
            commit_sha=commit_sha,
            commit_tree=commit_tree,
            remote_branch_sha=remote_after,
            pull_request=receipt,
            git_command_count=self.command_count,
            controlled_network_call_count=self.controlled_network_call_count,
            credential_handle_count=0,
            secret_value_exposure_count=0,
            unapproved_network_call_count=0,
            unrelated_path_count=0,
            general_command_count=0,
            force_push_count=0,
            commit_count=1,
            push_count=1,
            pull_request_count=1,
            merge_count=0,
            deployment_count=0,
            release_count=0,
        )

    def _validate_transport(self) -> None:
        if isinstance(self._push_remote, Path):
            self._require_real_directory(self._push_remote)

    def _remote_argument(self) -> str:
        return str(self._push_remote)

    def _remote_head(self, workspace: Path, branch: str) -> str | None:
        ref = f"refs/heads/{branch}"
        output = self._run(
            workspace,
            ("ls-remote", "--heads", self._remote_argument(), ref),
            network=True,
        ).strip()
        if not output:
            return None
        records = output.splitlines()
        if len(records) != 1:
            raise GitHubDeliveryReconciliationRequired("Remote branch lookup is ambiguous")
        try:
            sha, observed_ref = records[0].split("\t", 1)
        except ValueError as error:
            raise GitHubDeliveryReconciliationRequired("Remote branch response is malformed") from error
        if observed_ref != ref:
            raise GitHubDeliveryReconciliationRequired("Remote branch response is mismatched")
        return sha

    def _run(
        self,
        cwd: Path,
        arguments: tuple[str, ...],
        *,
        network: bool = False,
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
        if network:
            self.controlled_network_call_count += 1
        if result.returncode != 0 or len(result.stdout.encode()) > 2_000_000:
            if network:
                raise GitHubDeliveryReconciliationRequired(
                    "A controlled remote Git operation failed"
                )
            raise GitHubDeliveryPolicyError("A bounded local Git operation failed")
        return result.stdout

    @staticmethod
    def _zpaths(output: str) -> tuple[str, ...]:
        values = tuple(item for item in output.split("\0") if item)
        if len(values) != len(set(values)):
            raise GitHubDeliveryReconciliationRequired("Git returned duplicate paths")
        return tuple(sorted(values))

    @staticmethod
    def _require_real_directory(path: Path) -> None:
        try:
            details = path.lstat()
        except FileNotFoundError as error:
            raise GitHubDeliveryPolicyError("Delivery directory does not exist") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise GitHubDeliveryPolicyError("Delivery directory is unsafe")
