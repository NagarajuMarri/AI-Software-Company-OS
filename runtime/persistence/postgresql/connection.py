from dataclasses import dataclass
import re

from runtime.persistence.postgresql.exceptions import PostgreSQLConnectionError


@dataclass(frozen=True)
class PostgreSQLConfiguration:
    connection_reference: str
    minimum_pool_size: int = 1
    maximum_pool_size: int = 10

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", self.connection_reference):
            raise ValueError("Connection must be supplied by safe reference")
        if not 1 <= self.minimum_pool_size <= self.maximum_pool_size <= 100:
            raise ValueError("Invalid pool limits")


def connect(configuration, resolver):
    """Resolve the actual DSN at the last responsible moment, without echoing it."""
    try:
        dsn = resolver(configuration.connection_reference)
        if not isinstance(dsn, str) or not dsn:
            raise ValueError("Connection resolver returned no DSN")
        import psycopg

        return psycopg.connect(dsn)
    except Exception:
        # Fall through before raising the mapped error. Raising inside this
        # block would retain the driver/resolver error in ``__context__``, where
        # a resolved connection string (including credentials) could survive.
        pass
    raise PostgreSQLConnectionError("PostgreSQL connection failed")


def to_jsonb(value):
    """Adapt a Python JSON value for Psycopg without importing the driver eagerly."""
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError as error:
        if error.name != "psycopg":
            raise
        # Database-free unit tests use small fake connection objects. A real
        # PostgreSQL connection is always created through ``connect()``, which
        # fails closed when the optional driver is absent.
        return value
    return Jsonb(value)
