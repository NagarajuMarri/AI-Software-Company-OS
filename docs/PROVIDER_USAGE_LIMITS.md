# Provider Usage Limits

Operations record available input/output units, duration, request count, model,
retry count, and reported cost/currency. Missing cost remains unknown.
Configuration bounds attempts, timeout, prompt bytes, and result bytes;
execution metadata may impose stricter token and cost budgets. Violations block
further live submission and require human action.

Only explicitly retryable failures may retry. Each attempt has a new number and
idempotency key linked to the task. ASCOS does not retry uncertain submission,
identity/digest/workspace/branch changes, cancellation,
reconciliation-required state, or exhausted budgets.
