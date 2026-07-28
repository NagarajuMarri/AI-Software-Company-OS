"""Deterministic database schema migration boundary."""

import sqlite3

from runtime.persistence.database.exceptions import DatabaseSchemaError
from runtime.persistence.database.schema import (
    DATABASE_SCHEMA_VERSION,
    SCHEMA_SQL,
)


def migrate(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > DATABASE_SCHEMA_VERSION:
        raise DatabaseSchemaError(
            f"Database schema {version} is newer than supported "
            f"{DATABASE_SCHEMA_VERSION}"
        )
    if version == DATABASE_SCHEMA_VERSION:
        return
    if version != 0:
        raise DatabaseSchemaError(
            f"No migration adapter exists for database schema {version}"
        )
    try:
        connection.executescript(
            "BEGIN IMMEDIATE;\n"
            f"{SCHEMA_SQL}\n"
            f"PRAGMA user_version={DATABASE_SCHEMA_VERSION};\n"
            "COMMIT;"
        )
    except sqlite3.DatabaseError:
        if connection.in_transaction:
            connection.rollback()
        raise
