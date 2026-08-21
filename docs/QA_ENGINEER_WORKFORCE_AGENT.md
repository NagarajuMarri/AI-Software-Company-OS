# QA Engineer Workforce Agent

Day 26 operationalizes one bounded QA Engineer Digital Twin on the Day 22 provider-neutral runtime.
It turns the exact persisted Day 24 architecture and the complete ordered Day 25 Engineering family
output into a durable quality plan. The module does not yet create a product workspace or execute
product code.

## Exact role contract

The only admitted Business Role is `AgentRole.QA_ENGINEER`. Its provider is
`deterministic-qa-engineer-v1`, its tool allowlist is empty, its tool-call budget is zero, and live
provider use is disabled. The ordered capability profile is:

1. `test-strategy-planning`
2. `automated-test-specification`
3. `integration-test-design`
4. `defect-reporting`
5. `status-reporting`

The ordered action profile contains the Day 22 execution and evidence actions followed by
`PLAN_QA_ASSIGNMENT`, `SPECIFY_AUTOMATED_TESTS`, `SPECIFY_INTEGRATION_TESTS`,
`REPORT_QA_DEFECTS`, and `REPORT_QA_STATUS`. Role, provider, capability order, action order, tenant,
Twin, assignment, objective, authority, or tool drift fails before provider activity.

## Source-bound assignment

One immutable QA work order binds the exact persisted Software Architect artifact and exactly four
ordered persisted Engineering artifacts:

1. Backend Engineer
2. Frontend Engineer
3. AI Engineer
4. Data Engineer

All sources must share the tenant, opportunity, opportunity digest, architecture identity and
digest, expected draft statuses, and `NOT_SELECTED` pilot state. Each Engineering source is reloaded
from its write-once store before execution. Missing, additional, reordered, fabricated, changed,
cross-tenant, cross-opportunity, or cross-work-order input is rejected.

## Typed output

A successful bounded execution produces one `QAWorkArtifact` containing:

- four test-plan items, one bound to each Engineering artifact;
- four automated-test specifications with fixtures, assertions, and negative cases;
- two integration-test specifications spanning source interfaces;
- two draft defect reports describing source-evidenced specification gaps or integration risks;
- coverage requirements and handoff notes; and
- an explicit status report.

The provider result is untrusted. The service rebuilds the exact provider request and output and
requires both digests to reconcile with the terminal Day 22 receipt before validating the closed
nested schema. The artifact preserves the work-order, architecture, Engineering-source, role,
capability, action, authority, assignment, provider, request/output, and receipt bindings.

## Execution-state truthfulness

Day 26 defines test intent; it does not claim that a product test ran. Every automated and
integration specification remains `NOT_EXECUTED`, every defect remains
`DRAFT_DEFECT_AWAITING_AUTHORIZED_TEST_EXECUTION`, and the artifact remains
`DRAFT_QA_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`. A draft defect is a traceable source finding, not an
observed runtime failure. Product test files and execution require the isolated workspace and
coding/review loop in Days 31–32.

The source architecture remains `DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW`; all Engineering outputs
remain `DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`; the pilot state remains
`NOT_SELECTED`.

## Persistence and restart behavior

Validated artifacts are canonical JSON envelopes stored mode 0600 in tenant/execution-scoped,
path-contained, write-once directories. Reads reject unsafe permissions, symlinks, unknown entries,
oversized or non-canonical content, closed-schema violations, identity drift, and digest tampering.
Raw provider values and exceptions, credentials, secrets, customer data, and local paths are not
persisted.

The Day 22 runtime writes intent before provider activity and records one terminal digest-only
receipt. An exact retry or a restarted service/provider instance reopens the same artifact and
receipt without a second provider effect.

## Founder evidence

Mandatory Chromium CI executes the real QA composition with generic, non-customer fixtures. The
founder-safe report exposes the four role plans, automated and integration specifications, draft
defects, exact architecture and Engineering bindings, receipt digest, zero-tool boundary, and
truthful execution states. The browser verifies restrictive headers and empty console and network
failure collections. The evidence manifest binds the exact Day 26 commit to the approved Day 25
base, sources, work order, role profile, authority, assignment, provider request/output, receipt,
output counts, and screenshot digest.

## Explicit exclusions

Day 26 has no filesystem, product workspace, repository, command, browser tool, network, credential,
test-file write, product-test execution, quality approval, Security, DevOps, Documentation,
multi-agent orchestration, commit, merge, deployment, release, billing, budget-allocation,
architecture-approval, or official pilot-selection authority. Those remain separate locked modules
and human-controlled delivery boundaries.
