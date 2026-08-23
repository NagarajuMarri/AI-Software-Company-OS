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

The Codex SDK completion preflight proves one explicitly selected, secret-safe
billing mode and one separately confirmed read-only live invocation. The
governed Codex SDK execution adapter then maps an approved coding task to one
identifiable Codex thread. It supports a customer's ChatGPT-authenticated session
only on that customer's trusted local runner, or a company's Platform API key
on a trusted runner. It verifies or isolates the selected authentication mode
and never silently falls back between billing sources.

Codex runs with read-only sandboxing and denied approval requests. It returns
schema-constrained file operations rather than receiving product-write, Git,
GitHub, merge, deployment, release, or approval authority. ASCOS persists the
result and billing source, verifies that the workspace stayed unchanged during
the model turn, validates paths and change policy, applies accepted operations,
and runs quality gates through the existing controlled execution boundary.
Both `--allow-live-provider` and `--confirm-usage-consumption` are required for
the charged turn. See `CODEX_EXECUTION_PREFLIGHT.md` and
`CODEX_SDK_EXECUTION.md`.
