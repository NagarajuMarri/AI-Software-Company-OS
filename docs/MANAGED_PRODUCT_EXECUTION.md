# Managed Product Execution Bridge

Milestone 12.3B connects an approved, completed 12.3A materialisation to
controlled runtime execution. It preserves separate models for project-manager
tasks, runtime work, software-company agents, coding providers, repository
effects, and human decisions.

An immutable execution request declares selected tasks, mode, branch, policies,
provider capability, limits, and correlation identity. `PLAN_ONLY`, `DRY_RUN`,
and `SIMULATED` cannot mutate a product. `CONTROLLED_WRITE` additionally
requires the explicit `--allow-product-write` switch.

Plan generation is deterministic and ends in `AWAITING_APPROVAL`. A separate
human decision approves an exact plan ID and version. Coding providers cannot
approve their own work. Successful coding and required gates produce immutable
review evidence and `REVIEW_REQUIRED`; a second human decision is needed before
task completion or repository effects. Approval never means merge, deployment,
workflow release, or production release.

One approved plan maps to one validated runtime `WorkPackage`; each selected
project task maps to one validated `WorkItem`. Stable records preserve project
task, runtime item, correlation, and causation identities. Managed coding
requests contain stable external/idempotency identities, workspace/branch,
criteria, path and command allow-lists, limits, gates, and artifact
expectations. Result success is never trusted without identity, path, limit,
progress, artifact, status, gate, and prohibited-intent validation.

Workspace, runtime-mapping, branch, commit, push, and draft-PR actions have
separate durable effect records. Each record moves through `PREPARED`,
`IN_PROGRESS`, `COMPLETED`, or `UNCERTAIN`; divergence moves both effect and
execution to `RECONCILIATION_REQUIRED`. Intent contains the deterministic
workspace/repository, plan version, branch/base SHA, reviewed evidence/path,
remote ref/commit, or PR marker and content identities needed to inspect the
external system after restart. Completion is persisted only after exact
inspection. This protocol does not provide cross-system atomicity.

Only schema-versioned coding results accepted by `process_coding_result()` can
feed evidence. Evidence binds the plan/version, project, workspace, branch,
base commit, accepted result IDs, reviewed paths, and exact durable gate
results under one canonical SHA-256 digest. The digest and those bindings are
rechecked before review, commit, push, PR creation, and completion. Commits
stage only evidence-listed paths. Protected branches, force pushes, merges,
deployment, branch deletion, arbitrary Git configuration, and automatic
rebases are not supported.

The CLI provides request create/show/list, plan generate/show/approve/reject,
status, list, and cancellation with explicit registry, planning-state, and
execution-state paths. Expected domain failures return exit code 2.

Current limitations: no live Codex/OpenAI adapter, production workspace host,
network push in default tests, automatic merge/deploy, or operator UI for
divergent reconciliation.
