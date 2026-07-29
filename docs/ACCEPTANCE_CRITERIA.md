# Runtime Persistence Acceptance Criteria

# Milestone 12.3A acceptance

Planning must use registered identity and an explicit current knowledge snapshot,
produce strictly validated dependency-safe proposals, require separate
actor-attributed approval, persist only bounded structured state, materialise
only through `AIProjectManager`, and create no product repository or runtime
execution side effect.

# Milestone 12.2 acceptance

Knowledge indexing must be deterministic, text-only, ignore common generated
and version-control paths, use Python AST safely, preserve stable query and
serialization ordering, validate registry identity, persist only under
ASCOS-controlled storage, and never modify a product repository.

# Milestone 12.1 acceptance

Manager state must reference a registered project, permit only validated and
atomic task/milestone transitions, plan executable tasks deterministically,
calculate stable integer progress, round-trip all supported records through
schema-versioned atomic JSON under ASCOS-controlled storage, expose Python and
CLI operations, and never write to a managed product repository.

Milestone 11.3E requires atomic intent/event creation, deterministic exclusive
claims, hashed claim tokens, stale-fencing rejection, at-least-once dispatch,
idempotent local result application, bounded retry, dead-letter/operator audit,
uncertain-outcome reconciliation, restart safety, provider-neutral persistence,
and no automatic approval, merge, or deployment.

Milestone 11.3D requires argument-array command execution without a shell,
workspace containment, protected Git branches, typed offline GitHub behavior,
deterministic coding-provider selection, explicit side-effect records,
reconciliation after interruption, persisted task/review state, credential
exclusion, and approval that neither completes nor merges automatically.

Milestone 11.3C requires deterministic migrations, atomic checkpoint/event
commits, stale-writer rejection, durable event ordering, hashed lease
identities with UTC expiry and fencing, restart without historical
re-emission, legacy-provider compatibility, and executable examples.

A persistence implementation is acceptable when:

- canonical serialization is deterministic and rejects unsupported values;
- checkpoints are immutable, versioned, and SHA-256 verified;
- writes are atomic and partial temporary files are never listed;
- invalid references or event sequences reject the complete restore;
- all runtime identifiers, lifecycle states, capacity, history, and events
  survive restart;
- historical events are not re-emitted;
- new event sequences continue after restart;
- persistence-disabled construction remains compatible;
- failures are surfaced and never falsely reported as durable;
- approval and assignment completion remain explicit.
# Milestone 11.3F acceptance

The worker runtime must start only explicitly, use unique instance identities,
heartbeat through durable registries, stop gracefully, and preserve outbox fencing.
Provider routing must reject disabled, open, and saturated providers deterministically.
PostgreSQL claiming must use atomic `FOR UPDATE SKIP LOCKED`; real integration results
may only be claimed when the optional test database is configured.

# Milestone 12.0 acceptance

Managed projects require stable validated identities, normalized repository
uniqueness, deterministic lookup and lifecycle filtering, registration events,
composition-root access, and restart-safe atomic file persistence. The first
managed product registration must reference Spoken English AI portably and
must not modify its repository.
