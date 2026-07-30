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

Synchronous live submission requires an injected durable response sink. The
adapter writes the structured result and a schema-versioned identity/digest
receipt before returning control. Process-local task dictionaries are only a
same-process convenience and are never the live reconciliation authority.
Without a durable receipt, synchronous transport uncertainty is explicitly
non-reconcilable and requires an operator; ASCOS does not claim the Responses
API can search by an ASCOS idempotency key.

Patch application has its own durable effect. Files are fully validated, staged
and fsynced inside the managed workspace, then replaced atomically one at a
time. Completed replacements are checkpointed. Multi-file application is not a
transaction: restart inspection distinguishes none, all, partial, and divergent
state before continuing.
