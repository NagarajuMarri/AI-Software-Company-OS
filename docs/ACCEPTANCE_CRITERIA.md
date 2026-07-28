# Runtime Persistence Acceptance Criteria

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
