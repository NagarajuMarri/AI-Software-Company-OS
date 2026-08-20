# Runtime Persistence Operations

Monitor outbox depth, oldest pending age, expired claims, reconciliation count,
and dead letters. Retry and abandonment require an authenticated operator
identity and reason. Reconcile uncertain dispatch before retrying it; never
assume a timeout means the provider did nothing.

External operations that restore in `RECONCILIATION_REQUIRED` need remote-state
inspection before retry. Operators should correlate the operation ID, task ID,
provider task reference, branch, and audit records; never copy credentials into
diagnostics. Kill timed-out processes, clean abandoned caller-owned workspaces,
and treat provider output and patches as untrusted.

Use SQLite's online backup API or confirmed writer quiescence; copying only the
main file during WAL writes is unsafe. Restore into a separate path and verify
schema, digest, state version, and event position. Back up before migrations.
On conflicts reload and reconsider; use bounded backoff for busy errors. Break
only expired leases.

## Save and restore

Configure a caller-owned storage directory and stable `runtime_id`. Save an
explicit checkpoint after a significant successful operation, or enable the
automatic policy. On restart, create a fresh container with the same provider
and runtime ID, load the latest valid checkpoint, then call `restore_runtime`.

## Backup

Back up completed `*.checkpoint.json` files only. Copying can occur while the
runtime is idle; temporary `.checkpoint-*.tmp` files are incomplete and must
not be restored. Preserve file permissions and verify checkpoints by loading
them before relying on a backup.

## Corruption and recovery

Digest mismatch or malformed content raises a corruption/integrity exception.
`load_latest_checkpoint` skips corrupted files and returns the newest valid
checkpoint. If none is valid, stop the runtime and restore a verified backup.
Never edit checkpoint payloads manually.

## Limitations

The file provider assumes one writer process. It supplies atomic replacement,
restrictive `0600` permissions where supported,
and best-effort fsync but no distributed lock, encryption, retention, or remote
replication. Production deployments should use a future transactional provider
and an explicit backup/recovery plan.

Strict latest restore is the default and stops on a corrupt newest checkpoint.
Recovery mode may fall back, but operators must inspect the reported skipped
files. Symlink and permission guarantees vary by operating system; keep the
storage directory private and controlled by the runtime account.

# Process-worker operations

Workers are started explicitly with bounded operation, idle, and runtime limits.
Operators can inspect registrations, request shutdown, and scan stale heartbeats.
Provider disable, enable, and circuit reset require an operator identity and reason.

## PostgreSQL validation and operating limits

The CI PostgreSQL job is always scheduled and uses an isolated PostgreSQL 16 service.
Its real-server migration, concurrency, and recovery result is the Day 4 adapter
evidence. A local run without a securely supplied `ASCOS_POSTGRES_TEST_URL` skips the
integration module and must be reported as skipped, not passed.

Use only a disposable database for local integration tests. Supply its DSN through a
secret mechanism, never command output or committed configuration, and install the
`postgres` project extra. Before any deployment-oriented experiment, back up the target,
verify the expected schema version, and monitor migration errors, version conflicts,
outbox age, expired claims, and connection health. Configuration currently validates
pool-size bounds but does not construct a connection pool; pool composition and sizing
evidence are still required.

The PostgreSQL repositories are not wired into the runtime composition root and do not
yet implement the complete persistence and durable-outbox provider contracts. The CI
database is not backup, restore, failover, TLS, credential-rotation, capacity, or soak
evidence. Keep production usage blocked until those capabilities, composition-level
restart tests, and an operator-reviewed recovery procedure are implemented and
validated.
