# External Tool Execution

ASCOS exposes provider-neutral command and workspace contracts. The local
runner accepts an allow-listed executable plus a validated argument tuple,
never a shell string. It enforces workspace containment, environment
allow-listing, NUL rejection, timeouts, cancellation, bounded output, and
structured exit results. `shell=True` is forbidden.

The local workspace provider uses a caller-owned root, unique identifiers, and
resolved-path containment checks. Traversal and symlink escape are rejected
where the operating system exposes resolved link targets. Portable runtime
state stores workspace references, not credentials or reusable authentication.
