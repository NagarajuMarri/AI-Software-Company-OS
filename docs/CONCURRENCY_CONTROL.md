# Concurrency Control

Every checkpoint commit carries an expected runtime state version. The
transaction locks the writer path, compares that version, and advances it
exactly once. Two writers observing the same version cannot both commit: the
winner persists its checkpoint and events; the loser gets
`RuntimeVersionConflictError` with no partial rows or gaps.

Retries are explicit: reload, validate the intended operation, then submit a
new commit. SQLite busy/locked failures map to
`ConcurrentPersistenceError`. Event ID, global-position, and
aggregate-sequence constraints provide a second defense; batches are atomic.
