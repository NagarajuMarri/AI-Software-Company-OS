# External Tool Execution

External tool intent can be scheduled through the durable outbox. Workers hold
short-lived fenced claims; command/provider execution remains outside the
transaction that created intent.

ASCOS exposes provider-neutral command and workspace contracts. The local
runner accepts an allow-listed executable plus a validated argument tuple,
never a shell string. It enforces workspace containment, environment
allow-listing, NUL rejection, timeouts, cancellation, bounded output, and
structured exit results. `shell=True` is forbidden.

The default child environment contains only the host executable search path
(`PATH`) and, on Windows, `SYSTEMROOT`, so allow-listed tools remain portable
without inheriting credentials or unrelated process state. Callers may replace
that minimal base explicitly. Request-specific variables are still rejected
unless their names are allow-listed, and their values are redacted from output.

The local workspace provider uses a caller-owned root, unique identifiers, and
resolved-path containment checks. Traversal and symlink escape are rejected
where the operating system exposes resolved link targets. Portable runtime
state stores workspace references, not credentials or reusable authentication.
