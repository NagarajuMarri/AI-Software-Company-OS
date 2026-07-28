# Runtime Roadmap

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
