"""Transactional SQLite persistence provider."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.events.event import RuntimeEvent
from runtime.events.types import EventType
from runtime.persistence.database.exceptions import (
    ConcurrentPersistenceError,
    LeaseExpiredError,
    RuntimeVersionConflictError,
    StaleCheckpointError,
    StaleFencingTokenError,
)
from runtime.persistence.database.leases import RuntimeLeaseRepository
from runtime.persistence.database.locking import map_database_error
from runtime.persistence.database.migrations import migrate
from runtime.persistence.database.models import RuntimeLease
from runtime.persistence.file_store import FilePersistenceProvider
from runtime.persistence.models import (
    CheckpointSelection,
    DurabilityStatus,
    PersistenceCommitResult,
    RuntimeCheckpoint,
)
from runtime.persistence.serializer import CanonicalSerializer


class _ClosingConnection(sqlite3.Connection):
    """Commit or roll back like sqlite3, then release the file handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class DatabasePersistenceProvider:
    """SQLite implementation designed behind PostgreSQL-ready contracts."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        timeout: float = 5.0,
        clock=None,
    ) -> None:
        self.database_path = str(Path(database_path).resolve())
        self.timeout = timeout
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        connection = self._connect()
        try:
            migrate(connection)
        finally:
            connection.close()
        self.leases = RuntimeLeaseRepository(
            self._connect,
            self._ensure_runtime,
            self.clock,
        )
        self.last_checkpoint_selection: CheckpointSelection | None = None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.timeout,
            isolation_level=None,
            factory=_ClosingConnection,
        )
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _ensure_runtime(
        self,
        connection: sqlite3.Connection,
        runtime_id: str,
    ) -> None:
        now = self.clock().isoformat()
        connection.execute(
            "INSERT OR IGNORE INTO runtime_instances "
            "(runtime_id,schema_version,current_state_version,"
            "latest_checkpoint_id,latest_event_position,durability_status,"
            "latest_fencing_token,created_at,updated_at) "
            "VALUES(?,1,0,NULL,0,?,0,?,?)",
            (
                runtime_id,
                DurabilityStatus.NOT_ATTEMPTED.value,
                now,
                now,
            ),
        )

    def get_state_version(self, runtime_id: str) -> int:
        with self._connect() as connection:
            self._ensure_runtime(connection, runtime_id)
            return connection.execute(
                "SELECT current_state_version FROM runtime_instances "
                "WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()[0]

    def save_checkpoint(self, checkpoint: RuntimeCheckpoint) -> None:
        expected = self.get_state_version(checkpoint.runtime_id)
        self.commit_checkpoint(checkpoint, expected_state_version=expected)

    def commit_checkpoint(
        self,
        checkpoint: RuntimeCheckpoint,
        *,
        expected_state_version: int,
        lease: RuntimeLease | None = None,
        operation_id: str | None = None,
    ) -> PersistenceCommitResult:
        operation_id = operation_id or str(uuid.uuid4())
        now = self.clock()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_runtime(connection, checkpoint.runtime_id)
            row = connection.execute(
                "SELECT current_state_version, latest_event_position, "
                "latest_fencing_token FROM runtime_instances WHERE runtime_id=?",
                (checkpoint.runtime_id,),
            ).fetchone()
            current_version, current_position, latest_fencing = row
            if current_version != expected_state_version:
                raise RuntimeVersionConflictError(
                    f"Expected state version {expected_state_version}; "
                    f"current version is {current_version}"
                )
            if lease is not None:
                if lease.runtime_id != checkpoint.runtime_id:
                    raise StaleFencingTokenError(
                        "Lease belongs to a different runtime"
                    )
                self._validate_lease(
                    connection,
                    lease,
                    now,
                    latest_fencing,
                )
            events = list(checkpoint.payload["events"])
            if checkpoint.last_event_position != len(events):
                raise StaleCheckpointError(
                    "Checkpoint event position does not match payload"
                )
            if current_position > checkpoint.last_event_position:
                raise StaleCheckpointError(
                    "Checkpoint is older than durable event position"
                )
            existing_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT event_id FROM runtime_events WHERE runtime_id=? "
                    "ORDER BY global_position",
                    (checkpoint.runtime_id,),
                ).fetchall()
            ]
            if existing_ids != [
                event["id"] for event in events[:current_position]
            ]:
                raise StaleCheckpointError(
                    "Checkpoint event prefix does not match durable stream"
                )
            aggregate_sequences = {}
            for position, event in enumerate(
                events[current_position:],
                start=current_position + 1,
            ):
                aggregate_key = (
                    event["aggregate_type"],
                    event["aggregate_id"],
                )
                if aggregate_key not in aggregate_sequences:
                    aggregate_sequences[aggregate_key] = connection.execute(
                        "SELECT COALESCE(MAX(aggregate_sequence),0) "
                        "FROM runtime_events WHERE runtime_id=? "
                        "AND aggregate_type=? AND aggregate_id=?",
                        (checkpoint.runtime_id, *aggregate_key),
                    ).fetchone()[0]
                aggregate_sequences[aggregate_key] += 1
                if event["sequence_number"] != aggregate_sequences[aggregate_key]:
                    raise StaleCheckpointError(
                        "Checkpoint aggregate sequence is not contiguous"
                    )
                connection.execute(
                    "INSERT INTO runtime_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        event["id"],
                        checkpoint.runtime_id,
                        position,
                        event["aggregate_type"],
                        event["aggregate_id"],
                        event["sequence_number"],
                        event["event_type"],
                        event["occurred_at"],
                        event["correlation_id"],
                        event["causation_id"],
                        CanonicalSerializer.dumps(
                            CanonicalSerializer.encode_value(event["payload"])
                        ),
                    ),
                )
            state_version = current_version + 1
            document = FilePersistenceProvider._to_document(checkpoint)
            connection.execute(
                "INSERT INTO runtime_checkpoints VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    checkpoint.id,
                    checkpoint.runtime_id,
                    checkpoint.schema_version,
                    state_version,
                    checkpoint.created_at.isoformat(),
                    checkpoint.reason,
                    checkpoint.last_event_position,
                    checkpoint.state_digest,
                    CanonicalSerializer.dumps(document),
                    now.isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO runtime_state_versions VALUES(?,?,?,?)",
                (
                    checkpoint.runtime_id,
                    state_version,
                    checkpoint.id,
                    now.isoformat(),
                ),
            )
            connection.execute(
                "UPDATE runtime_instances SET current_state_version=?, "
                "latest_checkpoint_id=?, latest_event_position=?, "
                "durability_status=?, updated_at=? WHERE runtime_id=?",
                (
                    state_version,
                    checkpoint.id,
                    checkpoint.last_event_position,
                    DurabilityStatus.COMMITTED_DURABLE.value,
                    now.isoformat(),
                    checkpoint.runtime_id,
                ),
            )
            connection.execute(
                "INSERT INTO persistence_transactions VALUES(?,?,?,?,?,?,?)",
                (
                    operation_id,
                    checkpoint.runtime_id,
                    expected_state_version,
                    state_version,
                    "COMMITTED",
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.commit()
            return PersistenceCommitResult(
                checkpoint.runtime_id,
                operation_id,
                state_version,
                checkpoint.id,
                checkpoint.last_event_position,
                True,
                True,
                DurabilityStatus.COMMITTED_DURABLE,
                now,
            )
        except RuntimeVersionConflictError:
            connection.rollback()
            raise
        except sqlite3.OperationalError as error:
            connection.rollback()
            raise map_database_error(error)
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise ConcurrentPersistenceError(
                "Database constraint rejected persistence transaction"
            ) from error
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _validate_lease(
        connection,
        lease: RuntimeLease,
        now: datetime,
        latest_fencing: int,
    ) -> None:
        row = connection.execute(
            "SELECT lease_owner_id, lease_token_hash, expires_at, "
            "fencing_token FROM runtime_leases WHERE runtime_id=?",
            (lease.runtime_id,),
        ).fetchone()
        if row is None or lease.fencing_token != latest_fencing:
            raise StaleFencingTokenError("Lease fencing token is stale")
        if (
            row[0] != lease.owner_id
            or row[1]
            != hashlib.sha256(lease.lease_token.encode()).hexdigest()
            or row[3] != lease.fencing_token
        ):
            raise StaleFencingTokenError("Lease identity is stale")
        if datetime.fromisoformat(row[2]) <= now:
            raise LeaseExpiredError("Lease has expired")

    def load_checkpoint(self, checkpoint_id: str) -> RuntimeCheckpoint:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT canonical_payload FROM runtime_checkpoints "
                "WHERE checkpoint_id=?",
                (checkpoint_id,),
            ).fetchall()
        if len(rows) != 1:
            from runtime.persistence.exceptions import CheckpointNotFoundError

            raise CheckpointNotFoundError(checkpoint_id)
        return self._decode_checkpoint(rows[0][0])

    def list_checkpoints(self, runtime_id: str) -> list[RuntimeCheckpoint]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT canonical_payload FROM runtime_checkpoints "
                "WHERE runtime_id=? ORDER BY state_version, checkpoint_id",
                (runtime_id,),
            ).fetchall()
        return [self._decode_checkpoint(row[0]) for row in rows]

    def select_latest_checkpoint(
        self,
        runtime_id: str,
        *,
        recovery_mode: bool = False,
    ) -> CheckpointSelection:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT checkpoint_id, canonical_payload "
                "FROM runtime_checkpoints WHERE runtime_id=? "
                "ORDER BY state_version DESC",
                (runtime_id,),
            ).fetchall()
        skipped = []
        for checkpoint_id, payload in rows:
            try:
                selection = CheckpointSelection(
                    self._decode_checkpoint(payload),
                    recovery_mode,
                    tuple(skipped),
                )
                self.last_checkpoint_selection = selection
                return selection
            except Exception:
                if not recovery_mode:
                    raise
                skipped.append(checkpoint_id)
        from runtime.persistence.exceptions import CheckpointNotFoundError

        raise CheckpointNotFoundError(runtime_id)

    def load_latest_checkpoint(
        self,
        runtime_id: str,
        *,
        recovery_mode: bool = False,
    ) -> RuntimeCheckpoint:
        return self.select_latest_checkpoint(
            runtime_id,
            recovery_mode=recovery_mode,
        ).checkpoint

    @staticmethod
    def _decode_checkpoint(value: str) -> RuntimeCheckpoint:
        document = json.loads(value)
        return FilePersistenceProvider._from_document(document)

    def get_event(self, event_id: str) -> RuntimeEvent:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
        if row is None:
            from runtime.exceptions import EventNotFoundError

            raise EventNotFoundError(event_id)
        return self._row_to_event(row)

    def list_events(
        self,
        runtime_id: str,
        *,
        after_position: int = 0,
    ) -> list[RuntimeEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_events WHERE runtime_id=? "
                "AND global_position>? ORDER BY global_position",
                (runtime_id, after_position),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def list_events_for_aggregate(
        self,
        runtime_id: str,
        aggregate_type: str,
        aggregate_id: str,
    ) -> list[RuntimeEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_events WHERE runtime_id=? "
                "AND aggregate_type=? AND aggregate_id=? "
                "ORDER BY aggregate_sequence",
                (runtime_id, aggregate_type, aggregate_id),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def list_events_for_correlation(
        self,
        runtime_id: str,
        correlation_id: str,
    ) -> list[RuntimeEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_events WHERE runtime_id=? "
                "AND correlation_id=? ORDER BY global_position",
                (runtime_id, correlation_id),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def latest_global_position(self, runtime_id: str) -> int:
        with self._connect() as connection:
            return connection.execute(
                "SELECT COALESCE(MAX(global_position),0) FROM runtime_events "
                "WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()[0]

    def latest_aggregate_sequence(
        self,
        runtime_id: str,
        aggregate_type: str,
        aggregate_id: str,
    ) -> int:
        with self._connect() as connection:
            return connection.execute(
                "SELECT COALESCE(MAX(aggregate_sequence),0) "
                "FROM runtime_events WHERE runtime_id=? "
                "AND aggregate_type=? AND aggregate_id=?",
                (runtime_id, aggregate_type, aggregate_id),
            ).fetchone()[0]

    def append_event(
        self,
        runtime_id: str,
        event: RuntimeEvent,
    ) -> int:
        return self.append_event_batch(runtime_id, [event])[-1]

    def append_event_batch(
        self,
        runtime_id: str,
        events: list[RuntimeEvent],
    ) -> list[int]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_runtime(connection, runtime_id)
            position = connection.execute(
                "SELECT latest_event_position FROM runtime_instances "
                "WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()[0]
            positions = []
            aggregate_sequences = {}
            for event in events:
                aggregate_key = (event.aggregate_type, event.aggregate_id)
                if aggregate_key not in aggregate_sequences:
                    aggregate_sequences[aggregate_key] = connection.execute(
                        "SELECT COALESCE(MAX(aggregate_sequence),0) "
                        "FROM runtime_events WHERE runtime_id=? "
                        "AND aggregate_type=? AND aggregate_id=?",
                        (runtime_id, *aggregate_key),
                    ).fetchone()[0]
                aggregate_sequences[aggregate_key] += 1
                if event.sequence_number != aggregate_sequences[aggregate_key]:
                    raise ConcurrentPersistenceError(
                        "Aggregate event sequence must be contiguous"
                    )
                position += 1
                connection.execute(
                    "INSERT INTO runtime_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        event.id,
                        runtime_id,
                        position,
                        event.aggregate_type,
                        event.aggregate_id,
                        event.sequence_number,
                        event.event_type.value,
                        event.occurred_at.isoformat(),
                        event.correlation_id,
                        event.causation_id,
                        CanonicalSerializer.dumps(
                            CanonicalSerializer.encode_value(event.payload)
                        ),
                    ),
                )
                positions.append(position)
            connection.execute(
                "UPDATE runtime_instances SET latest_event_position=?, "
                "updated_at=? WHERE runtime_id=?",
                (position, self.clock().isoformat(), runtime_id),
            )
            connection.commit()
            return positions
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise ConcurrentPersistenceError(
                "Event batch violated durable ordering constraints"
            ) from error
        except sqlite3.OperationalError as error:
            connection.rollback()
            raise map_database_error(error)
        finally:
            connection.close()

    @staticmethod
    def _row_to_event(row) -> RuntimeEvent:
        payload = CanonicalSerializer.decode_value(json.loads(row[10]))
        return RuntimeEvent(
            id=row[0],
            aggregate_type=row[3],
            aggregate_id=row[4],
            sequence_number=row[5],
            event_type=EventType(row[6]),
            occurred_at=datetime.fromisoformat(row[7]),
            correlation_id=row[8],
            causation_id=row[9],
            payload=payload,
        )
