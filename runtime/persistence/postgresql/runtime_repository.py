from dataclasses import dataclass
from datetime import datetime
import re

from runtime.persistence.postgresql.connection import to_jsonb
from runtime.persistence.postgresql.exceptions import PostgreSQLVersionConflictError


_RUNTIME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class PostgreSQLRuntimeState:
    runtime_id: str
    state_version: int
    checkpoint: object
    updated_at: datetime


@dataclass(frozen=True)
class PostgreSQLRuntimeEventInput:
    event_id: str
    aggregate_id: str
    aggregate_sequence: int
    payload: object
    created_at: datetime


@dataclass(frozen=True)
class PostgreSQLRuntimeEventRecord:
    event_id: str
    runtime_id: str
    global_position: int
    aggregate_id: str
    aggregate_sequence: int
    payload: object
    created_at: datetime


class PostgreSQLRuntimeRepository:
    def __init__(self, connection_factory, *, clock):
        self.connection_factory = connection_factory
        self.clock = clock

    def initialize(self, runtime_id, checkpoint):
        self._validate_runtime_id(runtime_id)
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO runtime_instances(runtime_id,state_version,checkpoint,updated_at) "
                    "VALUES(%s,0,%s,%s) ON CONFLICT(runtime_id) DO NOTHING "
                    "RETURNING runtime_id,state_version,checkpoint,updated_at",
                    (runtime_id, to_jsonb(checkpoint), self.clock()),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        "SELECT runtime_id,state_version,checkpoint,updated_at "
                        "FROM runtime_instances WHERE runtime_id=%s",
                        (runtime_id,),
                    )
                    row = cursor.fetchone()
            return PostgreSQLRuntimeState(*row)
        finally:
            connection.close()

    def load(self, runtime_id):
        self._validate_runtime_id(runtime_id)
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT runtime_id,state_version,checkpoint,updated_at "
                    "FROM runtime_instances WHERE runtime_id=%s",
                    (runtime_id,),
                )
                row = cursor.fetchone()
            return None if row is None else PostgreSQLRuntimeState(*row)
        finally:
            connection.close()

    def list_events(self, runtime_id):
        self._validate_runtime_id(runtime_id)
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT event_id,runtime_id,global_position,aggregate_id,"
                    "aggregate_sequence,payload,created_at FROM runtime_events "
                    "WHERE runtime_id=%s ORDER BY global_position ASC",
                    (runtime_id,),
                )
                rows = cursor.fetchall()
            return tuple(PostgreSQLRuntimeEventRecord(*row) for row in rows)
        finally:
            connection.close()

    def commit(self, runtime_id, *, expected_version, checkpoint, events):
        self._validate_runtime_id(runtime_id)
        if not isinstance(expected_version, int) or expected_version < 0:
            raise ValueError("Invalid PostgreSQL runtime version")
        events = tuple(events)
        for event in events:
            self._validate_event(event)
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE runtime_instances SET state_version=state_version+1, "
                    "checkpoint=%s, updated_at=%s WHERE runtime_id=%s "
                    "AND state_version=%s RETURNING state_version",
                    (to_jsonb(checkpoint), self.clock(), runtime_id, expected_version),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PostgreSQLVersionConflictError("Runtime version conflict")
                for event in events:
                    cursor.execute(
                        "INSERT INTO runtime_events(event_id,runtime_id,aggregate_id,"
                        "aggregate_sequence,payload,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                        (
                            event.event_id,
                            runtime_id,
                            event.aggregate_id,
                            event.aggregate_sequence,
                            to_jsonb(event.payload),
                            event.created_at,
                        ),
                    )
            return row[0]
        finally:
            connection.close()

    @staticmethod
    def _validate_runtime_id(runtime_id):
        if not isinstance(runtime_id, str) or not _RUNTIME_ID.fullmatch(runtime_id):
            raise ValueError("Invalid PostgreSQL runtime identity")

    @staticmethod
    def _validate_event(event):
        if not isinstance(event, PostgreSQLRuntimeEventInput):
            raise TypeError("PostgreSQL runtime events must use PostgreSQLRuntimeEventInput")
        if (
            not isinstance(event.event_id, str)
            or not _RUNTIME_ID.fullmatch(event.event_id)
            or not isinstance(event.aggregate_id, str)
            or not _RUNTIME_ID.fullmatch(event.aggregate_id)
            or isinstance(event.aggregate_sequence, bool)
            or not isinstance(event.aggregate_sequence, int)
            or event.aggregate_sequence < 0
            or event.created_at.tzinfo is None
            or event.created_at.utcoffset() is None
        ):
            raise ValueError("Invalid PostgreSQL runtime event")
