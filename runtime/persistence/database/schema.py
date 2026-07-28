"""Versioned relational schema."""

DATABASE_SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runtime_instances (
    runtime_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
    current_state_version INTEGER NOT NULL CHECK(current_state_version >= 0),
    latest_checkpoint_id TEXT,
    latest_event_position INTEGER NOT NULL CHECK(latest_event_position >= 0),
    durability_status TEXT NOT NULL,
    latest_fencing_token INTEGER NOT NULL DEFAULT 0 CHECK(latest_fencing_token >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_checkpoints (
    checkpoint_id TEXT NOT NULL,
    runtime_id TEXT NOT NULL,
    checkpoint_schema_version INTEGER NOT NULL,
    state_version INTEGER NOT NULL CHECK(state_version >= 1),
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    last_event_position INTEGER NOT NULL CHECK(last_event_position >= 0),
    state_digest TEXT NOT NULL,
    canonical_payload TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    PRIMARY KEY(runtime_id, checkpoint_id),
    FOREIGN KEY(runtime_id) REFERENCES runtime_instances(runtime_id)
);
CREATE INDEX IF NOT EXISTS idx_checkpoint_order
ON runtime_checkpoints(runtime_id, state_version DESC, created_at DESC);
CREATE TABLE IF NOT EXISTS runtime_events (
    event_id TEXT PRIMARY KEY,
    runtime_id TEXT NOT NULL,
    global_position INTEGER NOT NULL CHECK(global_position >= 1),
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_sequence INTEGER NOT NULL CHECK(aggregate_sequence >= 1),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    correlation_id TEXT,
    causation_id TEXT,
    canonical_payload TEXT NOT NULL,
    UNIQUE(runtime_id, global_position),
    UNIQUE(runtime_id, aggregate_type, aggregate_id, aggregate_sequence),
    FOREIGN KEY(runtime_id) REFERENCES runtime_instances(runtime_id)
);
CREATE INDEX IF NOT EXISTS idx_event_position
ON runtime_events(runtime_id, global_position);
CREATE INDEX IF NOT EXISTS idx_event_aggregate
ON runtime_events(runtime_id, aggregate_type, aggregate_id, aggregate_sequence);
CREATE INDEX IF NOT EXISTS idx_event_correlation
ON runtime_events(runtime_id, correlation_id, global_position);
CREATE TABLE IF NOT EXISTS runtime_state_versions (
    runtime_id TEXT NOT NULL,
    state_version INTEGER NOT NULL CHECK(state_version >= 1),
    checkpoint_id TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    PRIMARY KEY(runtime_id, state_version),
    FOREIGN KEY(runtime_id, checkpoint_id)
        REFERENCES runtime_checkpoints(runtime_id, checkpoint_id)
);
CREATE INDEX IF NOT EXISTS idx_state_version
ON runtime_state_versions(runtime_id, state_version DESC);
CREATE TABLE IF NOT EXISTS runtime_leases (
    runtime_id TEXT PRIMARY KEY,
    lease_owner_id TEXT NOT NULL,
    lease_token_hash TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    renewed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    fencing_token INTEGER NOT NULL CHECK(fencing_token >= 1),
    FOREIGN KEY(runtime_id) REFERENCES runtime_instances(runtime_id)
);
CREATE INDEX IF NOT EXISTS idx_lease_expiration
ON runtime_leases(expires_at);
CREATE TABLE IF NOT EXISTS persistence_transactions (
    operation_id TEXT PRIMARY KEY,
    runtime_id TEXT NOT NULL,
    expected_state_version INTEGER NOT NULL,
    resulting_state_version INTEGER,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    committed_at TEXT,
    FOREIGN KEY(runtime_id) REFERENCES runtime_instances(runtime_id)
);
"""
