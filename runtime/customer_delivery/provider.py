"""Closed Git/GitHub adapter for one reviewed commit, push, and draft PR."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Protocol
from urllib.parse import urlparse

from runtime.customer_delivery.errors import (
    CustomerDeliveryConflict,
    CustomerDeliveryPolicyError,
)
from runtime.customer_delivery.models import (
    CustomerDeliveryConfiguration,
    CustomerDeliveryReview,
    CustomerDeliveryStatus,
    ReviewedFile,
)


@dataclass(frozen=True)
class DraftPullRequest:
    number: int
    url: str
    repository_full_name: str
    base_branch: str
    head_branch: str
    title: str
    draft: bool
    state: str


@dataclass(frozen=True)
class CustomerDeliveryOutcome:
    commit_sha: str
    tree_sha: str
    pull_request_number: int
    pull_request_url: str


class DraftPullRequestGateway(Protocol):
    def list_for_head(
        self,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
    ) -> tuple[DraftPullRequest, ...]: ...

    def create_draft(
        self,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
        title: str,
        body: str,
    ) -> DraftPullRequest: ...


class CustomerDeliveryAdapter(Protocol):
    def preflight(self, review: CustomerDeliveryReview) -> None: ...

    def deliver(self, review: CustomerDeliveryReview) -> CustomerDeliveryOutcome: ...


class GitHubCliDraftPullRequestGateway:
    """Use an existing GitHub CLI login without accepting a browser credential."""

    def __init__(self, executable: str = "gh") -> None:
        self._executable = executable

    def list_for_head(
        self,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
    ) -> tuple[DraftPullRequest, ...]:
        values = self._json(
            "pr",
            "list",
            "--repo",
            repository_full_name,
            "--base",
            base_branch,
            "--head",
            head_branch,
            "--state",
            "all",
            "--limit",
            "100",
            "--json",
            "number,url,isDraft,state,baseRefName,headRefName,title",
        )
        if not isinstance(values, list):
            raise CustomerDeliveryPolicyError("GitHub returned an invalid pull-request list")
        return tuple(self._pull_request(repository_full_name, value) for value in values)

    def create_draft(
        self,
        repository_full_name: str,
        base_branch: str,
        head_branch: str,
        title: str,
        body: str,
    ) -> DraftPullRequest:
        result = self._run(
            "pr",
            "create",
            "--repo",
            repository_full_name,
            "--base",
            base_branch,
            "--head",
            head_branch,
            "--draft",
            "--title",
            title,
            "--body-file",
            "-",
            input_text=body,
        )
        url = result.stdout.strip()
        if not url.startswith(f"https://github.com/{repository_full_name}/pull/"):
            raise CustomerDeliveryPolicyError("GitHub returned an invalid draft-PR URL")
        try:
            number = int(url.rstrip("/").rsplit("/", 1)[1])
        except (IndexError, ValueError):
            raise CustomerDeliveryPolicyError("GitHub returned an invalid draft-PR number") from None
        matches = self.list_for_head(repository_full_name, base_branch, head_branch)
        selected = tuple(value for value in matches if value.number == number)
        if len(selected) != 1:
            raise CustomerDeliveryPolicyError("Created draft PR could not be verified")
        return selected[0]

    def _json(self, *arguments: str) -> object:
        try:
            return json.loads(self._run(*arguments).stdout)
        except json.JSONDecodeError as error:
            raise CustomerDeliveryPolicyError("GitHub returned invalid JSON") from error

    def _run(self, *arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        if shutil.which(self._executable) is None:
            raise CustomerDeliveryPolicyError("GitHub CLI is unavailable")
        result = subprocess.run(
            (self._executable, *arguments),
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
            timeout=60,
        )
        if result.returncode:
            raise CustomerDeliveryPolicyError("GitHub draft-PR operation failed")
        return result

    @staticmethod
    def _pull_request(repository: str, value: object) -> DraftPullRequest:
        if not isinstance(value, dict):
            raise CustomerDeliveryPolicyError("GitHub pull-request record is invalid")
        expected = {
            "number",
            "url",
            "isDraft",
            "state",
            "baseRefName",
            "headRefName",
            "title",
        }
        if set(value) != expected:
            raise CustomerDeliveryPolicyError("GitHub pull-request fields are invalid")
        return DraftPullRequest(
            value["number"],
            value["url"],
            repository,
            value["baseRefName"],
            value["headRefName"],
            value["title"],
            value["isDraft"],
            str(value["state"]).upper(),
        )


class ControlledCustomerDeliveryAdapter:
    """Perform the exact reviewed delivery without shell or merge authority."""

    def __init__(
        self,
        configuration: CustomerDeliveryConfiguration,
        gateway: DraftPullRequestGateway,
        *,
        expected_remote_url: str | None = None,
    ) -> None:
        self._configuration = configuration
        self._gateway = gateway
        self._expected_remote_url = expected_remote_url or (
            f"https://github.com/{configuration.repository_full_name}.git"
        )

    def preflight(self, review: CustomerDeliveryReview) -> None:
        if review.status not in {
            CustomerDeliveryStatus.REVIEW_APPROVED,
            CustomerDeliveryStatus.DELIVERY_IN_PROGRESS,
        }:
            raise CustomerDeliveryConflict("Exact human review is not approved")
        self._require_binding(review)
        self._verify_workspace(review)
        remote = self._git("remote", "get-url", "--push", self._configuration.remote_name).strip()
        if _normalize_remote(remote) != _normalize_remote(self._expected_remote_url):
            raise CustomerDeliveryPolicyError("Git push remote differs from operator authority")
        branch_ref = f"refs/heads/{review.workspace_branch}"
        if self._git("ls-remote", "--heads", self._configuration.remote_name, branch_ref).strip():
            raise CustomerDeliveryConflict("Remote delivery branch already exists")
        if self._gateway.list_for_head(
            review.repository_full_name,
            review.base_branch,
            review.workspace_branch,
        ):
            raise CustomerDeliveryConflict("A pull request already exists for this delivery")

    def deliver(self, review: CustomerDeliveryReview) -> CustomerDeliveryOutcome:
        self.preflight(review)
        paths = tuple(item.path for item in review.reviewed_files)
        self._git("add", "--", *paths)
        staged = tuple(
            sorted(
                value
                for value in self._git("diff", "--cached", "--name-only", "--").splitlines()
                if value
            )
        )
        if staged != tuple(sorted(paths)):
            raise CustomerDeliveryPolicyError("Git index differs from reviewed paths")
        self._git(
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--no-gpg-sign",
            "-m",
            review.commit_message,
        )
        commit_sha = self._git("rev-parse", "HEAD").strip()
        parent_sha = self._git("rev-parse", "HEAD^").strip()
        tree_sha = self._git("rev-parse", "HEAD^{tree}").strip()
        committed = tuple(
            sorted(
                value
                for value in self._git(
                    "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"
                ).splitlines()
                if value
            )
        )
        if parent_sha != review.workspace_commit_before_turn or committed != tuple(sorted(paths)):
            raise CustomerDeliveryPolicyError("Created commit differs from reviewed intent")
        self._git(
            "push",
            "--porcelain",
            self._configuration.remote_name,
            f"HEAD:refs/heads/{review.workspace_branch}",
        )
        remote = self._git(
            "ls-remote",
            "--heads",
            self._configuration.remote_name,
            f"refs/heads/{review.workspace_branch}",
        ).strip()
        remote_sha = remote.split(maxsplit=1)[0] if remote else ""
        if remote_sha != commit_sha:
            raise CustomerDeliveryPolicyError("Remote branch differs from reviewed commit")
        pull_request = self._gateway.create_draft(
            review.repository_full_name,
            review.base_branch,
            review.workspace_branch,
            review.pull_request_title,
            review.pull_request_body,
        )
        if (
            pull_request.repository_full_name != review.repository_full_name
            or pull_request.base_branch != review.base_branch
            or pull_request.head_branch != review.workspace_branch
            or pull_request.title != review.pull_request_title
            or not pull_request.draft
            or pull_request.state != "OPEN"
        ):
            raise CustomerDeliveryPolicyError("Draft PR differs from reviewed authority")
        if self._git("status", "--porcelain=v1", "--untracked-files=all").strip():
            raise CustomerDeliveryPolicyError("Delivered workspace is not clean")
        return CustomerDeliveryOutcome(
            commit_sha,
            tree_sha,
            pull_request.number,
            pull_request.url,
        )

    def _require_binding(self, review: CustomerDeliveryReview) -> None:
        if (
            review.repository_full_name != self._configuration.repository_full_name
            or review.base_branch != self._configuration.base_branch
        ):
            raise CustomerDeliveryPolicyError("Delivery target differs from operator authority")

    def _verify_workspace(self, review: CustomerDeliveryReview) -> None:
        if self._git("branch", "--show-current").strip() != review.workspace_branch:
            raise CustomerDeliveryPolicyError("Delivery workspace branch changed")
        if self._git("rev-parse", "HEAD").strip() != review.workspace_commit_before_turn:
            raise CustomerDeliveryPolicyError("Delivery workspace commit changed")
        changed = tuple(
            sorted(
                line[3:]
                for line in self._git(
                    "status", "--porcelain=v1", "--untracked-files=all"
                ).splitlines()
                if len(line) > 3
            )
        )
        if changed != tuple(sorted(item.path for item in review.reviewed_files)):
            raise CustomerDeliveryPolicyError("Delivery workspace paths changed after review")
        for item in review.reviewed_files:
            path = self._configuration.workspace_root / item.path
            if not path.is_file() or path.is_symlink():
                raise CustomerDeliveryPolicyError("Reviewed file is missing or unsafe")
            import hashlib

            if hashlib.sha256(path.read_bytes()).hexdigest() != item.content_digest:
                raise CustomerDeliveryPolicyError("Reviewed file content changed")
        diff = canonical_review_patch(
            self._configuration.workspace_root,
            review.reviewed_files,
        )
        import hashlib

        if hashlib.sha256(diff.encode("utf-8")).hexdigest() != review.git_diff_digest:
            raise CustomerDeliveryPolicyError("Reviewed Git diff changed")

    def _git(self, *arguments: str) -> str:
        environment = dict(os.environ)
        for name in (
            "OPENAI_API_KEY",
            "CODEX_API_KEY",
            "CODEX_ACCESS_TOKEN",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0",
        ):
            environment.pop(name, None)
        environment["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            (
                "git",
                "-c",
                f"core.hooksPath={os.devnull}",
                "-c",
                "commit.gpgsign=false",
                *arguments,
            ),
            cwd=self._configuration.workspace_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            raise CustomerDeliveryPolicyError("Controlled Git operation failed")
        return result.stdout


def _normalize_remote(value: str) -> str:
    if value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username:
            raise CustomerDeliveryPolicyError("Delivery requires credential-free GitHub HTTPS URL")
        return value.rstrip("/").removesuffix(".git").casefold()
    return str(Path(value).resolve())


def canonical_review_patch(workspace: Path, files: tuple[ReviewedFile, ...]) -> str:
    """Render a stable escaped-review source including Git-untracked new files."""

    paths = tuple(item.path for item in files)
    tracked_diff = _standalone_git(
        workspace,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--",
        *paths,
    )
    sections = [tracked_diff] if tracked_diff else []
    for item in files:
        tracked = subprocess.run(
            ("git", "ls-files", "--error-unmatch", "--", item.path),
            cwd=workspace,
            env=_git_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if tracked.returncode == 0:
            continue
        if tracked.returncode not in {1, 128}:
            raise CustomerDeliveryPolicyError("Could not classify a reviewed Git path")
        try:
            content = (workspace / item.path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise CustomerDeliveryPolicyError("Reviewed patch file is not bounded UTF-8 text") from error
        lines = "".join(f"+{line}" for line in content.splitlines(keepends=True))
        if content and not content.endswith(("\n", "\r")):
            lines += "\n\\ No newline at end of file\n"
        sections.append(
            f"diff --ascos a/{item.path} b/{item.path}\n"
            f"new file sha256 {item.content_digest}\n"
            "--- /dev/null\n"
            f"+++ b/{item.path}\n"
            "@@ full file @@\n"
            f"{lines}"
        )
    return "\n".join(section.rstrip("\n") for section in sections) + ("\n" if sections else "")


def _standalone_git(workspace: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-c", f"core.hooksPath={os.devnull}", *arguments),
        cwd=workspace,
        env=_git_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise CustomerDeliveryPolicyError("Could not inspect the reviewed Git patch")
    return result.stdout


def _git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_KEY_0",
        "GIT_CONFIG_VALUE_0",
    ):
        environment.pop(name, None)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment
