from dataclasses import dataclass

from runtime.persistence.postgresql.exceptions import PostgreSQLSchemaError


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(1, (
        "CREATE TABLE IF NOT EXISTS ascos_schema_version "
        "(singleton SMALLINT PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)",
        "INSERT INTO ascos_schema_version(singleton, version) VALUES(1,0) "
        "ON CONFLICT(singleton) DO NOTHING",
        "CREATE TABLE IF NOT EXISTS runtime_instances "
        "(runtime_id TEXT PRIMARY KEY, state_version BIGINT NOT NULL, "
        "checkpoint JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL)",
        "CREATE TABLE IF NOT EXISTS runtime_events "
        "(event_id TEXT PRIMARY KEY, runtime_id TEXT NOT NULL, "
        "global_position BIGSERIAL UNIQUE, aggregate_id TEXT NOT NULL, "
        "aggregate_sequence BIGINT NOT NULL, payload JSONB NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL, "
        "UNIQUE(runtime_id, aggregate_id, aggregate_sequence))",
        "CREATE TABLE IF NOT EXISTS outbox_operations "
        "(operation_id TEXT PRIMARY KEY, runtime_id TEXT NOT NULL, task_id TEXT NOT NULL, "
        "status TEXT NOT NULL, priority INTEGER NOT NULL, available_at TIMESTAMPTZ NOT NULL, "
        "created_at TIMESTAMPTZ NOT NULL, provider_id TEXT NOT NULL, operation_type TEXT NOT NULL, "
        "idempotency_key TEXT NOT NULL UNIQUE, payload JSONB NOT NULL, "
        "claim_owner TEXT, claim_token_hash TEXT, claim_expires_at TIMESTAMPTZ, "
        "fencing_token BIGINT NOT NULL DEFAULT 0, version BIGINT NOT NULL DEFAULT 0)",
        "CREATE INDEX IF NOT EXISTS idx_outbox_claim "
        "ON outbox_operations(status, available_at, priority, created_at, operation_id)",
        "CREATE INDEX IF NOT EXISTS idx_outbox_task ON outbox_operations(task_id)",
        "CREATE INDEX IF NOT EXISTS idx_outbox_runtime ON outbox_operations(runtime_id)",
        "CREATE TABLE IF NOT EXISTS worker_registrations "
        "(worker_instance_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, runtime_id TEXT NOT NULL, "
        "status TEXT NOT NULL, heartbeat_expires_at TIMESTAMPTZ NOT NULL, "
        "canonical_state JSONB NOT NULL, version BIGINT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS idx_worker_expiry "
        "ON worker_registrations(status, heartbeat_expires_at)",
        "CREATE TABLE IF NOT EXISTS provider_health "
        "(provider_id TEXT NOT NULL, capability TEXT NOT NULL, status TEXT NOT NULL, "
        "canonical_state JSONB NOT NULL, version BIGINT NOT NULL, "
        "PRIMARY KEY(provider_id, capability))",
        "CREATE INDEX IF NOT EXISTS idx_provider_health_status ON provider_health(status)",
    )),
)

POSTGRESQL_MIGRATION_LOCK_ID = 0x4153434F53


def _validate_migrations(migrations):
    versions = [migration.version for migration in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise ValueError("PostgreSQL migrations must be contiguous from version 1")
    if any(not migration.statements for migration in migrations):
        raise ValueError("PostgreSQL migrations must contain statements")


class PostgreSQLMigrator:
    def __init__(self, connection_factory, *, migrations=None):
        self.connection_factory = connection_factory
        self.migrations = tuple(MIGRATIONS if migrations is None else migrations)
        _validate_migrations(self.migrations)

    def upgrade(self):
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (POSTGRESQL_MIGRATION_LOCK_ID,),
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ascos_schema_version "
                    "(singleton SMALLINT PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL)"
                )
                cursor.execute(
                    "INSERT INTO ascos_schema_version VALUES(1,0) "
                    "ON CONFLICT(singleton) DO NOTHING"
                )
                cursor.execute(
                    "SELECT version FROM ascos_schema_version WHERE singleton=1 FOR UPDATE"
                )
                current = cursor.fetchone()[0]
                target = self.migrations[-1].version if self.migrations else 0
                if current > target:
                    raise PostgreSQLSchemaError("PostgreSQL schema is newer")
                for migration in self.migrations:
                    if migration.version <= current:
                        continue
                    for statement in migration.statements:
                        cursor.execute(statement)
                    cursor.execute(
                        "UPDATE ascos_schema_version SET version=%s WHERE singleton=1",
                        (migration.version,),
                    )
            return target
        finally:
            connection.close()
