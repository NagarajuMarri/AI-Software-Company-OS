"""Validated text-only patch application inside a managed workspace."""

from pathlib import Path

from runtime.coding_providers.errors import ProviderPolicyError
from runtime.coding_providers.models import FileOperationKind
from runtime.managed_execution.policy import safe_relative_path, validate_change


class ControlledPatchApplier:
    def __init__(
        self, *, maximum_patch_bytes=128_000, maximum_file_bytes=256_000,
        allow_deletions=False,
    ):
        self.maximum_patch_bytes = maximum_patch_bytes
        self.maximum_file_bytes = maximum_file_bytes
        self.allow_deletions = allow_deletions

    def apply(self, workspace_path, operations, *, task, policy):
        root = Path(workspace_path).resolve()
        seen = set()
        total = 0
        validated = []
        for operation in operations:
            path = safe_relative_path(operation.path)
            if path in seen or path == ".git" or path.startswith(".git/"):
                raise ProviderPolicyError("Duplicate, conflicting, or Git-internal patch")
            seen.add(path)
            if task.allowed_paths and not any(
                    path.startswith(prefix) for prefix in task.allowed_paths):
                raise ProviderPolicyError("Patch path is outside task allow-list")
            if any(path.startswith(prefix) for prefix in task.forbidden_paths):
                raise ProviderPolicyError("Patch path is forbidden")
            validate_change(path, policy)
            destination = (root / path).resolve()
            if root not in destination.parents or destination.is_symlink():
                raise ProviderPolicyError("Patch escapes workspace or targets symlink")
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
        for operation, destination, content in validated:
            if operation.kind == FileOperationKind.DELETE:
                destination.unlink()
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8", newline="\n")
        return tuple(operation.path for operation, _, _ in validated)
