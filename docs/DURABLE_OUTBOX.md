# Durable External Operation Outbox

ASCOS records external intent before invoking Git, GitHub, or coding-agent
providers. The task mutation, runtime event, and in-memory outbox record join
the same runtime transaction. Database-backed repositories serialize claims
and state transitions with `BEGIN IMMEDIATE`; file-backed state uses atomic
replacement.

Delivery is at least once. Local exactly-once effect is approached through
stable operation IDs, provider idempotency keys, request/result fingerprints,
and idempotent result application. No provider call occurs in the transaction
that records intent.

SQLite provides deterministic single-host writer serialization. PostgreSQL
implementations should preserve the repository contract while using verified
row-locking/skip-locked semantics; those semantics are not claimed here.
