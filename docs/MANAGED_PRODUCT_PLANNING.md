# Managed Product Planning Bridge

Milestone 12.3A connects the Project Registry, Project Knowledge Engine, and AI
Project Manager through a provider-neutral planning boundary. It converts a
reviewed product change request into a proposed milestone and ordered task plan.
It does not execute work or modify a managed repository.

## Lifecycle and boundaries

Requests are immutable, bounded, UTC-timestamped records tied to a registered
project. Context building is explicit and never scans a repository: it loads an
existing knowledge snapshot, rejects missing or stale knowledge, selects bounded
file/symbol/statistical data, and includes only the same project's manager state.
Source contents, binary data, credentials, environment secrets, and hidden
reasoning are excluded.

`ManagedProductPlanningProvider` accepts the request and bounded context and
returns structured `ProposedProductMilestone` data. The offline deterministic
provider uses fixed templates and structural knowledge; it makes no network call
and claims no semantic reasoning. A future LLM adapter must accept the same
bounded context, return validated structured output, expose only user-visible
rationale, persist no chain of thought, handle timeouts/malformed output, and
remain subject to explicit human approval.

Proposals begin as `PROPOSED`. Approval, rejection, and supersession are separate
actor-attributed UTC decisions. Providers cannot approve their own output.
Approved content is frozen. Rejection requires a reason and prevents
materialisation.

Materialisation uses a restart-safe reconciliation protocol rather than claiming
an unsupported transaction across the independent manager and planning files.
Before manager mutation, ASCOS durably writes a deterministic operation record.
The operation advances through `PREPARED`, `MANAGER_COMMITTED`, and `COMPLETED`;
failed saves may record `FAILED`, while mismatched durable manager state records
`RECONCILIATION_REQUIRED`.

On retry or restart, the service compares the existing inactive milestone,
ordered tasks and dependencies, structured metadata, risks, and approval
decision with the approved proposal. An exact match resumes completion without
duplicates. Partial or mismatched state raises a typed reconciliation error.
The proposal receives `materialised_at` only after the expected manager state is
durable. The operation becomes `COMPLETED` only after that proposal update is
durable, so full materialisation requires both records. Materialisation still
uses `AIProjectManager` validation and creates no runtime work item, branch,
commit, pull request, merge, deployment, or product-repository write.

## Persistence and CLI

Schema version 1 records use deterministic UTF-8 JSON and atomic replacement:

```text
<state-root>/planning/<project-id>/requests/<request-id>.json
<state-root>/planning/<project-id>/contexts/<request-id>.json
<state-root>/planning/<project-id>/proposals/<proposal-id>.json
<state-root>/planning/<project-id>/materialisations/<operation-id>.json
```

Materialisation records use schema version 1 and contain the operation,
project/proposal/milestone identities, expected task and risk IDs, expected
approval-decision ID, lifecycle state, UTC timestamps, and optional failure
details.

CLI groups include `planning request create|show|list`,
`planning context build`, `planning proposal generate|show|list|approve|reject|materialise`,
and `planning status`. Every invocation requires explicit registry and state-root
paths and supports `--json`.

Current planning limitations: one deterministic template provider, no live LLM,
no automatic revision generation, and context relevance based on stable bounded
ordering rather than semantic search.

Milestone 12.3B adds an optional downstream execution bridge. Planning remains
proposal-only: materialisation does not create runtime work or authorize a
workspace, provider, product write, commit, push, or pull request. Those require
a new immutable execution request and separate exact-plan human approval.
