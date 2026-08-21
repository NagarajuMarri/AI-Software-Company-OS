"""Exact Day 31 workspace-bound composition for ASCOS Day 32."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
import subprocess

from runtime.coding_review.errors import (
    CodingReviewConflict,
    CodingReviewNotFound,
    CodingReviewPolicyError,
)
from runtime.coding_review.models import (
    ARTIFACT_STATUS,
    CODING_REVIEW_ACTIONS,
    CODING_REVIEW_CAPABILITIES,
    CODING_REVIEW_TOOL_IDS,
    DELIVERY_STATE,
    PILOT_STATUS,
    QA_STATE,
    SECURITY_STATE,
    SOURCE_STATE,
    WORKSPACE_STATE,
    CodingReviewArtifact,
    CodingReviewAuthority,
    CodingReviewObservation,
    CodingReviewWorkOrder,
    ObservedProductFile,
    artifact_id_for,
    canonical_digest,
)
from runtime.coding_review.persistence import FileCodingReviewArtifactStore
from runtime.coding_review.provider import CodingReviewProvider
from runtime.product_workspace import (
    ARTIFACT_STATUS as WORKSPACE_ARTIFACT_STATUS,
    PILOT_STATUS as WORKSPACE_PILOT_STATUS,
    SOURCE_STATE as DAY31_SOURCE_STATE,
    WORKSPACE_STATE as DAY31_WORKSPACE_STATE,
    FileProductWorkspaceArtifactStore,
    ProductWorkspaceArtifact,
)
from runtime.workforce_orchestration import (
    FileOrchestrationArtifactStore,
    MultiAgentOrchestrationArtifact,
    OrchestrationSourceKind,
)
from runtime.workforce_qa import (
    ARTIFACT_STATUS as QA_ARTIFACT_STATUS,
    PILOT_STATUS as QA_PILOT_STATUS,
    FileQAArtifactStore,
    QAWorkArtifact,
)
from runtime.workforce_security import (
    ARTIFACT_STATUS as SECURITY_ARTIFACT_STATUS,
    PILOT_STATUS as SECURITY_PILOT_STATUS,
    FileSecurityArtifactStore,
    SecurityWorkArtifact,
)


class CodingReviewService:
    """Run bounded coding, QA, and Security while stopping before Git delivery."""

    def __init__(
        self,
        provider: CodingReviewProvider,
        workspace_store: FileProductWorkspaceArtifactStore,
        orchestration_store: FileOrchestrationArtifactStore,
        qa_store: FileQAArtifactStore,
        security_store: FileSecurityArtifactStore,
        store: FileCodingReviewArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._workspace_store = workspace_store
        self._orchestration_store = orchestration_store
        self._qa_store = qa_store
        self._security_store = security_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._git_count = 0

    def run(
        self,
        *,
        execution_id: str,
        work_order: CodingReviewWorkOrder,
        authority: CodingReviewAuthority,
        workspace_artifact: ProductWorkspaceArtifact,
        orchestration_artifact: MultiAgentOrchestrationArtifact,
        qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact,
        source_repository: Path,
        workspace: Path,
    ) -> CodingReviewArtifact:
        if not isinstance(work_order, CodingReviewWorkOrder):
            raise CodingReviewPolicyError("Coding-review work order is invalid")
        if not isinstance(authority, CodingReviewAuthority):
            raise CodingReviewPolicyError("Coding-review authority is invalid")
        existing = self._existing(work_order.tenant_id, execution_id)
        if existing is not None:
            if not (
                existing.work_order_digest == work_order.digest
                and existing.authority_digest == authority.digest
                and existing.workspace_artifact_digest == workspace_artifact.digest
                and existing.orchestration_artifact_digest == orchestration_artifact.digest
                and existing.qa_artifact_digest == qa_artifact.digest
                and existing.security_artifact_digest == security_artifact.digest
            ):
                raise CodingReviewConflict(
                    "Coding-review execution already has different immutable state"
                )
            return existing

        self._validate_sources(
            work_order,
            workspace_artifact,
            orchestration_artifact,
            qa_artifact,
            security_artifact,
        )
        self._validate_authority(work_order, authority, self._clock())
        if not isinstance(source_repository, Path) or not isinstance(workspace, Path):
            raise CodingReviewPolicyError("Coding-review repository paths are invalid")
        self._git_count = 0
        before_source = self._source_snapshot(source_repository)
        before_workspace = self._workspace_snapshot(workspace, include_changes=True)
        self._validate_before(
            work_order,
            workspace_artifact,
            source_repository,
            workspace,
            before_source,
            before_workspace,
        )

        observation = self._provider.execute(workspace, work_order, authority)
        if not isinstance(observation, CodingReviewObservation):
            raise CodingReviewPolicyError("Coding-review provider observation is invalid")
        after_source = self._source_snapshot(source_repository)
        after_workspace = self._workspace_snapshot(workspace, include_changes=True)
        final_paths = after_workspace[4]
        final_files = tuple(
            ObservedProductFile(
                path=path,
                owner_role=work_order.owner_for(path),
                content_digest=hashlib.sha256((workspace / path).read_bytes()).hexdigest(),
            )
            for path in final_paths
        )
        final_diff_digest = canonical_digest(
            {
                "base_commit": work_order.base_commit,
                "base_tree": work_order.base_tree,
                "changed_files": tuple(
                    (item.path, item.owner_role, item.content_digest) for item in final_files
                ),
            }
        )
        observation = replace(
            observation,
            final_changed_paths=final_paths,
            final_files=final_files,
            final_diff_digest=final_diff_digest,
        )
        self._validate_after(
            work_order,
            authority,
            before_source,
            before_workspace,
            after_source,
            after_workspace,
            observation,
        )
        artifact = CodingReviewArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=work_order.assignment_id,
            orchestration_artifact_id=orchestration_artifact.artifact_id,
            orchestration_artifact_digest=orchestration_artifact.digest,
            orchestration_source_set_digest=orchestration_artifact.source_set_digest,
            workspace_artifact_id=workspace_artifact.artifact_id,
            workspace_artifact_digest=workspace_artifact.digest,
            qa_artifact_id=qa_artifact.artifact_id,
            qa_artifact_digest=qa_artifact.digest,
            security_artifact_id=security_artifact.artifact_id,
            security_artifact_digest=security_artifact.digest,
            repository_id=work_order.repository_id,
            repository_identity=work_order.repository_identity,
            workspace_id=work_order.workspace_id,
            base_branch=work_order.base_branch,
            base_commit=work_order.base_commit,
            base_tree=work_order.base_tree,
            feature_branch=work_order.feature_branch,
            provider_id=observation.provider_id,
            authority_digest=authority.digest,
            capability_ids=CODING_REVIEW_CAPABILITIES,
            action_ids=CODING_REVIEW_ACTIONS,
            tool_ids=CODING_REVIEW_TOOL_IDS,
            rounds=observation.rounds,
            failure_routes=observation.failure_routes,
            final_changed_paths=observation.final_changed_paths,
            final_files=observation.final_files,
            final_diff_digest=observation.final_diff_digest,
            qa_execution_count=observation.qa_execution_count,
            security_execution_count=observation.security_execution_count,
            product_file_write_count=observation.product_file_write_count,
            specialized_command_count=observation.specialized_command_count,
            git_inspection_count=self._git_count,
            provider_output_digest=observation.digest,
            generated_at=self._clock(),
            network_call_count=observation.network_call_count,
            general_command_count=observation.general_command_count,
            credential_access_count=observation.credential_access_count,
            staged_path_count=0,
            commit_count=observation.commit_count,
            push_count=observation.push_count,
            pull_request_count=observation.pull_request_count,
            source_state=SOURCE_STATE,
            workspace_state=WORKSPACE_STATE,
            qa_state=QA_STATE,
            security_state=SECURITY_STATE,
            delivery_state=DELIVERY_STATE,
            status=ARTIFACT_STATUS,
            pilot_status=PILOT_STATUS,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> CodingReviewArtifact:
        return self._store.load(tenant_id, execution_id)

    def _existing(self, tenant_id: str, execution_id: str) -> CodingReviewArtifact | None:
        try:
            return self._store.load(tenant_id, execution_id)
        except CodingReviewNotFound:
            return None

    def _validate_sources(
        self,
        work_order: CodingReviewWorkOrder,
        workspace: ProductWorkspaceArtifact,
        orchestration: MultiAgentOrchestrationArtifact,
        qa: QAWorkArtifact,
        security: SecurityWorkArtifact,
    ) -> None:
        if not (
            isinstance(workspace, ProductWorkspaceArtifact)
            and isinstance(orchestration, MultiAgentOrchestrationArtifact)
            and isinstance(qa, QAWorkArtifact)
            and isinstance(security, SecurityWorkArtifact)
        ):
            raise CodingReviewPolicyError("Coding-review source artifact type is invalid")
        if not (
            workspace.tenant_id == orchestration.tenant_id == qa.tenant_id == security.tenant_id
            == work_order.tenant_id
            and workspace.opportunity_id == orchestration.opportunity_id == qa.opportunity_id
            == security.opportunity_id == work_order.opportunity_id
            and workspace.digest == work_order.workspace_artifact_digest
            and workspace.orchestration_artifact_digest == orchestration.digest
            == work_order.orchestration_artifact_digest
            and orchestration.source_set_digest == work_order.orchestration_source_set_digest
            and qa.digest == work_order.qa_artifact_digest
            and security.digest == work_order.security_artifact_digest
            and security.qa_artifact_digest == qa.digest
            and workspace.repository_id == work_order.repository_id
            and workspace.repository_identity == work_order.repository_identity
            and workspace.workspace_id == work_order.workspace_id
            and workspace.base_branch == work_order.base_branch
            and workspace.base_commit == work_order.base_commit
            and workspace.base_tree == work_order.base_tree
            and workspace.feature_branch == work_order.feature_branch
            and workspace.status == WORKSPACE_ARTIFACT_STATUS
            and workspace.source_state == DAY31_SOURCE_STATE
            and workspace.workspace_state == DAY31_WORKSPACE_STATE
            and workspace.pilot_status == WORKSPACE_PILOT_STATUS == PILOT_STATUS
            and qa.status == QA_ARTIFACT_STATUS
            and qa.pilot_status == QA_PILOT_STATUS == PILOT_STATUS
            and security.status == SECURITY_ARTIFACT_STATUS
            and security.pilot_status == SECURITY_PILOT_STATUS == PILOT_STATUS
        ):
            raise CodingReviewPolicyError(
                "Coding review requires the exact Day 26, Day 27, Day 30, and Day 31 chain"
            )
        bindings = {item.kind: item.artifact_digest for item in orchestration.source_bindings}
        if (
            bindings.get(OrchestrationSourceKind.QA) != qa.digest
            or bindings.get(OrchestrationSourceKind.SECURITY) != security.digest
        ):
            raise CodingReviewPolicyError("Coding-review orchestration bindings are invalid")
        persisted = (
            self._workspace_store.load(workspace.tenant_id, workspace.execution_id),
            self._orchestration_store.load(orchestration.tenant_id, orchestration.execution_id),
            self._qa_store.load(qa.tenant_id, qa.execution_id),
            self._security_store.load(security.tenant_id, security.execution_id),
        )
        if persisted != (workspace, orchestration, qa, security):
            raise CodingReviewPolicyError("Coding-review source artifact is not exact persisted state")

    @staticmethod
    def _validate_authority(
        work_order: CodingReviewWorkOrder,
        authority: CodingReviewAuthority,
        now: datetime,
    ) -> None:
        if not (
            authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.work_order_digest == work_order.digest
            and authority.workspace_artifact_digest == work_order.workspace_artifact_digest
            and authority.allowed_action_ids == CODING_REVIEW_ACTIONS
            and authority.allowed_tool_ids == CODING_REVIEW_TOOL_IDS
            and not authority.live_provider_allowed
            and not authority.network_allowed
            and not authority.credentials_allowed
            and not authority.source_file_writes_allowed
            and authority.workspace_text_writes_allowed
            and not authority.commit_allowed
            and not authority.push_allowed
            and not authority.pull_request_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.issued_at <= now <= authority.expires_at
        ):
            raise CodingReviewPolicyError("Coding-review authority or time boundary does not match")

    def _validate_before(
        self,
        work_order: CodingReviewWorkOrder,
        artifact: ProductWorkspaceArtifact,
        source_path: Path,
        workspace_path: Path,
        source: tuple[str, str, str, str, str],
        workspace: tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]],
    ) -> None:
        if source_path.absolute().resolve() != source_path.absolute():
            raise CodingReviewPolicyError("Coding-review source path contains a link")
        if workspace_path.absolute().resolve() != workspace_path.absolute():
            raise CodingReviewPolicyError("Coding-review workspace path contains a link")
        if workspace_path.name != artifact.workspace_relative_path:
            raise CodingReviewPolicyError("Coding-review workspace identity does not match")
        source_branch, source_head, source_tree, source_status, remote = source
        branch, head, tree, status, changed_paths, staged = workspace
        if not (
            source_branch == work_order.base_branch
            and source_head == work_order.base_commit
            and source_tree == work_order.base_tree
            and source_status == ""
            and remote == work_order.repository_identity
            and branch == work_order.feature_branch
            and head == work_order.base_commit
            and tree == work_order.base_tree
            and status == ""
            and changed_paths == ()
            and staged == ()
        ):
            raise CodingReviewPolicyError("Coding-review source or workspace is not the exact clean base")

    def _validate_after(
        self,
        work_order: CodingReviewWorkOrder,
        authority: CodingReviewAuthority,
        source_before: tuple[str, str, str, str, str],
        workspace_before: tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]],
        source_after: tuple[str, str, str, str, str],
        workspace_after: tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]],
        observation: CodingReviewObservation,
    ) -> None:
        branch, head, tree, status, changed_paths, staged = workspace_after
        if not (
            source_after == source_before
            and workspace_before[0] == branch == work_order.feature_branch
            and workspace_before[1] == head == work_order.base_commit
            and workspace_before[2] == tree == work_order.base_tree
            and status != ""
            and staged == ()
            and changed_paths == observation.final_changed_paths
            and set(changed_paths) <= set(work_order.allowed_paths)
            and observation.product_file_write_count <= authority.max_file_writes
            and observation.specialized_command_count
            + observation.product_file_write_count
            + self._git_count
            <= authority.max_tool_calls
            and observation.network_call_count == 0
            and observation.general_command_count == 0
            and observation.credential_access_count == 0
            and observation.commit_count == 0
            and observation.push_count == 0
            and observation.pull_request_count == 0
            and len(observation.rounds) <= authority.max_review_rounds
        ):
            raise CodingReviewPolicyError(
                "Coding-review provider crossed its workspace, review, or delivery boundary"
            )

    def _source_snapshot(self, path: Path) -> tuple[str, str, str, str, str]:
        self._real_directory(path, "source repository")
        root = self._git(path, ("rev-parse", "--show-toplevel")).strip()
        if Path(root).resolve() != path.absolute().resolve():
            raise CodingReviewPolicyError("Coding-review source is not the repository root")
        return (
            self._git(path, ("branch", "--show-current")).strip(),
            self._git(path, ("rev-parse", "HEAD")).strip(),
            self._git(path, ("rev-parse", "HEAD^{tree}")).strip(),
            self._git(path, ("status", "--porcelain=v1", "--untracked-files=all")),
            self._git(path, ("remote", "get-url", "origin")).strip(),
        )

    def _workspace_snapshot(
        self, path: Path, *, include_changes: bool
    ) -> tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]]:
        self._real_directory(path, "isolated workspace")
        root = self._git(path, ("rev-parse", "--show-toplevel")).strip()
        if Path(root).resolve() != path.absolute().resolve():
            raise CodingReviewPolicyError("Coding-review workspace is not the worktree root")
        status = self._git(
            path, ("status", "--porcelain=v1", "-z", "--untracked-files=all")
        )
        changed = self._status_paths(status) if include_changes else ()
        staged = tuple(
            item
            for item in self._git(path, ("diff", "--cached", "--name-only", "-z")).split("\0")
            if item
        )
        return (
            self._git(path, ("branch", "--show-current")).strip(),
            self._git(path, ("rev-parse", "HEAD")).strip(),
            self._git(path, ("rev-parse", "HEAD^{tree}")).strip(),
            status,
            changed,
            staged,
        )

    @staticmethod
    def _status_paths(status: str) -> tuple[str, ...]:
        records = tuple(item for item in status.split("\0") if item)
        paths: list[str] = []
        for record in records:
            if len(record) < 4 or record[2] != " ":
                raise CodingReviewPolicyError("Coding-review Git status is malformed")
            code, path = record[:2], record[3:]
            if any(marker in code for marker in "RCDU") or not path:
                raise CodingReviewPolicyError("Coding-review file deletion or rename is forbidden")
            paths.append(path)
        if len(set(paths)) != len(paths):
            raise CodingReviewPolicyError("Coding-review Git status contains duplicate paths")
        return tuple(sorted(paths))

    def _git(self, cwd: Path, arguments: tuple[str, ...]) -> str:
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
        self._git_count += 1
        if result.returncode != 0 or len(result.stdout.encode()) > 2_000_000:
            raise CodingReviewPolicyError("Bounded coding-review Git inspection failed")
        return result.stdout

    @staticmethod
    def _real_directory(path: Path, label: str) -> None:
        try:
            details = path.absolute().lstat()
        except FileNotFoundError as error:
            raise CodingReviewPolicyError(f"Coding-review {label} was not found") from error
        if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
            raise CodingReviewPolicyError(f"Coding-review {label} is unsafe")
