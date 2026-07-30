# Coding Context Policy

Context includes only approved plan/task metadata, acceptance criteria, path
policy, gate argument arrays, bounded knowledge evidence, and bounded UTF-8
candidate files. It excludes credential/environment files, keys, binaries,
symlinks, forbidden/unrelated files, host paths, unrestricted Git history, and
repository dumps.

Limits cover files, bytes per file, total bytes, evidence items, and prompt
bytes. Canonical content produces a stored SHA-256 digest; raw live prompts are
not persisted.

Returned operations accept only relative UTF-8 text paths inside the workspace.
Traversal, absolute paths, `.git`, protected paths, symlinks, binary content,
duplicates, overflow, deletion, and mode changes are rejected by default.
Provider commands are never executed.
