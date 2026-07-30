# Managed Execution Reconciliation

Execution spans independent manager, runtime, workspace, Git, coding-provider,
gate, and GitHub boundaries. ASCOS does not claim a cross-system transaction.

Each plan has a durable lifecycle operation:

`PREPARED → WORKSPACE_READY → BRANCH_READY → RUNTIME_CREATED →
CODING_SUBMITTED → CODING_COMPLETED → QUALITY_GATES_COMPLETED →
REVIEW_REQUIRED → REVIEW_APPROVED → COMMIT_CREATED → PUSH_COMPLETED →
PR_CREATED → COMPLETED`

`FAILED`, `CANCELLED`, `SUCCEEDED`, `REJECTED`, `SUPERSEDED`, and
`RECONCILIATION_REQUIRED` cannot re-enter ordinary execution. Each public
mutation accepts an explicit predecessor phase. Execution approval binds the
plan version; completion approval separately binds the evidence digest.

Every non-transactional effect first persists a `PREPARED` record with exact
expected identity, then `IN_PROGRESS`, and only becomes `COMPLETED` after
inspection. An exception after invocation records `UNCERTAIN`. Reconciliation
inspects the expected workspace tree, local branch/base SHA, commit parent,
message and paths, remote ref SHA, or exact draft PR repository/base/head/marker
and content. Exact state is reused. Missing state may be retried from durable
intent. Divergent or multiple state is never reset, rebased, force-updated, or
deleted; it becomes `RECONCILIATION_REQUIRED` with operator diagnostics.

Runtime mappings use the same prepared-effect protocol. Exact pre-existing
mappings are reused and missing expected mappings can be completed
deterministically. Foreign or divergent mappings stop recovery without creating
duplicates.

Schema-version-1 sorted UTF-8 JSON lives under
`<state-root>/execution/<project-id>/` in `requests/`, `plans/`, `operations/`,
`task-mappings/`, `workspaces/`, `coding-results/`, `quality-gates/`,
`evidence/`, and `repository-effects/`. Writes use atomic same-directory
replacement and restrictive permissions where supported. Corruption, traversal,
and unsupported schemas are rejected. These local atomic writes do not make
Git, GitHub, provider, runtime, and filesystem effects one transaction.
