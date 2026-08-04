# Milestone 13.2 — Managed Product Implementation Pipeline

The `runtime.managed_product_implementation` package orchestrates implementation through injected provider, workspace, push, and pull-request ports. It never invokes Codex or another concrete implementation provider directly.

Every transition and its workspace, verification, commit, push, pull-request, review-package, and resume evidence can be persisted atomically. Verification is ordered and fail-fast. Git commits validate repository-relative paths, pushes reject protected branches and force-push behavior is absent, and pull requests are always drafts.

The pipeline's successful automation boundary is `WAITING_FOR_HUMAN_REVIEW`. It exposes no merge operation. A separate human-reviewed process may later record approval and completion; completed records are immutable.

Cleanup supports keep, on-success, and always policies. Workspaces are cloned into deterministic task paths, checked against the requested commit SHA, supplied a credential-isolated environment, and may have remotes removed.
