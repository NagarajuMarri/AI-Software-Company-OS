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

Workspace, branch, commit, push, and draft-PR actions are separate explicit
operations. Commits require reviewed workspace state and stage only
evidence-listed paths. Protected branches, force pushes, merges, deployment,
branch deletion, arbitrary Git configuration, and automatic rebases are not
supported.

The CLI provides request create/show/list, plan generate/show/approve/reject,
status, list, and cancellation with explicit registry, planning-state, and
execution-state paths. Expected domain failures return exit code 2.

Current limitations: no live Codex/OpenAI adapter, production workspace host,
network push in default tests, automatic merge/deploy, or operator UI for
divergent reconciliation.
