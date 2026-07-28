class PostgreSQLWorkerRepository:
    def __init__(self, connection_factory): self.connection_factory = connection_factory

    def heartbeat(self, instance_id, *, expected_version, now, expires_at):
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE worker_registrations SET heartbeat_expires_at=%s, "
                    "version=version+1 WHERE worker_instance_id=%s AND version=%s "
                    "RETURNING version",
                    (expires_at, instance_id, expected_version),
                )
                row = cursor.fetchone()
                if row is None: raise RuntimeError("Worker heartbeat version conflict")
                return row[0]
        finally: connection.close()
