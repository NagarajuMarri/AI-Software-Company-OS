# Runtime Persistence Operations

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

The file provider assumes one writer process. It supplies atomic replacement
and best-effort fsync but no distributed lock, encryption, retention, or remote
replication. Production deployments should use a future transactional provider
and an explicit backup/recovery plan.
