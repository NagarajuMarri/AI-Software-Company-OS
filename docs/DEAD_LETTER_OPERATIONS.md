# Dead-Letter Operations

Dead-letter records retain operation identity, bounded secret-free payload,
safe attempt history, correlation, failure classification, and reason.
Operators may explicitly retry, abandon, or clone a corrected replacement.
Retry does not erase attempt history, and replacement uses a new operation and
idempotency identity.
