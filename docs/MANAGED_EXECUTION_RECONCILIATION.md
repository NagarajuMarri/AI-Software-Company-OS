# Managed Execution Reconciliation

Execution spans independent manager, runtime, workspace, Git, coding-provider,
gate, and GitHub boundaries. ASCOS does not claim a cross-system transaction.

Each plan has a durable operation:

`PREPARED → WORKSPACE_READY → BRANCH_READY → RUNTIME_CREATED →
CODING_SUBMITTED → CODING_COMPLETED → QUALITY_GATES_COMPLETED →
REVIEW_REQUIRED → REVIEW_APPROVED → COMMIT_CREATED → PUSH_COMPLETED →
PR_CREATED → COMPLETED`

`FAILED`, `CANCELLED`, and `RECONCILIATION_REQUIRED` preserve uncertainty.
Records carry exact project/proposal/milestone/task/runtime, workspace, branch,
provider, gate, evidence, approval, commit, push, and PR identities. Retries
compare deterministic identities; partial or divergent mappings are not assumed
successful and require operator resolution.

Schema-version-1 sorted UTF-8 JSON lives under
`<state-root>/execution/<project-id>/` in `requests/`, `plans/`, `operations/`,
`task-mappings/`, `workspaces/`, `quality-gates/`, and `evidence/`. Writes use
atomic same-directory replacement and restrictive permissions where supported.
Corruption, traversal, and unsupported schemas are rejected.
