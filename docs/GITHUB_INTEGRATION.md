# GitHub Integration

Outbox handlers use stable idempotency keys for GitHub operations where the
adapter supports them. Uncertain draft-PR outcomes require lookup and
reconciliation; merge is intentionally absent from the handler set.

The GitHub contract returns typed repository, branch, pull-request, and CI
models rather than HTTP or SDK payloads. `InMemoryGitHubProvider` provides
deterministic offline behavior. `CallableGitHubProvider` is the real-adapter
boundary and accepts an injected client; it stores no token.

PR creation is draft-first. Ready-for-review and merge are distinct, and merge
requires an explicit approval policy plus successful CI. No runtime workflow
automatically merges a PR.
