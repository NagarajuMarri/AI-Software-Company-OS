"""Conservative path, change, and coding-result validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import PurePath, PurePosixPath, PureWindowsPath

from runtime.managed_execution.errors import ExecutionPolicyError
from runtime.managed_execution.models import (
    ChangePolicy,
    ManagedCodingRequest,
    ReviewEvidence,
    ValidatedCodingResult,
)

BRANCH = re.compile(
    r"^(?![-/.])(?!.*(?:\.\.|//|@\{|[~^:?*\[\\]))"
    r"(?!.*(?:/\.|\.lock(?:/|$)))[A-Za-z0-9._/-]{1,200}(?<![/.])$"
)
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def safe_relative_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or ".." in PurePath(value.replace("\\", "/")).parts
        or "\0" in value
    ):
        raise ExecutionPolicyError(f"Unsafe relative path {value!r}")
    return value.replace("\\", "/")


def validate_branch(value: str, *, protected=("main", "master")) -> str:
    if not isinstance(value, str) or not BRANCH.fullmatch(value):
        raise ExecutionPolicyError("Unsafe feature branch")
    if value in protected:
        raise ExecutionPolicyError("Protected branch is not writable")
    return value


def validate_change(
    path: str, policy: ChangePolicy, *, additions: int = 0, deletions: int = 0
) -> None:
    normalized = safe_relative_path(path)
    lower = normalized.casefold()
    if policy.allowed_path_prefixes and not any(
        lower.startswith(prefix.casefold()) for prefix in policy.allowed_path_prefixes
    ):
        raise ExecutionPolicyError(f"Path {path!r} is outside the allow-list")
    if any(lower.startswith(prefix.casefold()) for prefix in policy.forbidden_path_prefixes):
        raise ExecutionPolicyError(f"Path {path!r} is forbidden")
    if any(lower.endswith(suffix.casefold()) for suffix in policy.forbidden_file_types):
        raise ExecutionPolicyError(f"File type for {path!r} is forbidden")
    if any(token.casefold() in lower for token in policy.protected_configuration_files):
        raise ExecutionPolicyError(f"Protected configuration path {path!r} requires approval")
    if additions > policy.maximum_additions or deletions > policy.maximum_deletions:
        raise ExecutionPolicyError("Change line limits exceeded")


def validate_coding_result(
    request: ManagedCodingRequest,
    result: ValidatedCodingResult,
    policy: ChangePolicy,
) -> ValidatedCodingResult:
    if result.external_task_id != request.external_task_id:
        raise ExecutionPolicyError("Coding result belongs to another task")
    if result.workspace_id != request.workspace_id:
        raise ExecutionPolicyError("Coding result belongs to another workspace")
    if len(result.changed_files) > min(
        request.maximum_changed_files, policy.maximum_changed_files
    ):
        raise ExecutionPolicyError("Changed-file limit exceeded")
    if result.additions + result.deletions > request.maximum_changed_lines:
        raise ExecutionPolicyError("Changed-line limit exceeded")
    if tuple(result.progress_sequences) != tuple(
        range(1, len(result.progress_sequences) + 1)
    ):
        raise ExecutionPolicyError("Malformed provider progress sequence")
    if result.status not in {
        "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_PERMANENT", "TIMED_OUT", "CANCELLED"
    }:
        raise ExecutionPolicyError("Unsupported coding-result status")
    if any(gate not in request.quality_gates for gate in result.executed_gates):
        raise ExecutionPolicyError("Result claims an unapproved quality gate")
    if result.status == "SUCCEEDED" and set(request.expected_artifacts) - set(result.artifacts):
        raise ExecutionPolicyError("Required result artifacts are missing")
    for path in result.changed_files:
        normalized = safe_relative_path(path)
        if request.allowed_paths and not any(
            normalized.startswith(prefix) for prefix in request.allowed_paths
        ):
            raise ExecutionPolicyError("Provider changed a path outside the task allow-list")
        if any(normalized.startswith(prefix) for prefix in request.forbidden_paths):
            raise ExecutionPolicyError("Provider changed a forbidden path")
        validate_change(path, policy, additions=result.additions, deletions=result.deletions)
    summary = result.summary.casefold()
    if "merge" in summary or "deploy" in summary:
        raise ExecutionPolicyError("Provider result requests merge or deployment")
    return result


def evidence_digest(evidence_without_digest) -> str:
    if is_dataclass(evidence_without_digest):
        evidence_without_digest = asdict(evidence_without_digest)  # type: ignore[arg-type]
    evidence_without_digest = dict(evidence_without_digest)
    evidence_without_digest.pop("integrity_digest", None)
    encoded = json.dumps(
        _canonical(evidence_without_digest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_evidence_digest(evidence: ReviewEvidence) -> ReviewEvidence:
    if evidence_digest(evidence) != evidence.integrity_digest:
        raise ExecutionPolicyError("Review evidence integrity digest is invalid")
    return evidence


def _canonical(value):
    if is_dataclass(value):
        return _canonical(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value
