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
