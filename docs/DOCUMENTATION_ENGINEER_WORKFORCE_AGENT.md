# Documentation Engineer Workforce Agent

ASCOS Day 29 operationalizes one provider-neutral `AgentRole.DOCUMENTATION_ENGINEER` Digital
Twin. The module turns the exact persisted Day 24–28 workforce artifact chain into five typed,
source-validated documentation drafts and one customer handoff while deliberately publishing
nothing.

## Exact inputs

One Documentation work order binds the exact persisted Software Architect artifact; ordered
Backend, Frontend, AI, and Data Engineering artifacts; QA artifact; Security artifact; DevOps
artifact; tenant; opportunity; assignment; acceptance checks; risks; constraints; and current
delegated authority. QA, Security, and DevOps must bind the same architecture and ordered
Engineering digests, while DevOps must also bind the exact QA and Security digests.

Every source is reloaded from its canonical store before provider activity. Missing, additional,
reordered, stale, fabricated, cross-tenant, or differently bound sources fail closed.

## Exact profile

The deterministic offline provider is `deterministic-documentation-engineer-v1`. Its ordered
capabilities cover technical, user, API, operations, and release documentation; customer handoff;
source validation; and status reporting. Its ordered actions include only the generic Day 22
assigned-work/evidence actions and corresponding draft, handoff, validation, and reporting actions.

The profile has no tools, zero tool calls, and no live-provider authorization. It cannot read or
write a filesystem, workspace, environment, repository, customer channel, publication system,
credential, network, deployment, release, or provider target.

## Typed output

One successful bounded execution produces one closed `DocumentationWorkArtifact` containing:

- one `TECHNICAL` record bound to Architecture and all four Engineering sources;
- one `USER` record bound to Frontend Engineering and QA;
- one `API` record bound to Architecture plus Backend, Frontend, and AI Engineering;
- one `OPERATIONS` record bound to Security and DevOps;
- one `RELEASE` record bound to all eight upstream artifact digests;
- one customer handoff covering exactly those five document IDs; and
- acceptance checks, coverage requirements, and a bounded-complete status report.

Every record has a typed audience, purpose, exact source digests, sections, validation checks,
`VALIDATED_AGAINST_EXACT_SOURCES` validation state,
`DRAFT_SOURCE_VALIDATED_AWAITING_HUMAN_REVIEW` status, and `NOT_PUBLISHED` publication state. The
complete artifact remains `DRAFT_DOCUMENTATION_OUTPUT_AWAITING_HUMAN_REVIEW`. Validation means
only closed-schema and exact-source validation; it does not claim that product implementation,
tests, scans, infrastructure, deployment, release, or customer delivery occurred.

## Runtime and persistence guarantees

Before execution, ASCOS validates the exact ordered role/capability/action profile, provider,
tool-free Twin, tenant, assignment, objective digest, source chain, authority expiry, zero-tool
budget, and offline-provider boundary. After execution, it rebuilds the provider request and
deterministic output and reconciles both digests with the terminal Day 22 runtime receipt.

Only reconciled, closed, typed output may enter the Day 29 store. The artifact is canonical,
tenant/execution scoped, write once, bounded, mode 0600, path contained, integrity checked, and
restart safe. Exact retries reopen the same receipt and artifact without another provider effect.
Reads reject tampering, non-canonical data, unsafe permissions, symlinks, unknown entries, identity
drift, and malformed nested records.

## End-user evidence

Mandatory exact-head Chromium testing renders a founder-safe report showing all five draft
documents, their validation/publication states, customer handoff, exact
Architecture/Engineering/QA/Security/DevOps digests, and authority exclusions. The browser asserts
restrictive headers, complete document visibility, empty console errors, and empty network
failures. The manifest binds the exact commit, approved Day 28 base, every upstream artifact, work
order, profile, authority, assignment, provider request/output, receipt, document states, and
screenshot digest.

The fixture is generic verification data. It is not a pilot selection, product workspace,
publication target, deployment, release, or customer communication.

## Explicit exclusions

Day 29 does not write documentation files or repositories; publish or send documents; access a
customer channel; implement or test a product; run scans, CI, migrations, deployments, monitoring,
or rollback; commit; merge; release; approve architecture, quality, security, DevOps, or risk;
perform multi-agent orchestration; spend budget; bill; or select an official pilot. Those actions
require later locked modules and separate human authorization.
