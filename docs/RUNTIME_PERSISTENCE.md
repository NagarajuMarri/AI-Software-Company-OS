# Runtime Persistence

ASCOS persistence is an optional layer around the default deterministic
in-memory runtime. Domain services depend on provider-neutral contracts; they
do not read JSON files or depend on a database.

## Checkpoint schema

Schema version 1 stores a `RuntimeCheckpoint` with checkpoint and runtime
identity, UTC creation time, reason, last event position, SHA-256 state digest,
and an immutable runtime-state payload. The payload contains packages, work
items, artifact identifiers, agents and capabilities, assignments, executions,
recovery records, workflow requests and workflows, plus the complete event
stream.

Canonical JSON uses sorted keys, compact separators, ISO-8601 UTC datetimes,
stable enum values, and explicit type discriminators for non-JSON scalar
values. Pickle and dynamic type imports are prohibited.

## Integrity and restoration

The digest covers the canonical payload. Loading rejects malformed JSON,
unknown schemas, digest mismatches, unsafe identifiers, invalid event
sequences, and broken aggregate references. Restoration builds and validates a
temporary object graph before replacing any live collections. Historical
events are inserted directly and are never republished.

After restoration, new events use the restored store, so aggregate sequences,
generated IDs, correlations, causation, and publication order continue.

## Durability and failure policy

The file provider writes a temporary file, flushes and fsyncs it where
available, then atomically renames it. A checkpoint is visible only after the
rename. The provider is intentionally single-process; concurrent writers
require a future locking provider.

Automatic checkpoints run after the in-memory domain transaction commits. If
the checkpoint fails, ASCOS raises `PersistenceCommitError`: domain state is
committed but explicitly not reported as durable. The failure is never
ignored.

Future database or cloud providers must implement the same persistence
contracts and validation rules without changing domain services.
