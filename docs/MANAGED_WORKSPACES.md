# Managed Workspaces

Managed workspaces are caller-rooted, uniquely identified copies resolved only
from `ProjectRegistry.local_path`; identity is never inferred from the current
directory. Preparation rejects missing sources, symlinks, nested unrelated Git
repositories, traversal, and paths outside the workspace root.

The registered remote identity and approved base branch are persisted with
`REQUESTED`, `PREPARING`, `READY`, `IN_USE`, `DIRTY`, `ARCHIVED`, `CLEANED`,
`FAILED`, or `RECONCILIATION_REQUIRED`. Git uses argument arrays through the
safe command runner. The base must be clean and expected before branch creation.
Main/master are protected; force push, deletion, merge, deployment, and
credential persistence are unsupported.

Before copying, managed execution persists workspace intent containing project,
plan/version, workspace ID, registered repository identity, exact destination,
base branch, and a deterministic source-tree digest. A restart inspects that
exact destination and digest. An exact copy is adopted and its workspace record
completed; a missing copy can be retried; a partial, foreign, symlinked, or
divergent copy requires reconciliation and is never overwritten automatically.

Branch intent is persisted before `git switch -c` with workspace/repository,
base branch, expected base SHA, and feature branch. Recovery accepts only the
expected feature ref at that SHA. Existing divergent branches are not reset,
deleted, force-updated, or rebased.
