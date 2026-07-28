# Outbox Operation Lifecycle

Operations move through `PENDING`, `CLAIMED`, `DISPATCHING`, and a terminal or
scheduled state. Successful dispatch becomes `SUCCEEDED`; classified failures
become `RETRY_WAIT`, `RECONCILIATION_REQUIRED`, or `DEAD_LETTER`. Pending work
may be explicitly cancelled.

Claims carry an owner, UTC expiry, hashed opaque token, and monotonic fencing
token. Selection is deterministic by priority, availability, creation time,
then operation ID. Expired claimed work becomes pending; expired dispatching
work becomes reconciliation-required because provider acceptance is uncertain.
