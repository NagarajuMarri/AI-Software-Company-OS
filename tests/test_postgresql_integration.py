"""Real PostgreSQL integration coverage for the bounded persistence adapter.

These tests deliberately require an external PostgreSQL server.  The normal
unit-test job skips this module; the PostgreSQL CI job supplies the URL and
therefore imports and exercises psycopg rather than a fake connection.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import os
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest


POSTGRES_TEST_URL = os.environ.get("ASCOS_POSTGRES_TEST_URL")
if not POSTGRES_TEST_URL:
    pytest.skip(
        "ASCOS_POSTGRES_TEST_URL is not configured",
        allow_module_level=True,
    )

# Do not make this an importorskip: when the integration job is enabled, a
# missing PostgreSQL driver is a broken test environment and must fail CI.
import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

from runtime.outbox.models import OutboxClaim  # noqa: E402
from runtime.persistence.postgresql import migrations as migration_module  # noqa: E402
from runtime.persistence.postgresql.exceptions import (  # noqa: E402
    PostgreSQLSchemaError,
    PostgreSQLVersionConflictError,
)
from runtime.persistence.postgresql.migrations import (  # noqa: E402
    Migration,
    PostgreSQLMigrator,
)
from runtime.persistence.postgresql.outbox_repository import (  # noqa: E402
    PostgreSQLOutboxRepository,
)
from runtime.persistence.postgresql.provider_health_repository import (  # noqa: E402
    PostgreSQLProviderHealthRepository,
)
from runtime.persistence.postgresql.runtime_repository import (  # noqa: E402
    PostgreSQLRuntimeEventInput,
    PostgreSQLRuntimeRepository,
)
from runtime.persistence.postgresql.worker_repository import (  # noqa: E402
    PostgreSQLWorkerRepository,
)


NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def postgresql_database():
    """Give each test an isolated schema and real independent connections."""

    schema_name = f"ascos_test_{uuid4().hex}"
    with psycopg.connect(POSTGRES_TEST_URL, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )

    def connection_factory():
        connection = psycopg.connect(POSTGRES_TEST_URL, autocommit=True)
        connection.execute(
            sql.SQL("SET search_path TO {}, pg_catalog").format(
                sql.Identifier(schema_name)
            )
        )
        connection.autocommit = False
        return connection

    try:
        yield connection_factory
    finally:
        with psycopg.connect(POSTGRES_TEST_URL, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema_name)
                )
            )


def _query_one(connection_factory, statement, parameters=()):
    with connection_factory() as connection:
        return connection.execute(statement, parameters).fetchone()


def _insert_outbox_operation(
    connection_factory,
    operation_id,
    *,
    priority=100,
    status="PENDING",
    available_at=NOW,
    created_at=NOW,
    claim_owner=None,
    claim_token_hash=None,
    claim_expires_at=None,
    fencing_token=0,
    version=0,
):
    with connection_factory() as connection:
        connection.execute(
            """
            INSERT INTO outbox_operations(
                operation_id, runtime_id, task_id, status, priority,
                available_at, created_at, provider_id, operation_type,
                idempotency_key, payload, claim_owner, claim_token_hash,
                claim_expires_at, fencing_token, version
            ) VALUES(
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                operation_id,
                "runtime-1",
                f"task-{operation_id}",
                status,
                priority,
                available_at,
                created_at,
                "github",
                "CREATE_PULL_REQUEST",
                f"idempotency-{operation_id}",
                Jsonb({"operation_id": operation_id}),
                claim_owner,
                claim_token_hash,
                claim_expires_at,
                fencing_token,
                version,
            ),
        )


def test_migration_is_fresh_idempotent_and_visible_after_restart(
    postgresql_database,
):
    migrator = PostgreSQLMigrator(postgresql_database)
    expected_version = migration_module.MIGRATIONS[-1].version

    assert migrator.upgrade() == expected_version
    assert PostgreSQLMigrator(postgresql_database).upgrade() == expected_version

    version = _query_one(
        postgresql_database,
        "SELECT version FROM ascos_schema_version WHERE singleton=1",
    )[0]
    tables = _query_one(
        postgresql_database,
        """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name IN (
              'runtime_instances',
              'runtime_events',
              'outbox_operations',
              'worker_registrations',
              'provider_health'
          )
        """,
    )[0]

    assert version == expected_version
    assert tables == 5


