# External Operation Reconciliation

Reconciliation claims uncertain operations using the same lease and fencing
rules. It queries the provider by stable idempotency identity. A confirmed
result is applied idempotently; an unverifiable outcome is retained through a
dead-letter decision rather than guessed as success or failure.

Crash recovery never marks dispatching work successful. Expired `CLAIMED` work
is eligible again, while expired `DISPATCHING` work becomes
`RECONCILIATION_REQUIRED`.
