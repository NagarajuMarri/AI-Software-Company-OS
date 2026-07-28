class PostgreSQLProviderHealthRepository:
    def __init__(self, connection_factory): self.connection_factory = connection_factory

    def save(self, state, *, expected_version, canonical_state):
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE provider_health SET status=%s, canonical_state=%s, "
                    "version=version+1 WHERE provider_id=%s AND capability=%s "
                    "AND version=%s RETURNING version",
                    (
                        state.status.value, canonical_state, state.provider_id,
                        state.capability, expected_version,
                    ),
                )
                row = cursor.fetchone()
                if row is None: raise RuntimeError("Provider health version conflict")
                return row[0]
        finally: connection.close()
