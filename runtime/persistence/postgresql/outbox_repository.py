import hashlib
import secrets
from datetime import timedelta


CLAIM_SELECT_SQL = """
SELECT operation_id, fencing_token
FROM outbox_operations
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= %s
  AND (claim_expires_at IS NULL OR claim_expires_at <= %s)
ORDER BY priority ASC, available_at ASC, created_at ASC, operation_id ASC
FOR UPDATE SKIP LOCKED
LIMIT 1
"""


class PostgreSQLOutboxRepository:
    def __init__(self, connection_factory, *, clock):
        self.connection_factory = connection_factory
        self.clock = clock

    def claim_next(self, owner_id, *, ttl_seconds=30):
        connection = self.connection_factory()
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = self.clock()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute(CLAIM_SELECT_SQL, (now, now))
                row = cursor.fetchone()
                if row is None: return None
                operation_id, fencing = row
                cursor.execute(
                    "UPDATE outbox_operations SET status='CLAIMED', claim_owner=%s, "
                    "claim_token_hash=%s, claim_expires_at=%s, fencing_token=%s, "
                    "version=version+1 WHERE operation_id=%s RETURNING version",
                    (
                        owner_id, token_hash, now + timedelta(seconds=ttl_seconds),
                        fencing + 1, operation_id,
                    ),
                )
                version = cursor.fetchone()[0]
            return {
                "operation_id": operation_id, "owner_id": owner_id,
                "claim_token": token, "fencing_token": fencing + 1,
                "version": version,
            }
        finally:
            connection.close()
