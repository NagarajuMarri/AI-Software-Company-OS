"""Component-aware path policy and no-link workspace traversal."""

import os
import stat
from pathlib import Path, PurePosixPath

from runtime.coding_providers.errors import ProviderPolicyError
from runtime.managed_execution.policy import safe_relative_path


def normalized_parts(value):
    normalized = safe_relative_path(value)
    return PurePosixPath(normalized).parts


def matches_prefix(path, prefix):
    path_parts = normalized_parts(path)
    prefix = prefix.replace("\\", "/").rstrip("/")
    if not prefix:
        return True
    prefix_parts = normalized_parts(prefix)
    return path_parts[:len(prefix_parts)] == prefix_parts


def allowed_path(path, allowed, forbidden):
    if allowed and not any(matches_prefix(path, prefix) for prefix in allowed):
        return False
    return not any(matches_prefix(path, prefix) for prefix in forbidden)


def secure_destination(root, relative, *, allow_missing_leaf=True):
    root = Path(root).resolve()
    parts = normalized_parts(relative)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        if not current.exists() and not current.is_symlink():
            if index < len(parts) - 1 and not allow_missing_leaf:
                raise ProviderPolicyError("Workspace path component is missing")
            continue
        info = current.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or attributes & reparse:
            raise ProviderPolicyError("Workspace path contains a link or reparse point")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ProviderPolicyError("Workspace parent is not a directory")
        if index == len(parts) - 1 and not (
            stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
        ):
            raise ProviderPolicyError("Workspace path is a special file")
    absolute = os.path.abspath(current)
    if os.path.commonpath((str(root), absolute)) != str(root):
        raise ProviderPolicyError("Workspace path escapes root")
    return current
