# Quality Gate Profiles

A project-specific profile contains ordered argument-array commands, timeouts,
required flags, expected exit codes, executable/environment allow-lists, bounded
artifact capture, redaction, and failure policy.

Gates run only in the managed workspace through `LocalCommandRunner`, which uses
`shell=False`, bounded time/output, and secret-value redaction. Results are
`PASSED`, `FAILED`, `TIMED_OUT`, `NOT_RUN`, `CANCELLED`, or `ERROR`; a required
gate that did not run is never successful. Profiles are not Python-specific.
The isolated pilot demonstrates compile, pytest, targeted-boundary, and diff
validation gates.

Validation occurs before the first gate: the command must be a non-empty
immutable argument array, its executable must be allow-listed, shell
interpreters are rejected, and timeout is bounded. The child environment is
built from the runner's minimal platform base (`PATH`, plus `SYSTEMROOT` on
Windows) and explicitly allowed supplied values; unrestricted process
environment is not inherited. Profile redactions, allowed environment values,
and standard token/secret/password/API-key/credential forms are scrubbed, and
stdout/stderr are bounded before persistence.

`stop-required` records the failed required gate and durable `NOT_RUN` results
for the remainder; `continue` executes the full ordered profile. Exactly one
durable result is required per configured gate. A required `FAILED`,
`NOT_RUN`, `ERROR`, `TIMED_OUT`, or `CANCELLED` result blocks evidence.
