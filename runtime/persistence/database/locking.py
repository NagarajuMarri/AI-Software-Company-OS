"""SQLite busy/locked error mapping."""

import sqlite3

from runtime.persistence.database.exceptions import ConcurrentPersistenceError


def map_database_error(error: sqlite3.OperationalError) -> Exception:
    if "locked" in str(error).lower() or "busy" in str(error).lower():
        return ConcurrentPersistenceError("Database is busy or locked")
    return error
