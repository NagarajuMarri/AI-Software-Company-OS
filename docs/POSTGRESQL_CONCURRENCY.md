# PostgreSQL Concurrency

Claims use `SELECT … FOR UPDATE SKIP LOCKED` in one transaction, ordered by priority,
availability, creation time, and operation ID. That transaction stores a token hash,
advances fencing, assigns owner and expiry, and changes status. Rollback confirms no
claim and releases locks. An expired `CLAIMED` operation is eligible for a fenced
reclaim; the new claim replaces the token hash and owner, advances the fence, and makes
the stored ownership identity differ from the stale claim. Runtime, heartbeat, and
health writes use expected versions. Enforcing owner, token, and fencing checks on every
later outbox transition remains part of the incomplete full outbox contract.

The always-scheduled PostgreSQL CI job verifies these properties using independent
connections to PostgreSQL 16. It also verifies concurrent migration serialization,
single-winner optimistic writes, and recovery through a fresh repository connection.
Fake connections and skipped integration tests remain useful unit evidence but are not
real concurrency or recovery evidence.

These checks cover the SQL adapter boundary only. They do not prove distributed worker
correctness, full outbox-provider compatibility, production pool sizing, failover, or
long-running contention behavior. Those require composition-level and deployment-level
validation before PostgreSQL can be called production-ready.
