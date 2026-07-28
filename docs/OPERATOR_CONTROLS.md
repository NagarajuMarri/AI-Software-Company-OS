# Outbox Operator Controls

Internal operator services inspect operations and attempts, retry or abandon
dead letters, clone corrected replacements, and pause or resume providers.
Actions require an actor identity and reason and append immutable audit
records. No public endpoint or direct database mutation interface is provided.

Payload inspection must remain redacted and bounded. Active claimed or
dispatching work cannot be destructively abandoned.
