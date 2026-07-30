# Provider Reconciliation

Provider submission is not transactionally atomic with local persistence.
ASCOS persists `PREPARED` intent, moves to `SUBMISSION_IN_PROGRESS`, and records
`SUBMITTED` only after exact idempotency-key lookup returns one matching task.

A crash after invocation produces `UNCERTAIN`. One exact match is adopted. No
match or multiple matches becomes `RECONCILIATION_REQUIRED`; replacement work
is never silently submitted. Plan version, project, managed/external task,
workspace, branch, request/context digests, provider, and attempt remain bound.

Progress is durable and monotonic. Identical replay is idempotent; conflicting
replay, regression, foreign identity, altered digests, or forged task identity
blocks the operation. This protocol does not claim cross-system atomicity.
