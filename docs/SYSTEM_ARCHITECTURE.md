# System Architecture

## Live coding-provider boundary

Milestone 12.4 adds a typed registry, durable operations/progress/results,
bounded context, validated text patches, usage limits, deterministic provider,
and optional deny-by-default OpenAI Responses API adapter. Submission uses
durable intent and exact reconciliation, not cross-system atomicity. Accepted
results come from ASCOS-applied patches and independent Git observation before
existing gates, evidence, review, and repository controls resume.

Live synchronous responses cross a mandatory durable receipt sink before the
adapter returns. A missing receipt after uncertainty is operator-reconciled, not
automatically resubmitted. Patch and cancellation effects have independent
schema-versioned lifecycles. Per-file replacement is atomic where the host
filesystem supports it, but ASCOS does not claim multi-file or cross-system
atomicity.

## Managed product execution

Milestone 12.3B follows completed planning materialisation. It translates an
exact, separately approved execution plan into traceable runtime work, an
isolated workspace, deterministic coding tasks, allow-listed quality gates,
integrity-digested review evidence, separately approved repository effects, and
a draft pull request. Project tasks, runtime work, domain agents, provider
tasks, Git/GitHub effects, and human decisions remain separate types and stores.

External effects use schema-versioned prepared/in-progress/completed/uncertain
records and inspection-based reconciliation rather than a cross-system
transaction. Workspace trees, runtime mappings, Git refs/commits/remotes, and
draft PRs are accepted only when their deterministic identities match durable
intent; divergence becomes operator-visible `RECONCILIATION_REQUIRED`.
Accepted coding results and canonical evidence digests form the boundary
between provider output, gates, human completion review, and repository
effects. The default path is offline and deterministic; no live provider,
merge, deployment, or workflow release is composed. See
`docs/MANAGED_PRODUCT_EXECUTION.md` and
`docs/MANAGED_EXECUTION_RECONCILIATION.md`.

## Managed product planning

The planning bridge sits between the Project Registry, persisted Project
Knowledge Engine snapshots, and AI Project Manager. Its provider contract
produces proposals only. Validation and human approval precede idempotent
materialisation into inactive manager milestones; runtime orchestration remains
a separate, future boundary. See `docs/MANAGED_PRODUCT_PLANNING.md`.

Manager and planning JSON files are independent atomic stores, not one
transaction. Materialisation therefore uses a durable operation record and
restart reconciliation: expected manager content is verified exactly before
the operation and proposal are completed. Partial or divergent state is surfaced
for reconciliation rather than overwritten or duplicated.

The `ProjectRegistry` is the managed-product identity boundary. It records
repository routing and lifecycle metadata but performs no repository I/O.
Product-specific code remains outside ASCOS. Milestone 12.0 composes one
in-memory registry per runtime and offers an atomic file adapter behind the same
contract. Database persistence and project-scoped workflow routing remain
separate future capabilities.

The outbox separates durable intent, claim/dispatch, provider execution, local
result application, reconciliation, and operator control. Provider calls occur
outside rollbackable local transactions. Workers are explicit runtime objects,
not automatically started services.

External execution is split into tool, workspace, Git, GitHub, coding-agent,
and task-coordination boundaries. Domain services never import subprocess,
SQLite, GitHub SDK, OpenAI SDK, or operating-system shell details. Coding-agent
providers are execution infrastructure and are intentionally distinct from
software-company domain agents.

`DatabasePersistenceProvider` is composed through the provider-neutral
persistence boundary. It owns SQL, migrations, optimistic versions, and
optional leases; no database model leaks into domain services. A PostgreSQL
provider can therefore preserve domain contracts.

`ASCOSRuntimeContainer` is the composition root. Its default configuration is
fully in-memory. Optional persistence adds `RuntimePersistenceService` and a
caller-supplied `PersistenceProvider`; no singleton or hard-coded path exists.

The domain graph remains RuntimeEngine → AgentRegistry → Orchestrator →
ExecutionService/ExecutionRecoveryService → SoftwareDeliveryWorkflowService.
One EventStore, EventPublisher, and transaction coordinator are shared.

Persistence observes successful workflow boundaries through a post-transaction
callback. Explicit saves are always available. Capture and restoration live
outside domain models, preserving the provider-neutral boundary.

The file provider is a development and test implementation. A future database
provider can implement checkpoint, state, event, and persistence-transaction
contracts while preserving checkpoint schema and integrity validation.
# Milestone 11.3F runtime boundary

Explicit spawned workers reconstruct dependencies from safe references. Worker
registration and heartbeat persistence are separate from outbox claim ownership and
fencing. Provider health and deterministic routing are provider-neutral services.
PostgreSQL-specific migrations, transactions, and locking remain isolated beneath
the persistence adapter; SQLite remains the local-development provider.
