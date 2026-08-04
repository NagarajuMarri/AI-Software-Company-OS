# Runtime Roadmap

# Milestone 14.0

Product Requirements Management adds first-class requirements and PRDs with controlled lifecycle,
versioning, approval, locking, supersession, revision history, deterministic diffs, validation,
roadmap derivation, decision logs, atomic persistence, and requirement-to-release traceability. The
Spoken English AI PRD v1.0 is the locked product baseline. Future implementation milestones must
resolve approved requirement IDs before materialisation.

# Milestone 12.4

Add the controlled coding-provider boundary and prepare Personalised Daily
Speaking Practice Session as the first real Spoken English AI workflow through
ASCOS. The optional live adapter is deny-by-default; offline tests prove
durability, context, patch, progress, reconciliation, and security controls
without modifying the product repository.

# Milestone 12.3B

The Managed Product Execution Bridge adds separately approved execution plans,
runtime mappings, isolated workspaces, deterministic coding tasks, conservative
change policy, quality gates, review evidence, explicit completion review, and
draft-only repository effects. Live coding providers, automatic merge,
deployment, release, and production workspace infrastructure remain future
work.

# Milestone 12.3A

The Managed Product Planning Bridge connects registered identity, structural
knowledge, and deterministic project management through reviewed requests,
bounded context, provider-neutral proposals, explicit approval, and safe
materialisation. Runtime execution and live LLM planning remain future work.

# Milestone 12.2

The Project Knowledge Engine adds deterministic, read-only repository scanning,
structural symbol and dependency knowledge, statistics, queries, atomic
ASCOS-controlled persistence, and CLI access. Semantic AI and autonomous coding
remain future work.

# Milestone 12.1

The AI Project Manager adds deterministic milestone and task state,
dependency-aware next actions, integer progress, decisions, notes, risks,
typed transitions, atomic project-isolated JSON persistence, a Python API, and
CLI operations. It does not add LLM planning, autonomous agents, product
business logic, or product-repository writes.

# Milestone 12.0

The project registry establishes stable managed-product identity, repository
routing and lifecycle metadata, duplicate protection, registration events,
composition-root access, and optional atomic JSON persistence.
`spoken-english-ai` is demonstrated as the first managed product without
coupling ASCOS to or modifying its repository. Project-scoped execution,
lifecycle transition services, and database persistence remain future work.

Milestone 11.3E adds durable outbox repositories, fenced worker claims,
idempotent dispatch/application, deterministic retry, dead-letter controls,
reconciliation, crash recovery, supervisor health, and safe metrics. A future
milestone may add real worker processes and PostgreSQL locking verification.

Milestone 11.3D establishes safe local execution, workspace and Git isolation,
offline GitHub contracts, coding-agent provider selection, durable external
task tracking, reconciliation, and explicit human approval. Worker processes,
distributed queues, and a supported production Codex/OpenAI adapter remain
future milestones.

Milestone 11.3C delivers transactional SQLite checkpoints/events, optimistic
concurrency, runtime leases, fencing, and restart recovery. PostgreSQL remains
a future provider behind the same contracts.

- 11.3A: deterministic end-to-end software delivery workflow.
- 11.3B: provider-neutral persistence, file checkpoints, and restart recovery.
- Future: process-safe locking, database-backed providers, incremental
  snapshots, retention policies, encrypted backups, and disaster-recovery
  automation.

Milestone 11.3B deliberately adds no database, cloud store, broker, or async
runtime.
# Milestone 11.3F

Process worker lifecycle, durable registration and heartbeat, provider health,
circuit breaking, deterministic routing, and an optional PostgreSQL concurrency
adapter are implemented. A future milestone may add deployment-specific composition
and broader real-PostgreSQL soak testing; it must not weaken explicit-start,
operator-control, idempotency, or fencing guarantees.
