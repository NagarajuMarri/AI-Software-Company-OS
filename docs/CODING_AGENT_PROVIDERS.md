# Coding-Agent Providers

Coding-agent submission and cancellation may be dispatched through the outbox.
Stable task/operation identity supports reconciliation after timeout or worker
crash; no live provider client or key is persisted.

Coding-agent providers are execution adapters, separate from the domain
`AgentRegistry`. The registry selects available providers deterministically by
priority and requested capability. Requests and results are typed and contain
allowed commands, paths, acceptance criteria, progress, changed paths, tests,
and artifact references.

The deterministic provider simulates success, retryable/permanent failure,
timeout, cancellation, and progress. It is not a production Codex adapter.

The optional Codex SDK completion preflight proves one explicitly selected,
secret-safe billing mode and one separately confirmed read-only live invocation.
It supports a customer's ChatGPT-authenticated session only on that customer's
trusted local runner, or a company's Platform API key on a trusted runner. It
verifies or isolates the selected authentication mode and never silently falls
back between billing sources. It does not generate or apply product code. The
next completion module must adapt governed coding tasks to resumable Codex
threads behind this same contract without persisting the SDK client,
credentials, raw provider responses, or unrestricted authority. See
`CODEX_EXECUTION_PREFLIGHT.md`.
