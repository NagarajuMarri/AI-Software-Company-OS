# Coding-Agent Providers

Coding-agent providers are execution adapters, separate from the domain
`AgentRegistry`. The registry selects available providers deterministically by
priority and requested capability. Requests and results are typed and contain
allowed commands, paths, acceptance criteria, progress, changed paths, tests,
and artifact references.

The deterministic provider simulates success, retryable/permanent failure,
timeout, cancellation, and progress. It is not a production Codex adapter.
Real Codex/OpenAI integration requires a supported external invocation/API
mechanism and belongs behind the same contract without persisting its client or
credentials.
