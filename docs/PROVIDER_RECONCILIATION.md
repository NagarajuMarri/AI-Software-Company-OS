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

Deterministic-provider recovery may use its test-local idempotency index, but
ASCOS revalidates provider, operation, project, plan/version, managed/external
task, workspace, branch, request/context digest, and idempotency key. Live
recovery instead uses the durable response receipt. The synchronous Responses
API adapter does not claim remote search-by-idempotency support. No receipt
means `RECONCILIATION_REQUIRED`; multiple or mismatched evidence is also
rejected.

Patch reconciliation compares durable intent with exact file hashes and Git
state. No applied files may be explicitly retried; all exactly applied files
are adopted; partial, missing-checkpoint, or divergent application requires
operator reconciliation. Accepted manifest digests are rechecked against the
workspace.
