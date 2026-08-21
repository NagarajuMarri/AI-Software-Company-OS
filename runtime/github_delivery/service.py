"""Governed Day 33 service for exact reviewed GitHub delivery."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
import subprocess
from typing import Callable

from runtime.coding_review import (
    ARTIFACT_STATUS as CODING_ARTIFACT_STATUS,
    DELIVERY_STATE as CODING_DELIVERY_STATE,
    PILOT_STATUS as CODING_PILOT_STATUS,
    QA_STATE as CODING_QA_STATE,
    SECURITY_STATE as CODING_SECURITY_STATE,
    SOURCE_STATE as CODING_SOURCE_STATE,
    WORKSPACE_STATE as CODING_WORKSPACE_STATE,
    CodingReviewArtifact,
    FileCodingReviewArtifactStore,
)
from runtime.github_delivery.errors import (
    GitHubDeliveryConflict,
    GitHubDeliveryNotFound,
    GitHubDeliveryPolicyError,
)
from runtime.github_delivery.models import (
    ARTIFACT_STATUS,
    BRANCH_STATE,
    DELIVERY_STATE,
    GITHUB_DELIVERY_ACTIONS,
    GITHUB_DELIVERY_CAPABILITIES,
    GITHUB_DELIVERY_TOOL_IDS,
    PILOT_STATUS,
    PULL_REQUEST_STATE,
    SOURCE_STATE,
    WORKSPACE_STATE,
    GitHubDeliveryArtifact,
    GitHubDeliveryAuthority,
    GitHubDeliveryObservation,
    GitHubDeliveryWorkOrder,
    ReviewedFileBinding,
    artifact_id_for,
)
from runtime.github_delivery.persistence import FileGitHubDeliveryArtifactStore
from runtime.github_delivery.provider import GitHubDeliveryProvider


class GitHubDeliveryService:
    """Commit and publish only exact Day 32 reviewed files under current authority."""

    def __init__(
        self,
        provider: GitHubDeliveryProvider,
        coding_review_store: FileCodingReviewArtifactStore,
        store: FileGitHubDeliveryArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._coding_review_store = coding_review_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        work_order: GitHubDeliveryWorkOrder,
        authority: GitHubDeliveryAuthority,
        coding_review_artifact: CodingReviewArtifact,
        source_repository: Path,
        workspace: Path,
    ) -> GitHubDeliveryArtifact:
        if not isinstance(work_order, GitHubDeliveryWorkOrder):
            raise GitHubDeliveryPolicyError("GitHub delivery work order is invalid")
        if not isinstance(authority, GitHubDeliveryAuthority):
            raise GitHubDeliveryPolicyError("GitHub delivery authority is invalid")
        existing = self._existing(work_order.tenant_id, execution_id)
        if existing is not None:
            if not (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.coding_review_artifact_digest == coding_review_artifact.digest
            ):
                raise GitHubDeliveryConflict(
                    "GitHub delivery execution already has different immutable state"
                )
            return existing

        self._validate_source_artifact(work_order, coding_review_artifact)
        self._validate_authority(work_order, authority, self._clock())
        if not isinstance(source_repository, Path) or not isinstance(workspace, Path):
            raise GitHubDeliveryPolicyError("GitHub delivery repository paths are invalid")
        source_before = self._source_snapshot(source_repository)
        workspace_before = self._workspace_snapshot(workspace)
        self._validate_before(
            work_order,
            coding_review_artifact,
            source_repository,
            workspace,
            source_before,
            workspace_before,
        )

        observation = self._provider.deliver(workspace, work_order, authority)
        if not isinstance(observation, GitHubDeliveryObservation):
            raise GitHubDeliveryPolicyError("GitHub delivery provider observation is invalid")
        source_after = self._source_snapshot(source_repository)
        workspace_after = self._workspace_snapshot(workspace)
        self._validate_after(
            work_order,
            authority,
            coding_review_artifact,
            source_before,
            source_after,
            workspace_after,
            workspace,
            observation,
        )
        artifact = GitHubDeliveryArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            coding_review_artifact_id=coding_review_artifact.artifact_id,
            coding_review_artifact_digest=coding_review_artifact.digest,
            workspace_artifact_digest=coding_review_artifact.workspace_artifact_digest,
            orchestration_artifact_digest=coding_review_artifact.orchestration_artifact_digest,
            qa_artifact_digest=coding_review_artifact.qa_artifact_digest,
            security_artifact_digest=coding_review_artifact.security_artifact_digest,
            repository_id=work_order.repository_id,
            repository_identity=work_order.repository_identity,
            repository_full_name=work_order.repository_full_name,
            workspace_id=work_order.workspace_id,
            base_branch=work_order.base_branch,
            base_commit=work_order.base_commit,
            base_tree=work_order.base_tree,
            feature_branch=work_order.feature_branch,
            reviewed_files=work_order.reviewed_files,
            final_diff_digest=work_order.final_diff_digest,
            commit_message=work_order.commit_message,
            pull_request_title=work_order.pull_request_title,
            pull_request_body_digest=work_order.pull_request_body_digest,
            provider_id=observation.provider_id,
            authority_digest=authority.digest,
            capability_ids=GITHUB_DELIVERY_CAPABILITIES,
            action_ids=GITHUB_DELIVERY_ACTIONS,
            tool_ids=GITHUB_DELIVERY_TOOL_IDS,
            staged_paths=observation.staged_paths,
            committed_paths=observation.committed_paths,
            commit_parent=observation.commit_parent,
            commit_sha=observation.commit_sha,
            commit_tree=observation.commit_tree,
            remote_branch_sha=observation.remote_branch_sha,
            pull_request=observation.pull_request,
            git_command_count=observation.git_command_count,
            controlled_network_call_count=observation.controlled_network_call_count,
            credential_handle_count=observation.credential_handle_count,
            provider_output_digest=observation.digest,
            generated_at=self._clock(),
            secret_value_exposure_count=observation.secret_value_exposure_count,
            unapproved_network_call_count=observation.unapproved_network_call_count,
            unrelated_path_count=observation.unrelated_path_count,
            general_command_count=observation.general_command_count,
            force_push_count=observation.force_push_count,
            commit_count=observation.commit_count,
            push_count=observation.push_count,
            pull_request_count=observation.pull_request_count,
            merge_count=observation.merge_count,
            deployment_count=observation.deployment_count,
            release_count=observation.release_count,
            source_state=SOURCE_STATE,
            workspace_state=WORKSPACE_STATE,
            branch_state=BRANCH_STATE,
            pull_request_state=PULL_REQUEST_STATE,
            delivery_state=DELIVERY_STATE,
            status=ARTIFACT_STATUS,
            pilot_status=PILOT_STATUS,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> GitHubDeliveryArtifact:
        return self._store.load(tenant_id, execution_id)

    def _existing(self, tenant_id: str, execution_id: str) -> GitHubDeliveryArtifact | None:
        try:
            return self._store.load(tenant_id, execution_id)
        except GitHubDeliveryNotFound:
            return None

    def _validate_source_artifact(
        self,
        work_order: GitHubDeliveryWorkOrder,
        artifact: CodingReviewArtifact,
    ) -> None:
        if not isinstance(artifact, CodingReviewArtifact):
            raise GitHubDeliveryPolicyError("GitHub delivery source artifact is invalid")
        expected_files = tuple(
            ReviewedFileBinding(item.path, item.owner_role, item.content_digest)
            for item in artifact.final_files
        )
        if not (
            artifact.digest == work_order.coding_review_artifact_digest
            and artifact.tenant_id == work_order.tenant_id
            and artifact.opportunity_id == work_order.opportunity_id
            and artifact.workspace_artifact_digest == work_order.workspace_artifact_digest
            and artifact.repository_id == work_order.repository_id
            and artifact.repository_identity == work_order.repository_identity
            and artifact.workspace_id == work_order.workspace_id
            and artifact.base_branch == work_order.base_branch
            and artifact.base_commit == work_order.base_commit
            and artifact.base_tree == work_order.base_tree
            and artifact.feature_branch == work_order.feature_branch
            and expected_files == work_order.reviewed_files
            and artifact.final_diff_digest == work_order.final_diff_digest
            and artifact.status == CODING_ARTIFACT_STATUS
            and artifact.source_state == CODING_SOURCE_STATE
            and artifact.workspace_state == CODING_WORKSPACE_STATE
            and artifact.qa_state == CODING_QA_STATE
            and artifact.security_state == CODING_SECURITY_STATE
            and artifact.delivery_state == CODING_DELIVERY_STATE
            and artifact.commit_count == artifact.push_count == artifact.pull_request_count == 0
            and artifact.pilot_status == CODING_PILOT_STATUS == PILOT_STATUS
        ):
            raise GitHubDeliveryPolicyError(
                "GitHub delivery requires the exact successful persisted Day 32 review artifact"
            )
        persisted = self._coding_review_store.load(artifact.tenant_id, artifact.execution_id)
        if persisted != artifact:
            raise GitHubDeliveryPolicyError("GitHub delivery source is not exact persisted state")

    @staticmethod
    def _validate_authority(
        work_order: GitHubDeliveryWorkOrder,
        authority: GitHubDeliveryAuthority,
        now: datetime,
    ) -> None:
        if not (
            authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.work_order_digest == work_order.digest
            and authority.coding_review_artifact_digest == work_order.coding_review_artifact_digest
            and authority.repository_id == work_order.repository_id
            and authority.workspace_id == work_order.workspace_id
            and authority.base_branch == work_order.base_branch
            and authority.feature_branch == work_order.feature_branch
            and authority.allowed_action_ids == GITHUB_DELIVERY_ACTIONS
            and authority.allowed_tool_ids == GITHUB_DELIVERY_TOOL_IDS
            and len(work_order.reviewed_files) <= authority.max_reviewed_paths
            and authority.repository_write_allowed
            and authority.controlled_network_allowed
            and authority.scoped_credential_handle_allowed
            and authority.commit_allowed
            and authority.push_allowed
            and authority.pull_request_allowed
            and authority.draft_only
            and not authority.force_push_allowed
            and not authority.merge_allowed
            and not authority.deployment_allowed
            and not authority.release_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.issued_at <= now <= authority.expires_at
        ):
            raise GitHubDeliveryPolicyError("GitHub delivery authority or time boundary does not match")

    def _validate_before(
        self,
        work_order: GitHubDeliveryWorkOrder,
        artifact: CodingReviewArtifact,
        source_path: Path,
        workspace_path: Path,
        source: tuple[str, str, str, str, str],
        workspace: tuple[str, str, str, str, tuple[str, ...], tuple[str, ...], str],
    ) -> None:
        if source_path.absolute().resolve() != source_path.absolute():
            raise GitHubDeliveryPolicyError("GitHub delivery source path contains a link")
        if workspace_path.absolute().resolve() != workspace_path.absolute():
            raise GitHubDeliveryPolicyError("GitHub delivery workspace path contains a link")
        if workspace_path.name != work_order.workspace_id:
            raise GitHubDeliveryPolicyError("GitHub delivery workspace identity does not match")
        source_branch, source_head, source_tree, source_status, source_remote = source
        branch, head, tree, status, changed, staged, remote = workspace
        if not (
            source_branch == work_order.base_branch
            and source_head == work_order.base_commit
            and source_tree == work_order.base_tree
            and source_status == ""
            and source_remote == work_order.repository_identity
            and branch == work_order.feature_branch
            and head == work_order.base_commit
            and tree == work_order.base_tree
            and status != ""
            and changed == work_order.reviewed_paths == artifact.final_changed_paths
            and staged == ()
            and remote == work_order.repository_identity
        ):
            raise GitHubDeliveryPolicyError(
                "GitHub delivery source or workspace is not the exact reviewed Day 32 state"
            )
        self._validate_git_config(workspace_path)
        self._validate_reviewed_files(workspace_path, work_order.reviewed_files)

    def _validate_after(
        self,
        work_order: GitHubDeliveryWorkOrder,
        authority: GitHubDeliveryAuthority,
        artifact: CodingReviewArtifact,
        source_before: tuple[str, str, str, str, str],
        source_after: tuple[str, str, str, str, str],
        workspace_after: tuple[str, str, str, str, tuple[str, ...], tuple[str, ...], str],
        workspace_path: Path,
        observation: GitHubDeliveryObservation,
    ) -> None:
        branch, head, tree, status, changed, staged, remote = workspace_after
        parent = self._git(workspace_path, ("rev-parse", "HEAD^" )).strip()
        subject = self._git(workspace_path, ("log", "-1", "--format=%s")).strip()
        committed_paths = self._zpaths(
            self._git(
                workspace_path,
                ("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD"),
            )
        )
        receipt = observation.pull_request
        if not (
            source_after == source_before
            and branch == work_order.feature_branch
            and head == observation.commit_sha
            and tree == observation.commit_tree
            and status == ""
            and changed == staged == ()
            and remote == work_order.repository_identity
            and parent == observation.commit_parent == work_order.base_commit
            and subject == work_order.commit_message
            and committed_paths == observation.committed_paths == work_order.reviewed_paths
            and observation.staged_paths == work_order.reviewed_paths
            and observation.remote_branch_sha == observation.commit_sha
            and receipt.repository_full_name == work_order.repository_full_name
            and receipt.base_branch == work_order.base_branch
            and receipt.head_branch == work_order.feature_branch
            and receipt.base_commit == work_order.base_commit
            and receipt.head_commit == observation.commit_sha
            and receipt.title == work_order.pull_request_title
            and receipt.body_digest == work_order.pull_request_body_digest
            and receipt.draft
            and receipt.state == "OPEN"
            and not receipt.merged
            and observation.git_command_count <= authority.max_git_commands
            and observation.controlled_network_call_count
            <= authority.max_controlled_network_calls
            and observation.credential_handle_count <= 2
            and observation.secret_value_exposure_count == 0
            and observation.unapproved_network_call_count == 0
            and observation.unrelated_path_count == 0
            and observation.general_command_count == 0
            and observation.force_push_count == 0
            and observation.commit_count == observation.push_count
            == observation.pull_request_count
            == 1
            and observation.merge_count == observation.deployment_count
            == observation.release_count
            == 0
        ):
            raise GitHubDeliveryPolicyError(
                "GitHub delivery provider crossed its commit, push, draft-PR, or stop boundary"
            )
        self._validate_reviewed_files(workspace_path, work_order.reviewed_files)
        if artifact.final_diff_digest != work_order.final_diff_digest:
            raise GitHubDeliveryPolicyError("Reviewed diff binding changed during delivery")

    def _source_snapshot(self, path: Path) -> tuple[str, str, str, str, str]:
        self._real_directory(path, "source repository")
        root = self._git(path, ("rev-parse", "--show-toplevel")).strip()
        if Path(root).resolve() != path.absolute().resolve():
            raise GitHubDeliveryPolicyError("GitHub delivery source is not the repository root")
        return (
            self._git(path, ("branch", "--show-current")).strip(),
            self._git(path, ("rev-parse", "HEAD")).strip(),
            self._git(path, ("rev-parse", "HEAD^{tree}")).strip(),
            self._git(path, ("status", "--porcelain=v1", "--untracked-files=all")),
            self._git(path, ("remote", "get-url", "origin")).strip(),
        )

    def _workspace_snapshot(
        self, path: Path
    ) -> tuple[str, str, str, str, tuple[str, ...], tuple[str, ...], str]:
        self._real_directory(path, "delivery workspace")
        root = self._git(path, ("rev-parse", "--show-toplevel")).strip()
        if Path(root).resolve() != path.absolute().resolve():
            raise GitHubDeliveryPolicyError("GitHub delivery workspace is not the repository root")
        status = self._git(path, ("status", "--porcelain=v1", "-z", "--untracked-files=all"))
        return (
            self._git(path, ("branch", "--show-current")).strip(),
            self._git(path, ("rev-parse", "HEAD")).strip(),
            self._git(path, ("rev-parse", "HEAD^{tree}")).strip(),
            status,
            self._status_paths(status),
            self._zpaths(self._git(path, ("diff", "--cached", "--name-only", "-z"))),
            self._git(path, ("remote", "get-url", "origin")).strip(),
        )

    def _validate_git_config(self, path: Path) -> None:
        unsafe = self._git(
            path,
            (
                "config",
                "--local",
                "--name-only",
                "--get-regexp",
                r"^(filter\.|core\.hooksPath$|core\.fsmonitor$|credential\.|url\.|http\.|remote\..*\.pushurl$)",
            ),
            allowed_returncodes=(0, 1),
        ).strip()
        if unsafe:
            raise GitHubDeliveryPolicyError(
                "GitHub delivery repository has executable or credential Git configuration"
            )

    @staticmethod
    def _validate_reviewed_files(path: Path, bindings: tuple[ReviewedFileBinding, ...]) -> None:
        for binding in bindings:
            target = path / binding.path
            try:
                details = target.lstat()
            except FileNotFoundError as error:
                raise GitHubDeliveryPolicyError("A reviewed file is missing") from error
            if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
                raise GitHubDeliveryPolicyError("A reviewed file is unsafe")
            if hashlib.sha256(target.read_bytes()).hexdigest() != binding.content_digest:
                raise GitHubDeliveryPolicyError("A reviewed file digest changed")

    @staticmethod
    def _status_paths(status: str) -> tuple[str, ...]:
        records = tuple(item for item in status.split("\0") if item)
        paths: list[str] = []
        for record in records:
            if len(record) < 4 or record[2] != " ":
                raise GitHubDeliveryPolicyError("GitHub delivery status is malformed")
            code, path = record[:2], record[3:]
            if any(marker in code for marker in "RCDU") or not path:
                raise GitHubDeliveryPolicyError("GitHub delivery deletion or rename is forbidden")
            paths.append(path)
        if len(paths) != len(set(paths)):
            raise GitHubDeliveryPolicyError("GitHub delivery status contains duplicate paths")
        return tuple(sorted(paths))

    @staticmethod
    def _zpaths(output: str) -> tuple[str, ...]:
        paths = tuple(item for item in output.split("\0") if item)
        if len(paths) != len(set(paths)):
            raise GitHubDeliveryPolicyError("GitHub delivery Git output contains duplicate paths")
        return tuple(sorted(paths))

    @staticmethod
    def _real_directory(path: Path, label: str) -> None:
        try:
            details = path.absolute().lstat()
        except FileNotFoundError as error:
            raise GitHubDeliveryPolicyError(f"GitHub delivery {label} was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise GitHubDeliveryPolicyError(f"GitHub delivery {label} is unsafe")

    @staticmethod
    def _git(
        cwd: Path,
        arguments: tuple[str, ...],
        *,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "LC_ALL": "C.UTF-8",
        }
        result = subprocess.run(
            (
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "credential.helper=",
                *arguments,
            ),
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            check=False,
        )
        if result.returncode not in allowed_returncodes or len(result.stdout.encode()) > 2_000_000:
            raise GitHubDeliveryPolicyError("Bounded GitHub delivery inspection failed")
        return result.stdout
