# Security Boundaries

Credentials are injected only at adapter invocation and are excluded from
checkpoints, events, task payloads, command logs, and exception messages.
Executables, environment keys, repository URLs, paths, branches, output size,
and timeouts are allow-listed or bounded.

External providers and generated patches are untrusted. Human review is
required before approval; protected branches deny writes by default. Operators
must restrict workspace roots, use least-privilege credentials, review audit
records, reconcile interrupted operations, and rotate any credential suspected
of exposure.
