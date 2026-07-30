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
