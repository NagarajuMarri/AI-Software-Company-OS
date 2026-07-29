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
