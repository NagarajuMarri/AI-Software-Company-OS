"""Policy-bounded coding context built from approved candidate files."""

import hashlib
import json
from pathlib import Path

from runtime.coding_providers.errors import ProviderPolicyError
from runtime.coding_providers.models import (
    CodingContextFile,
    CodingContextPackage,
    ContextLimits,
)
from runtime.coding_providers.path_policy import allowed_path, secure_destination

_SECRET_FILES = {".env", ".npmrc", ".pypirc", "credentials", "id_rsa"}


class CodingContextBuilder:
    def __init__(self, limits=ContextLimits()):
        self.limits = limits

    def build(self, *, plan, task, request, workspace_path, evidence=()):
        root = Path(workspace_path).resolve()
        files = []
        total = 0
        for name in task.candidate_files[:self.limits.maximum_files]:
            path = name.replace("\\", "/")
            if Path(path).name.casefold() in _SECRET_FILES:
                continue
            if not allowed_path(path, task.allowed_paths, task.forbidden_paths):
                continue
            resolved = secure_destination(root, path)
            if not resolved.is_file():
                continue
            raw = resolved.read_bytes()
            if b"\0" in raw:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            available = min(
                self.limits.maximum_bytes_per_file,
                self.limits.maximum_total_bytes - total)
            if available <= 0:
                break
            encoded = text.encode("utf-8")[:available]
            text = encoded.decode("utf-8", errors="ignore")
            used = len(text.encode("utf-8"))
            total += used
            files.append(CodingContextFile(path, text, used < len(raw)))
        bounded_evidence = tuple(str(item)[:1_000]
                                 for item in evidence[:self.limits.maximum_evidence_items])
        payload = {
            "project_id": plan.project_id,
            "execution_plan_id": plan.execution_plan_id,
            "plan_version": plan.version,
            "managed_task_id": task.project_task_id,
            "workspace_id": plan.workspace_identity,
            "branch": plan.feature_branch,
            "objective": task.objective,
            "acceptance_criteria": task.acceptance_criteria,
            "allowed_paths": task.allowed_paths,
            "forbidden_paths": task.forbidden_paths,
            "quality_gate_commands": task.allowed_commands,
            "files": tuple((item.path, item.content, item.truncated) for item in files),
            "evidence": bounded_evidence,
            "allows_no_change_success": bool(
                getattr(task, "allows_no_change_success", False)),
            "allows_deletions": bool(getattr(task, "allows_deletions", False)),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > self.limits.maximum_prompt_bytes:
            raise ProviderPolicyError("Coding context exceeds prompt limit")
        digest = hashlib.sha256(encoded).hexdigest()
        return CodingContextPackage(
            plan.project_id, plan.execution_plan_id, plan.version,
            task.project_task_id, plan.workspace_identity, plan.feature_branch,
            task.objective, task.acceptance_criteria, task.allowed_paths,
            task.forbidden_paths, task.allowed_commands, tuple(files),
            bounded_evidence, digest, total,
            bool(getattr(task, "allows_no_change_success", False)),
            bool(getattr(task, "allows_deletions", False)))
