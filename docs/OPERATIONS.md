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
PostgreSQL integration verification is optional and must be reported as skipped when
no secure test database reference is configured.
