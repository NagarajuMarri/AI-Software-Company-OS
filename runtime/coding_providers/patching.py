"""Validated, staged text-only patch application inside a managed workspace."""

import os
from pathlib import Path

from runtime.coding_providers.errors import ProviderPolicyError
from runtime.coding_providers.models import FileOperationKind
from runtime.coding_providers.path_policy import (
    allowed_path,
    secure_destination,
)
from runtime.managed_execution.policy import safe_relative_path, validate_change


class ControlledPatchApplier:
    def __init__(
        self, *, maximum_patch_bytes=128_000, maximum_file_bytes=256_000,
        allow_deletions=False,
    ):
        self.maximum_patch_bytes = maximum_patch_bytes
        self.maximum_file_bytes = maximum_file_bytes
        self.allow_deletions = allow_deletions

    def validate(self, workspace_path, operations, *, task, policy):
        root = Path(workspace_path).resolve()
        seen = set()
        total = 0
        validated = []
        for operation in operations:
            path = safe_relative_path(operation.path)
            if path in seen or path == ".git" or path.startswith(".git/"):
                raise ProviderPolicyError("Duplicate, conflicting, or Git-internal patch")
            seen.add(path)
            if not allowed_path(path, task.allowed_paths, task.forbidden_paths):
                raise ProviderPolicyError("Patch path is outside policy")
            validate_change(path, policy)
            destination = secure_destination(root, path)
            if operation.kind == FileOperationKind.DELETE:
                if not self.allow_deletions:
                    raise ProviderPolicyError("File deletion is not permitted")
                validated.append((operation, destination, None))
                continue
            if operation.content is None or "\0" in operation.content:
                raise ProviderPolicyError("Patch content must be UTF-8 text")
            content = operation.content.encode("utf-8")
            total += len(content)
            if len(content) > self.maximum_file_bytes or total > self.maximum_patch_bytes:
                raise ProviderPolicyError("Patch size limit exceeded")
            validated.append((operation, destination, operation.content))
        return tuple(validated)

    def apply_staged(
        self, workspace_path, operations, *, task, policy, effect_id,
        completed_callback=lambda path: None,
    ):
        root = Path(workspace_path).resolve()
        validated = self.validate(root, operations, task=task, policy=policy)
        staging_root = root / ".ascos-provider-staging" / effect_id
        secure_destination(root, ".ascos-provider-staging")
        staging_root.mkdir(parents=True, exist_ok=True)
        staged = []
        for index, (operation, destination, content) in enumerate(validated):
            if operation.kind == FileOperationKind.DELETE:
                staged.append((operation, destination, None))
                continue
            stage = staging_root / f"{index}.stage"
            with stage.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            staged.append((operation, destination, stage))
        for operation, destination, stage in staged:
            if operation.kind == FileOperationKind.DELETE:
                destination.unlink()
            else:
                secure_destination(root, operation.path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, destination)
            completed_callback(operation.path)
        self.cleanup_staging(staging_root)
        return tuple(operation.path for operation, _, _ in validated)

    def apply(self, workspace_path, operations, *, task, policy):
        return self.apply_staged(
            workspace_path, operations, task=task, policy=policy,
            effect_id="direct", completed_callback=lambda path: None)

    @staticmethod
    def cleanup_staging(staging_root):
        staging_root = Path(staging_root)
        try:
            staging_root.rmdir()
            staging_root.parent.rmdir()
        except OSError:
            pass
