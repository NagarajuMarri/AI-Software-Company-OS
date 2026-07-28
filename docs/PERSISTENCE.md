# Persistence Providers

Outbox repositories are provider-neutral. In-memory storage participates in
runtime transaction snapshots and checkpoints. File storage writes canonical
JSON using atomic replacement. SQLite stores a versioned canonical state plus
indexed operation projections for eligibility, task, aggregate, and
idempotency queries.

Unknown newer file or database schemas are rejected. Stored state excludes raw
claim tokens, credentials, provider clients, and process handles. Runtime
checkpoint restore preserves terminal/scheduled work and safely reclassifies
expired or uncertain work.
