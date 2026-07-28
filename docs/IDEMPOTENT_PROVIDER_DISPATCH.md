# Idempotent Provider Dispatch

Every operation has a unique ID and stable idempotency key. The request
fingerprint binds operation type, provider, aggregate version, payload schema,
and canonical payload. Reusing a key with a changed fingerprint is rejected.

Providers supporting remote idempotency receive the stable key. Other
providers rely on local deduplication and reconciliation. Successful results
are fingerprinted; applying the same result twice is a no-op, while a changed
result for the same key is rejected.
