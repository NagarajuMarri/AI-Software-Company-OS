from runtime.persistence.postgresql.exceptions import PostgreSQLVersionConflictError


class PostgreSQLRuntimeRepository:
    def __init__(self, connection_factory, *, clock):
        self.connection_factory = connection_factory
        self.clock = clock

    def commit(self, runtime_id, *, expected_version, checkpoint, events):
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE runtime_instances SET state_version=state_version+1, "
                    "checkpoint=%s, updated_at=%s WHERE runtime_id=%s "
                    "AND state_version=%s RETURNING state_version",
                    (checkpoint, self.clock(), runtime_id, expected_version),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PostgreSQLVersionConflictError("Runtime version conflict")
                for event in events:
                    cursor.execute(
                        "INSERT INTO runtime_events(event_id,runtime_id,aggregate_id,"
                        "aggregate_sequence,payload,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                        event,
                    )
            return row[0]
        finally: connection.close()