def test_concurrent_migrations_serialize_to_one_schema_version(
    postgresql_database,
):
    workers = 6
    barrier = Barrier(workers)

    def migrate():
        barrier.wait(timeout=10)
        return PostgreSQLMigrator(postgresql_database).upgrade()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        versions = list(executor.map(lambda _index: migrate(), range(workers)))

    expected_version = migration_module.MIGRATIONS[-1].version
    stored_version = _query_one(
        postgresql_database,
        "SELECT version FROM ascos_schema_version WHERE singleton=1",
    )[0]
    assert versions == [expected_version] * workers
    assert stored_version == expected_version


def test_migration_rejects_a_newer_database_without_changing_it(
    postgresql_database,
):
    migrator = PostgreSQLMigrator(postgresql_database)
    migrator.upgrade()
    newer_version = migration_module.MIGRATIONS[-1].version + 1
    with postgresql_database() as connection:
        connection.execute(
            "UPDATE ascos_schema_version SET version=%s WHERE singleton=1",
            (newer_version,),
        )

    with pytest.raises(PostgreSQLSchemaError, match="newer"):
        PostgreSQLMigrator(postgresql_database).upgrade()

    assert _query_one(
        postgresql_database,
        "SELECT version FROM ascos_schema_version WHERE singleton=1",
    )[0] == newer_version


