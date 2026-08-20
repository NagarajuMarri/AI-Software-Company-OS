# Software Architect Workforce Agent

Day 24 operationalizes one bounded Software Architect on the provider-neutral Day 22 Digital Twin
runtime. It is an architecture-proposal boundary, not an architecture-approval or engineering
execution boundary.

## Exact source and output

The agent accepts only the exact canonical Day 23 Product Manager plan already persisted for the
same tenant and opportunity. The service verifies the artifact kind, Product Manager Business Role,
opportunity and source digests, draft state, and `NOT_SELECTED` pilot state before preparing the
assignment. A changed, fabricated, cross-tenant, cross-opportunity, missing, corrupt, or unpersisted
plan fails before provider activity.

One successful assignment produces a closed typed `ArchitectureProposalArtifact` containing:

- a domain boundary and explicit architecture principles;
- components with responsibilities, interfaces, and data ownership;
- integration points and the data lifecycle;
- security controls and a runtime-verifiable quality strategy;
- concrete technology recommendations with rationale and alternatives;
- ADR drafts structured around context, decision, consequences, and human review;
- rated technical risks with impact, mitigation, and escalation; and
- a status report naming completed work, next actions, blockers, and human decisions.

The deterministic verification provider proposes Python 3.11+, a standards-based HTTPS interface,
PostgreSQL 16+, and pytest with Playwright Chromium. These are reviewable recommendations, not
automatically accepted product decisions. The exact product and future human review may change them.

## Authority profile

The Digital Twin maps only to `AgentRole.SOFTWARE_ARCHITECT`. Its capabilities are architecture
proposal, technology selection, ADR drafting, technical-risk identification, and status reporting.
Its delegation permits only assigned-work execution, execution evidence, and those five proposal
actions. The tool allowlist is empty, tool-call budget is zero, and live-provider authorization is
false.

The role cannot approve architecture or scope, create engineering tasks, access a repository or
filesystem, run commands, use the network, read credentials, write code, commit, merge, deploy,
release, bill, allocate budget, select an official pilot, or orchestrate other agents. Backend,
frontend, AI, and data engineering assignments remain Day 25.

## Validation and persistence

The runtime records the immutable execution intent and terminal digest receipt. The architecture
service reconstructs the exact typed provider request and deterministic result, checks the request
and output digests against that receipt, validates every nested field and status, and only then saves
the proposal. Duplicate keys, unknown fields, accepted ADRs, approved recommendations, selected
pilots, invalid ratings, and identity/digest mismatches fail closed.

The file adapter uses a tenant/execution-scoped, closed directory and one canonical write-once JSON
record with mode 0600. It rejects traversal, escaping or symlinked paths, unknown entries, unsafe
permissions, malformed or oversized content, non-canonical records, and digest tampering. Exact retry
and restart reopen the same receipt and artifact without repeating the provider effect.

## Review state and evidence

The proposal is always `DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW`. Every technology recommendation
and ADR is `PROPOSED`, every ADR requires human approval, and pilot state remains `NOT_SELECTED`.
Major architecture acceptance remains a founder/human action outside this module.

Exact-head CI runs unit, security, regression, compilation, lint, typing, example, PostgreSQL, and
real Chromium coverage. Chromium inspects a founder-safe report containing the architecture,
technology proposals, proposed ADRs, technical risks, exact Product-Manager handoff, receipt and
authority boundary; it verifies restrictive response headers and empty console/network failure
collections. The uploaded manifest binds the exact commit and approved Day 23 base without secrets,
credentials, cookies, raw provider payloads, or local paths.
