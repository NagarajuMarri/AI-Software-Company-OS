import hashlib
import re
import secrets
from datetime import timedelta

from runtime.outbox.models import OutboxClaim


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

RECOVER_EXPIRED_SQL = """
UPDATE outbox_operations
SET status = CASE
        WHEN status = 'DISPATCHING' THEN 'RECONCILIATION_REQUIRED'
        ELSE 'PENDING'
    END,
    claim_owner = NULL,
    claim_token_hash = NULL,
    claim_expires_at = NULL,
    version = version + 1
WHERE status IN ('CLAIMED', 'DISPATCHING')
  AND claim_expires_at IS NOT NULL
  AND claim_expires_at <= %s
"""

_OWNER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class PostgreSQLOutboxRepository:
    def __init__(self, connection_factory, *, clock):
        self.connection_factory = connection_factory
        self.clock = clock

    def claim_next(self, owner_id, *, ttl_seconds=30):
        self._validate_claim_request(owner_id, ttl_seconds)
        connection = self.connection_factory()
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = self.clock()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                self._recover_expired(cursor, now)
                cursor.execute(CLAIM_SELECT_SQL, (now, now))
                row = cursor.fetchone()
                if row is None:
                    return None
                operation_id, fencing = row
                expires_at = now + timedelta(seconds=ttl_seconds)
                cursor.execute(
                    "UPDATE outbox_operations SET status='CLAIMED', claim_owner=%s, "
                    "claim_token_hash=%s, claim_expires_at=%s, fencing_token=%s, "
                    "version=version+1 WHERE operation_id=%s RETURNING version",
                    (
                        owner_id, token_hash, expires_at,
                        fencing + 1, operation_id,
                    ),
                )
                version = cursor.fetchone()[0]
                if version < 1:
                    raise RuntimeError("PostgreSQL outbox version did not advance")
            return OutboxClaim(
                operation_id,
                owner_id,
                token,
                now,
                expires_at,
                fencing + 1,
            )
        finally:
            connection.close()

    def recover_expired(self, now=None):
        connection = self.connection_factory()
        try:
            with connection.transaction():
                cursor = connection.cursor()
                self._recover_expired(cursor, now or self.clock())
                return cursor.rowcount
        finally:
            connection.close()

    @staticmethod
    def _recover_expired(cursor, now):
        cursor.execute(RECOVER_EXPIRED_SQL, (now,))

    @staticmethod
    def _validate_claim_request(owner_id, ttl_seconds):
        if not isinstance(owner_id, str) or not _OWNER_ID.fullmatch(owner_id):
            raise ValueError("Invalid PostgreSQL outbox owner")
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or not 0 < ttl_seconds <= 3600
        ):
            raise ValueError("Invalid PostgreSQL outbox claim duration")
