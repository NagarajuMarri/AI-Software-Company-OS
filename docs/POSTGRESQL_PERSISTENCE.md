# PostgreSQL Persistence

The bounded PostgreSQL adapter isolates driver imports, connections, migrations,
and dialect SQL. Applications pass a safe reference; the DSN is resolved only while
connecting and is never included in mapped errors. Migrations use an explicit version
row and a transaction-scoped advisory lock. Repeated upgrades are idempotent, and
newer unknown schema versions are rejected.

## Day 4 validation contract

Pull-request and `main` CI always start an isolated PostgreSQL 16 service and run both
the adapter unit tests and the real-server integration suite. That suite must exercise
fresh and repeated migrations, concurrent migration attempts, rollback/version safety,
multi-connection claims, stale-claim recovery, optimistic version conflicts, and
restart readback. A green unit-only run is not PostgreSQL runtime evidence.

Local verification requires a disposable test database and the PostgreSQL extra:

```bash
python -m pip install -e ".[dev,postgres]"
ASCOS_POSTGRES_TEST_URL='<test-dsn>' \
  python -m pytest -q tests/test_postgresql_adapter.py tests/test_postgresql_integration.py
```

The DSN must reference test infrastructure, must never be committed or logged, and
must be supplied through a deployment-controlled secret mechanism. If the integration
module is skipped because `ASCOS_POSTGRES_TEST_URL` is absent, that run cannot be cited
as real PostgreSQL verification.

## Deliberate boundary

Day 4 validates migration, concurrency, and recovery behavior for a bounded,
experimental adapter. It does **not** make PostgreSQL the composed runtime persistence
provider and does not establish production readiness. The adapter still does not
implement the complete `PersistenceProvider` and durable-outbox contracts used by the
composition root. Production composition, backup/restore and point-in-time recovery,
TLS and credential rotation, failover, capacity testing, and sustained soak evidence
remain required follow-up work.
