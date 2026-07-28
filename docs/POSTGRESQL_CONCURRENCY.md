# PostgreSQL Concurrency

Claims use `SELECT … FOR UPDATE SKIP LOCKED` in one transaction, ordered by priority,
availability, creation time, and operation ID. That transaction stores a token hash,
advances fencing, assigns owner and expiry, and changes status. Rollback confirms no
claim and releases locks. Runtime, heartbeat, and health writes use expected versions.

Real multi-connection behavior remains unverified when no test URL is configured.
