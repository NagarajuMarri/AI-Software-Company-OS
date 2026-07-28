"""Runtime lease and fencing operations."""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable

from runtime.persistence.database.exceptions import (
    LeaseConflictError,
    LeaseExpiredError,
)
from runtime.persistence.database.models import RuntimeLease


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RuntimeLeaseRepository:
    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection],
        ensure_runtime: Callable[[sqlite3.Connection, str], None],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._ensure_runtime = ensure_runtime
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def acquire_lease(
        self,
        runtime_id: str,
        owner_id: str,
        *,
        ttl_seconds: int = 30,
    ) -> RuntimeLease:
        now = self._clock()
        expires = now + timedelta(seconds=ttl_seconds)
        token = secrets.token_urlsafe(32)
        with self._connection_factory() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_runtime(connection, runtime_id)
            row = connection.execute(
                "SELECT expires_at FROM runtime_leases WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()
            if row and datetime.fromisoformat(row[0]) > now:
                raise LeaseConflictError("Runtime already has an active lease")
            current = connection.execute(
                "SELECT latest_fencing_token FROM runtime_instances "
                "WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()[0]
            fencing = current + 1
            connection.execute(
                "UPDATE runtime_instances SET latest_fencing_token=?, "
                "updated_at=? WHERE runtime_id=?",
                (fencing, now.isoformat(), runtime_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO runtime_leases VALUES(?,?,?,?,?,?,?)",
                (
                    runtime_id,
                    owner_id,
                    _hash(token),
                    now.isoformat(),
                    now.isoformat(),
                    expires.isoformat(),
                    fencing,
                ),
            )
        return RuntimeLease(
            runtime_id,
            owner_id,
            token,
            now,
            now,
            expires,
            fencing,
        )

    def inspect_lease(self, runtime_id: str) -> dict | None:
        with self._connection_factory() as connection:
            row = connection.execute(
                "SELECT lease_owner_id, acquired_at, renewed_at, expires_at, "
                "fencing_token FROM runtime_leases WHERE runtime_id=?",
                (runtime_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "runtime_id": runtime_id,
            "owner_id": row[0],
            "acquired_at": datetime.fromisoformat(row[1]),
            "renewed_at": datetime.fromisoformat(row[2]),
            "expires_at": datetime.fromisoformat(row[3]),
            "fencing_token": row[4],
        }

    def renew_lease(
        self,
        lease: RuntimeLease,
        *,
        ttl_seconds: int = 30,
    ) -> RuntimeLease:
        now = self._clock()
        expires = now + timedelta(seconds=ttl_seconds)
        with self._connection_factory() as connection:
            row = connection.execute(
                "SELECT lease_token_hash, expires_at, fencing_token "
                "FROM runtime_leases WHERE runtime_id=? AND lease_owner_id=?",
                (lease.runtime_id, lease.owner_id),
            ).fetchone()
            if (
                row is None
                or row[0] != _hash(lease.lease_token)
                or row[2] != lease.fencing_token
            ):
                raise LeaseConflictError("Lease identity is not current")
            if datetime.fromisoformat(row[1]) <= now:
                raise LeaseExpiredError("Lease has expired")
            connection.execute(
                "UPDATE runtime_leases SET renewed_at=?, expires_at=? "
                "WHERE runtime_id=?",
                (now.isoformat(), expires.isoformat(), lease.runtime_id),
            )
        return RuntimeLease(
            lease.runtime_id,
            lease.owner_id,
            lease.lease_token,
            lease.acquired_at,
            now,
            expires,
            lease.fencing_token,
        )

    def release_lease(self, lease: RuntimeLease) -> None:
        with self._connection_factory() as connection:
            cursor = connection.execute(
                "DELETE FROM runtime_leases WHERE runtime_id=? "
                "AND lease_owner_id=? AND lease_token_hash=? "
                "AND fencing_token=?",
                (
                    lease.runtime_id,
                    lease.owner_id,
                    _hash(lease.lease_token),
                    lease.fencing_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflictError("Lease identity is not current")

    def break_expired_lease(self, runtime_id: str) -> bool:
        now = self._clock()
        with self._connection_factory() as connection:
            cursor = connection.execute(
                "DELETE FROM runtime_leases WHERE runtime_id=? "
                "AND expires_at<=?",
                (runtime_id, now.isoformat()),
            )
            return cursor.rowcount == 1