def test_failing_migration_rolls_back_schema_and_version(
    postgresql_database,
    monkeypatch,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    original_version = migration_module.MIGRATIONS[-1].version
    broken_migration = Migration(
        original_version + 1,
        (
            "CREATE TABLE migration_rollback_probe(value INTEGER)",
            "SELECT ascos_deliberately_missing_migration_function()",
        ),
    )
    monkeypatch.setattr(
        migration_module,
        "MIGRATIONS",
        migration_module.MIGRATIONS + (broken_migration,),
    )

    with pytest.raises(psycopg.Error):
        PostgreSQLMigrator(postgresql_database).upgrade()

    row = _query_one(
        postgresql_database,
        """
        SELECT version, to_regclass('migration_rollback_probe')
        FROM ascos_schema_version
        WHERE singleton=1
        """,
    )
    assert row == (original_version, None)


def test_concurrent_claims_are_unique_and_follow_deterministic_order(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    operation_ids = [f"op-{index}" for index in range(8)]
    for index, operation_id in enumerate(operation_ids):
        _insert_outbox_operation(
            postgresql_database,
            operation_id,
            priority=index,
            created_at=NOW + timedelta(seconds=index),
        )

    workers = 4
    barrier = Barrier(workers)

    def claim(index):
        barrier.wait(timeout=10)
        repository = PostgreSQLOutboxRepository(
            postgresql_database,
            clock=lambda: NOW,
        )
        return repository.claim_next(f"worker-{index}", ttl_seconds=60)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        claims = list(executor.map(claim, range(workers)))

    assert all(isinstance(claim, OutboxClaim) for claim in claims)
    assert {claim.operation_id for claim in claims} == set(operation_ids[:workers])
    assert len({claim.operation_id for claim in claims}) == workers
    assert len({claim.token for claim in claims}) == workers
    assert {claim.fencing_token for claim in claims} == {1}

    with postgresql_database() as connection:
        rows = connection.execute(
            """
            SELECT operation_id, claim_owner, claim_token_hash, status,
                   fencing_token, version
            FROM outbox_operations
            WHERE status='CLAIMED'
            ORDER BY priority, operation_id
            """
        ).fetchall()
    assert [row[0] for row in rows] == operation_ids[:workers]
    assert {row[1] for row in rows} == {claim.owner_id for claim in claims}
    assert all(row[2] not in {claim.token for claim in claims} for row in rows)
    assert all(row[3:] == ("CLAIMED", 1, 1) for row in rows)
    stored_hashes = {row[2] for row in rows}
    assert {
        hashlib.sha256(claim.token.encode()).hexdigest() for claim in claims
    } == stored_hashes


def test_claim_transaction_failure_rolls_back_lock_and_mutation(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    _insert_outbox_operation(postgresql_database, "rollback-op")

    class FailingCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, statement, parameters=()):
            result = self.cursor.execute(statement, parameters)
            if "SET status='CLAIMED'" in statement:
                raise RuntimeError("forced claim failure")
            return result

        def fetchone(self):
            return self.cursor.fetchone()

    class FailingConnection:
        def __init__(self, connection):
            self.connection = connection

        def transaction(self):
            return self.connection.transaction()

        def cursor(self):
            return FailingCursor(self.connection.cursor())

        def close(self):
            self.connection.close()

    def failing_connection_factory():
        return FailingConnection(postgresql_database())

    with pytest.raises(RuntimeError, match="forced claim failure"):
        PostgreSQLOutboxRepository(
            failing_connection_factory,
            clock=lambda: NOW,
        ).claim_next("worker-failing")

    assert _query_one(
        postgresql_database,
        """
        SELECT status, claim_owner, claim_token_hash, claim_expires_at,
               fencing_token, version
        FROM outbox_operations
        WHERE operation_id='rollback-op'
        """,
    ) == ("PENDING", None, None, None, 0, 0)
    recovered_claim = PostgreSQLOutboxRepository(
        postgresql_database,
        clock=lambda: NOW,
    ).claim_next("worker-retry")
    assert recovered_claim.operation_id == "rollback-op"
    assert recovered_claim.fencing_token == 1


def test_expired_claim_is_reclaimed_with_a_new_fencing_token(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    _insert_outbox_operation(
        postgresql_database,
        "expired-op",
        status="CLAIMED",
        claim_owner="stale-worker",
        claim_token_hash=hashlib.sha256(b"stale-token").hexdigest(),
        claim_expires_at=NOW - timedelta(seconds=1),
        fencing_token=7,
        version=3,
    )

    claim = PostgreSQLOutboxRepository(
        postgresql_database,
        clock=lambda: NOW,
    ).claim_next("recovery-worker", ttl_seconds=45)

    assert isinstance(claim, OutboxClaim)
    assert claim.operation_id == "expired-op"
    assert claim.owner_id == "recovery-worker"
    assert claim.claimed_at == NOW
    assert claim.expires_at == NOW + timedelta(seconds=45)
    assert claim.fencing_token == 8
    stored = _query_one(
        postgresql_database,
        """
        SELECT claim_owner, claim_token_hash, claim_expires_at,
               fencing_token, version
        FROM outbox_operations
        WHERE operation_id='expired-op'
        """,
    )
    assert stored == (
        "recovery-worker",
        hashlib.sha256(claim.token.encode()).hexdigest(),
        NOW + timedelta(seconds=45),
        8,
        5,
    )


def test_recover_expired_routes_claims_by_dispatch_certainty(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    for operation_id, status in (
        ("expired-claimed", "CLAIMED"),
        ("expired-dispatching", "DISPATCHING"),
    ):
        _insert_outbox_operation(
            postgresql_database,
            operation_id,
            status=status,
            claim_owner="crashed-worker",
            claim_token_hash=hashlib.sha256(
                f"token-{operation_id}".encode()
            ).hexdigest(),
            claim_expires_at=NOW - timedelta(seconds=1),
            fencing_token=3,
            version=5,
        )

    repository = PostgreSQLOutboxRepository(
        postgresql_database,
        clock=lambda: NOW,
    )
    assert repository.recover_expired() == 2

    with postgresql_database() as connection:
        rows = connection.execute(
            """
            SELECT operation_id, status, claim_owner, claim_token_hash,
                   claim_expires_at, fencing_token, version
            FROM outbox_operations
            ORDER BY operation_id
            """
        ).fetchall()
    assert rows == [
        ("expired-claimed", "PENDING", None, None, None, 3, 6),
        (
            "expired-dispatching",
            "RECONCILIATION_REQUIRED",
            None,
            None,
            None,
            3,
            6,
        ),
    ]


def test_runtime_initialize_is_visible_to_a_restarted_repository(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    original = PostgreSQLRuntimeRepository(
        postgresql_database,
        clock=lambda: NOW,
    ).initialize("runtime-1", {"phase": "PLANNED", "attempt": 0})

    restarted = PostgreSQLRuntimeRepository(
        postgresql_database,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    recovered = restarted.load("runtime-1")
    repeated = restarted.initialize(
        "runtime-1",
        {"phase": "must-not-overwrite"},
    )

    assert original.runtime_id == "runtime-1"
    assert original.state_version == 0
    assert original.checkpoint == {"phase": "PLANNED", "attempt": 0}
    assert original.updated_at == NOW
    assert recovered == original
    assert repeated == original
    assert restarted.list_events("runtime-1") == ()


def test_runtime_commit_persists_checkpoint_and_ordered_events_atomically(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    repository = PostgreSQLRuntimeRepository(
        postgresql_database,
        clock=lambda: NOW,
    )
    repository.initialize("runtime-1", {"phase": "PLANNED"})
    events = (
        PostgreSQLRuntimeEventInput(
            "event-1",
            "project-1",
            1,
            {"kind": "IMPLEMENTATION_STARTED"},
            NOW + timedelta(seconds=1),
        ),
        PostgreSQLRuntimeEventInput(
            "event-2",
            "project-1",
            2,
            {"kind": "IMPLEMENTATION_FINISHED"},
            NOW + timedelta(seconds=2),
        ),
    )

    version = repository.commit(
        "runtime-1",
        expected_version=0,
        checkpoint={"phase": "IMPLEMENTED", "artifacts": ["pull-request"]},
        events=events,
    )

    restarted = PostgreSQLRuntimeRepository(
        postgresql_database,
        clock=lambda: NOW + timedelta(hours=1),
    )
    state = restarted.load("runtime-1")
    stored_events = restarted.list_events("runtime-1")
    assert version == 1
    assert state.state_version == 1
    assert state.checkpoint == {
        "phase": "IMPLEMENTED",
        "artifacts": ["pull-request"],
    }
    assert [event.event_id for event in stored_events] == ["event-1", "event-2"]
    assert [event.aggregate_sequence for event in stored_events] == [1, 2]
    assert [event.payload for event in stored_events] == [
        {"kind": "IMPLEMENTATION_STARTED"},
        {"kind": "IMPLEMENTATION_FINISHED"},
    ]
    assert all(event.runtime_id == "runtime-1" for event in stored_events)
    assert stored_events[0].global_position < stored_events[1].global_position


def test_duplicate_runtime_event_rolls_back_checkpoint_and_all_events(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    repository = PostgreSQLRuntimeRepository(
        postgresql_database,
        clock=lambda: NOW,
    )
    initial = repository.initialize("runtime-1", {"phase": "PLANNED"})
    duplicate_events = (
        PostgreSQLRuntimeEventInput(
            "duplicate-event",
            "project-1",
            1,
            {"ordinal": 1},
            NOW,
        ),
        PostgreSQLRuntimeEventInput(
            "duplicate-event",
            "project-1",
            2,
            {"ordinal": 2},
            NOW + timedelta(seconds=1),
        ),
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        repository.commit(
            "runtime-1",
            expected_version=0,
            checkpoint={"phase": "must-roll-back"},
            events=duplicate_events,
        )

    assert repository.load("runtime-1") == initial
    assert repository.list_events("runtime-1") == ()


def test_concurrent_runtime_commit_has_exactly_one_version_winner(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    PostgreSQLRuntimeRepository(
        postgresql_database,
        clock=lambda: NOW,
    ).initialize("runtime-1", {"winner": None})
    barrier = Barrier(2)

    def commit(index):
        barrier.wait(timeout=10)
        repository = PostgreSQLRuntimeRepository(
            postgresql_database,
            clock=lambda: NOW + timedelta(seconds=index + 1),
        )
        try:
            return repository.commit(
                "runtime-1",
                expected_version=0,
                checkpoint={"winner": index},
                events=(
                    PostgreSQLRuntimeEventInput(
                        f"winner-event-{index}",
                        "project-1",
                        1,
                        {"winner": index},
                        NOW + timedelta(seconds=index + 1),
                    ),
                ),
            )
        except PostgreSQLVersionConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(commit, range(2)))

    assert results.count(1) == 1
    assert results.count("conflict") == 1
    restarted = PostgreSQLRuntimeRepository(
        postgresql_database,
        clock=lambda: NOW + timedelta(days=1),
    )
    state = restarted.load("runtime-1")
    events = restarted.list_events("runtime-1")
    assert state.state_version == 1
    assert state.checkpoint in ({"winner": 0}, {"winner": 1})
    assert len(events) == 1
    assert events[0].payload == state.checkpoint
    assert events[0].event_id == f"winner-event-{state.checkpoint['winner']}"


def test_worker_heartbeat_compare_and_swap_has_one_winner(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    with postgresql_database() as connection:
        connection.execute(
            """
            INSERT INTO worker_registrations(
                worker_instance_id, worker_id, runtime_id, status,
                heartbeat_expires_at, canonical_state, version
            ) VALUES(%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "worker-instance-1",
                "worker-1",
                "runtime-1",
                "IDLE",
                NOW + timedelta(seconds=30),
                Jsonb({"heartbeat": 0}),
                0,
            ),
        )

    barrier = Barrier(2)

    def heartbeat(index):
        barrier.wait(timeout=10)
        try:
            return PostgreSQLWorkerRepository(postgresql_database).heartbeat(
                "worker-instance-1",
                expected_version=0,
                now=NOW + timedelta(seconds=index),
                expires_at=NOW + timedelta(seconds=60 + index),
            )
        except PostgreSQLVersionConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(heartbeat, range(2)))

    assert results.count(1) == 1
    assert results.count("conflict") == 1
    version, expires_at = _query_one(
        postgresql_database,
        """
        SELECT version, heartbeat_expires_at
        FROM worker_registrations
        WHERE worker_instance_id='worker-instance-1'
        """,
    )
    assert version == 1
    assert expires_at in {
        NOW + timedelta(seconds=60),
        NOW + timedelta(seconds=61),
    }


def test_provider_health_compare_and_swap_has_one_winner(
    postgresql_database,
):
    PostgreSQLMigrator(postgresql_database).upgrade()
    with postgresql_database() as connection:
        connection.execute(
            """
            INSERT INTO provider_health(
                provider_id, capability, status, canonical_state, version
            ) VALUES(%s, %s, %s, %s, %s)
            """,
            ("github", "git", "UNKNOWN", Jsonb({"revision": 0}), 0),
        )

    state = SimpleNamespace(
        provider_id="github",
        capability="git",
        status=SimpleNamespace(value="HEALTHY"),
    )
    barrier = Barrier(2)

    def save(index):
        barrier.wait(timeout=10)
        try:
            return PostgreSQLProviderHealthRepository(
                postgresql_database
            ).save(
                state,
                expected_version=0,
                canonical_state={"revision": index + 1},
            )
        except PostgreSQLVersionConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, range(2)))

    assert results.count(1) == 1
    assert results.count("conflict") == 1
    status, canonical_state, version = _query_one(
        postgresql_database,
        """
        SELECT status, canonical_state, version
        FROM provider_health
        WHERE provider_id='github' AND capability='git'
        """,
    )
    assert status == "HEALTHY"
    assert canonical_state in ({"revision": 1}, {"revision": 2})
    assert version == 1
