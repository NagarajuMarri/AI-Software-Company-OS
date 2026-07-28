# Outbox Retry Policy

Failures are classified as non-retryable, immediate retry, bounded exponential
backoff, rate-limited, reconciliation-required, or unknown. Authentication and
invalid payload failures dead-letter. Pre-acceptance provider unavailability
backs off. Rate limits respect a deterministic retry interval. Timeouts with
uncertain acceptance require reconciliation.

Attempt count and safe history persist. Maximum attempts move the operation to
dead letter. Random uncontrolled jitter is not used.
