# Runtime Persistence

The optional SQLite provider stores checkpoints and their event suffix in one
transaction. State versions advance once per durable checkpoint; optional
leases add expiry and fencing. In-memory and file providers remain supported,
but the file provider does not claim multi-process safety. See
[DATABASE_PERSISTENCE.md](DATABASE_PERSISTENCE.md).

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

The digest covers the canonical payload and all restoration-critical metadata:
checkpoint ID, runtime ID, schema version, UTC creation time, reason, and last
event position. Loading rejects malformed JSON, unknown schemas, digest
mismatches, unsafe identifiers, invalid event
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

Latest-checkpoint loading is strict by default: corruption of the newest file
stops restoration. Explicit recovery mode may select an older valid checkpoint;
the returned `CheckpointSelection` records every skipped corrupt filename.

Automatic checkpoints run after the in-memory domain transaction commits. If
the checkpoint fails, ASCOS raises `PersistenceCommitError`: domain state is
committed but explicitly not reported as durable. The failure is never
ignored.

`PersistenceCommitResult` distinguishes durable commits, committed but
uncheckpointed state, rollback, conflict, and failure without parsing exception
text. Restoration separately reports active assignments lacking a compatible
executor; executors are behavior and are never reconstructed from data.

Future database or cloud providers must implement the same persistence
contracts and validation rules without changing domain services.

Schema version 1 has an explicit validation boundary. Future older versions
require a migration adapter before construction; newer or unknown versions and
unknown type discriminators are rejected rather than interpreted.
