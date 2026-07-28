# External Task Lifecycle

External tasks progress through controlled created, queued, running, review,
approval/rejection, and completion states. Approval is separate from
completion. Invalid jumps fail without storing events.

External side effects use a durable-intent pattern: record `PLANNED` and
`STARTED`, perform the provider call outside the rollbackable transaction, then
atomically record `SUCCEEDED` or `FAILED`. An interruption after start restores
as `RECONCILIATION_REQUIRED`. This is an at-least-once boundary; providers
should accept idempotency keys and reconciliation must inspect remote state
before retry.
