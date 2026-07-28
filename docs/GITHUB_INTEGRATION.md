# GitHub Integration

The GitHub contract returns typed repository, branch, pull-request, and CI
models rather than HTTP or SDK payloads. `InMemoryGitHubProvider` provides
deterministic offline behavior. `CallableGitHubProvider` is the real-adapter
boundary and accepts an injected client; it stores no token.

PR creation is draft-first. Ready-for-review and merge are distinct, and merge
requires an explicit approval policy plus successful CI. No runtime workflow
automatically merges a PR.
