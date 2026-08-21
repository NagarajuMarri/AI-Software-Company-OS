# Security Engineer Workforce Agent

Day 27 operationalizes one bounded Security Engineer Digital Twin on the Day 22 provider-neutral
runtime. It turns the exact persisted Day 24 architecture, all four ordered Day 25 Engineering
artifacts, and the exact persisted Day 26 QA artifact into a durable security plan. The module does
not yet create or inspect a product workspace and does not execute a security scanner.

## Exact role contract

The only admitted Business Role is `AgentRole.SECURITY_ENGINEER`. Its provider is
`deterministic-security-engineer-v1`, its tool allowlist is empty, its tool-call budget is zero,
and live-provider use is disabled. The ordered capability profile is:

1. `threat-modeling`
2. `dependency-check-specification`
3. `secret-check-specification`
4. `security-finding-reporting`
5. `status-reporting`

The ordered action profile contains the Day 22 execution and evidence actions followed by
`PLAN_SECURITY_ASSIGNMENT`, `MODEL_SECURITY_THREATS`, `SPECIFY_DEPENDENCY_CHECKS`,
`SPECIFY_SECRET_CHECKS`, `REPORT_SECURITY_FINDINGS`, and `REPORT_SECURITY_STATUS`. Role,
provider, capability order, action order, tenant, Twin, assignment, objective, authority, source,
or tool drift fails before provider activity.

## Exact upstream bindings

One immutable Security work order binds:

- the exact persisted Software Architect artifact;
- exactly four ordered persisted Engineering artifacts—Backend, Frontend, AI, and Data; and
- the exact persisted QA artifact that consumes the same architecture and Engineering set.

Every source must share tenant, opportunity, opportunity digest, architecture identity and digest,
required draft status, and `NOT_SELECTED` pilot state. Every source is reloaded from its write-once
store before execution. Missing, additional, reordered, fabricated, changed, cross-tenant,
cross-opportunity, or cross-work-order input is rejected.

## Typed output

A successful bounded execution produces one `SecurityWorkArtifact` containing:

- exactly six STRIDE threat records, one for each category;
- four dependency-check specifications, one per Engineering source;
- four secret-check specifications, one per Engineering source;
- three draft security findings bound to the exact QA and relevant Engineering sources;
- coverage requirements and handoff notes; and
- an explicit status report.

Every threat identifies its assets, trust boundary, scenario, required security properties,
mitigations, and residual risk. Dependency specifications define manifest scope, provenance and
vulnerability checks, severity threshold, and required evidence. Secret specifications define
authorized search scopes, detector classes, allowlist policy, incident response, and redacted
evidence requirements.

The provider result is untrusted. The service rebuilds the exact request and output and requires both
digests to reconcile with the terminal Day 22 receipt before validating the complete closed schema.
The artifact preserves work-order, architecture, Engineering, QA, role, capability, action,
authority, assignment, provider request/output, and receipt bindings.

## Truthful non-execution state

Day 27 defines security intent; it does not claim that a product scan or validation ran. Every threat
validation, dependency check, and secret check remains `NOT_EXECUTED`. Every finding remains
`DRAFT_FINDING_AWAITING_AUTHORIZED_SECURITY_VALIDATION`, and the complete artifact remains
`DRAFT_SECURITY_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`. Architecture, Engineering, and QA statuses
remain unchanged and pilot state remains `NOT_SELECTED`.

Dependency manifests, lockfiles, source files, runtime configuration, credentials, and scanner
execution require the isolated workspace and coding/review loop in Days 31–32. Draft findings are
source-evidenced risks, not observed product vulnerabilities.

## Persistence and restart behavior

Validated artifacts are canonical JSON envelopes stored mode 0600 in tenant/execution-scoped,
path-contained, write-once directories. Reads reject unsafe permissions, symlinks, unknown entries,
oversized or non-canonical content, closed-schema violations, identity drift, and digest tampering.
Raw provider values and exceptions, credentials, secrets, customer data, and local paths are not
persisted.

The Day 22 runtime writes intent before provider activity and records one terminal digest-only
receipt. An exact retry or restarted service/provider instance reopens the same artifact and receipt
without a second provider effect.

## Founder evidence

Mandatory Chromium CI executes the real Security composition with generic non-customer fixtures.
The founder-safe report exposes all six threat categories, dependency and secret specifications,
draft findings, exact architecture/Engineering/QA bindings, receipt digest, zero-tool boundary, and
truthful non-execution states. The browser verifies restrictive headers and empty console and
network failure collections. The evidence manifest binds the exact Day 27 commit to the approved
Day 26 base, sources, work order, profile, authority, assignment, provider request/output, receipt,
output counts, and screenshot digest.

## Explicit exclusions

Day 27 has no filesystem, product workspace, repository, command, browser tool, network, credential,
manifest, lockfile, SBOM, scanner, remediation, security approval, risk acceptance, quality
approval, DevOps, Documentation, multi-agent orchestration, commit, merge, deployment, release,
billing, budget-allocation, architecture-approval, or official pilot-selection authority. Those
remain separate locked modules and human-controlled delivery boundaries.
