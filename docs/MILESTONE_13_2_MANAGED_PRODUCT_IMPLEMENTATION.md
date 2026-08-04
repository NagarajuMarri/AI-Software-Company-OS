# Milestone 13.2 — Managed Product Implementation Pipeline

The `runtime.managed_product_implementation` package orchestrates implementation through injected provider, workspace, push, and pull-request ports. It never invokes Codex or another concrete implementation provider directly.

Every transition and its workspace, verification, commit, push, pull-request, review-package, and resume evidence can be persisted atomically. Verification is ordered and fail-fast. Git commits validate repository-relative paths, pushes reject protected branches and force-push behavior is absent, and pull requests are always drafts.

Task identity and approved scope are immutable after creation. Workspaces reject traversal and symlink escapes, use isolated Git configuration, verify the exact base SHA, and retain uncertain state for reconciliation. Verification commands use an executable allow-list, an isolated environment, bounded/redacted output, and commit/diff-bound evidence. Required `FAIL` or `UNKNOWN` results block commits.

Commit and push services independently validate protected branches, approved paths, repository identity, branch identity, and recorded SHA. Ambiguous push outcomes are recorded as reconciliation-required. Draft pull-request records bind base branch, head branch, and head SHA and reject duplicate creation.

The pipeline's successful automation boundary is `WAITING_FOR_HUMAN_REVIEW`. It exposes no merge operation. A separate human-reviewed process may later record approval and completion; completed records are immutable.

Human approval requires a named reviewer and current commit-bound evidence. Self-approval is rejected unless a caller supplies an explicit governance-policy override. Approval remains separate from merge and deployment.

Cleanup supports keep, on-success, and always policies. Workspaces are cloned into deterministic task paths, checked against the requested commit SHA, supplied a credential-isolated environment, and may have remotes removed.
