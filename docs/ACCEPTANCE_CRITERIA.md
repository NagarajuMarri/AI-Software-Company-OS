# Runtime Persistence Acceptance Criteria

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
