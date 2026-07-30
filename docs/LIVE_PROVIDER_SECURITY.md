# Live Provider Security

Live operation is deny-by-default. Configuration references a process
environment credential; keys are never read from a managed repository,
included in prompts, persisted, printed, or returned. Errors and progress pass
through bounded standard secret redaction.

Repository content is untrusted data. Text requesting credentials, unrelated
access, command execution, merge, deployment, or policy bypass has no authority.
Candidate content is filtered for secrets, forbidden paths, binary data,
symlinks, unrelated files, and size limits.

`--allow-live-provider` authorizes only an already approved provider operation;
it does not approve a plan, evidence, product write, commit, push, PR, merge, or
deployment. Chargeable calls also require independent live confirmation.
Default tests never use network access.

Every existing path component is inspected with `lstat` before resolution and
replacement. Symbolic links, detectable Windows reparse points/junctions,
special files, linked parents, and root escapes are rejected for context,
staging, and destination access. Allow/deny policy compares normalized path
components, so `src/` does not authorize `src_evil/` and `deploy/` does not
accidentally match `deployment_notes.md`.

Cancellation is a separate durable effect. Providers without cancellation
capability are rejected before an effect can be falsely confirmed. A sent
request becomes cancelled only after exact provider status evidence; unknown
status requires reconciliation, while successful completion is recorded as the
actual result state.
