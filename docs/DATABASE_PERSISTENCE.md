# Database Persistence

ASCOS provides a relational persistence boundary backed by SQLite for local
operation and deterministic verification. Domain services depend only on
persistence contracts; database connections and rows never enter domain
models.

Schema version 1 contains runtime instances, checkpoints, ordered events,
state-version history, leases, and operation records. Foreign keys and unique
constraints protect checkpoint identity, global positions, event IDs, and
aggregate sequences.

A checkpoint commit uses one `BEGIN IMMEDIATE` transaction to verify the
expected state version, append new events, store the canonical checkpoint,
advance metadata, and record the operation. Version 0 means no durable commit;
the first successful commit is version 1. Failures roll back everything.
Stale writers receive `RuntimeVersionConflictError`; callers must reload,
reconsider, and explicitly retry. There is no last-write-wins behavior.

Canonical checkpoint digests cover identity, metadata, event position, and
state. Strict loading stops on corruption; recovery mode may select an older
valid checkpoint and exposes skipped IDs. Restoration validates an isolated
graph and never republishes historical events.

Migration from empty to schema version 1 is automatic and repeatable. Newer or
unknown schemas are rejected. SQLite WAL is intended for one host and moderate
concurrency. A future PostgreSQL provider retains these contracts while
isolating dialect SQL, isolation, lock handling, and migrations.
