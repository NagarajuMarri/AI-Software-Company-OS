from datetime import datetime, timezone
import os
import pytest

from runtime.persistence.postgresql.connection import PostgreSQLConfiguration, connect
from runtime.persistence.postgresql.exceptions import PostgreSQLConnectionError
from runtime.persistence.postgresql.migrations import MIGRATIONS
from runtime.persistence.postgresql.outbox_repository import (
    CLAIM_SELECT_SQL, PostgreSQLOutboxRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class Transaction:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class Cursor:
    def __init__(self, rows): self.rows = iter(rows); self.calls = []
    def execute(self, sql, params=()): self.calls.append((sql, params))
    def fetchone(self): return next(self.rows)


class Connection:
    def __init__(self, rows): self.cursor_value = Cursor(rows); self.closed = False
    def transaction(self): return Transaction()
    def cursor(self): return self.cursor_value
    def close(self): self.closed = True


def test_claim_sql_uses_skip_locked():
    assert "FOR UPDATE SKIP LOCKED" in CLAIM_SELECT_SQL


def test_claim_sql_has_deterministic_order():
    assert "priority ASC, available_at ASC, created_at ASC, operation_id ASC" in CLAIM_SELECT_SQL


def test_claim_is_atomic_and_fenced():
    connection = Connection([("op-1", 4), (9,)])
    result = PostgreSQLOutboxRepository(lambda: connection, clock=lambda: NOW).claim_next("worker")
    assert result["operation_id"] == "op-1"
    assert result["fencing_token"] == 5
    assert connection.closed


def test_empty_claim_returns_none():
    connection = Connection([None])
    assert PostgreSQLOutboxRepository(lambda: connection, clock=lambda: NOW).claim_next("worker") is None


def test_raw_url_rejected_as_configuration():
    with pytest.raises(ValueError): PostgreSQLConfiguration("postgresql://u:p@host/db")


def test_pool_bounds_are_validated():
    with pytest.raises(ValueError):
        PostgreSQLConfiguration("test-database", minimum_pool_size=10, maximum_pool_size=2)


def test_connection_error_is_redacted():
    with pytest.raises(PostgreSQLConnectionError) as captured:
        connect(PostgreSQLConfiguration("test-database"), lambda _: "not-a-real-dsn")
    assert "not-a-real-dsn" not in str(captured.value)


def test_migrations_are_versioned_and_ordered():
    assert [item.version for item in MIGRATIONS] == sorted({item.version for item in MIGRATIONS})


@pytest.mark.parametrize("fragment", [
    "outbox_operations", "worker_registrations", "provider_health",
    "runtime_events", "runtime_instances",
])
def test_migration_contains_required_boundary(fragment):
    sql = " ".join(statement for migration in MIGRATIONS for statement in migration.statements)
    assert fragment in sql


@pytest.mark.skipif(
    not os.environ.get("ASCOS_POSTGRES_TEST_URL"),
    reason="ASCOS_POSTGRES_TEST_URL is not configured",
)
def test_postgresql_integration_environment_is_opt_in():
    assert os.environ.get("ASCOS_POSTGRES_TEST_URL")
