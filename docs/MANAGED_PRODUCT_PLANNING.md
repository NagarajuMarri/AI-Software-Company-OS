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

Materialisation preflights identity and ID conflicts, then uses
`AIProjectManager` to create one inactive milestone and ordered tasks. It
preserves dependencies, criteria, candidate files, quality gates, risks, and
approval evidence. It is idempotent and creates no runtime work item, branch,
commit, pull request, merge, deployment, or product-repository write.

## Persistence and CLI

Schema version 1 records use deterministic UTF-8 JSON and atomic replacement:

```text
<state-root>/planning/<project-id>/requests/<request-id>.json
<state-root>/planning/<project-id>/contexts/<request-id>.json
<state-root>/planning/<project-id>/proposals/<proposal-id>.json
```

CLI groups include `planning request create|show|list`,
`planning context build`, `planning proposal generate|show|list|approve|reject|materialise`,
and `planning status`. Every invocation requires explicit registry and state-root
paths and supports `--json`.

Current limitations: one deterministic template provider, no live LLM, no
automatic revision generation, no runtime execution bridge, and context
relevance based on stable bounded ordering rather than semantic search.
