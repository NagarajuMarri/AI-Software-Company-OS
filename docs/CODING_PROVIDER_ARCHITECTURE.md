# Coding Provider Architecture

Milestone 12.4 adds a typed provider boundary under `runtime/coding_providers/`.
Providers declare capabilities, validate injected configuration, submit and
inspect tasks, return ordered progress and structured results, accept
cancellation, and reconcile deterministic idempotency keys. They cannot approve
plans/evidence, access arbitrary host files, commit, push, create or merge pull
requests, deploy, or read product credential files.

The registry rejects duplicate, unknown, disabled, unhealthy, or
capability-incompatible providers. The deterministic provider is the offline
default. The optional OpenAI Responses API adapter is disabled until an operator
supplies an approved model, environment credential reference,
`--allow-live-provider`, and separate live-operation confirmation.

The live adapter receives only a bounded context package and returns structured
text file operations. ASCOS validates and applies them, then independently
inspects Git state. No SDK dependency, hosted shell, provider command execution,
or unrestricted repository access is introduced.
