# Governed Multi-agent Orchestration

## Scope

Day 30 implements the locked ASCOS multi-agent orchestration module. It coordinates the exact
persisted workforce artifacts produced by Days 23–29 without rerunning those agents and without
creating a product workspace. The source order is immutable: CEO, Product Manager, Architecture,
Backend, Frontend, AI, Data, QA, Security, DevOps, and Documentation.

## Orchestration contract

One `OrchestrationWorkOrder` binds every source digest, the assignment, objectives, acceptance
checks, constraints, and issue time. One expiring `OrchestrationAuthority` binds that work order,
the canonical source-set digest, the exact action profile, an empty tool profile, zero tool calls,
no live provider, and a bounded parallel-work limit.

`MultiAgentOrchestrationService` verifies every source against its write-once store and validates
the complete upstream chain before invoking a replaceable `OrchestrationPlanningProvider`.
`DeterministicOrchestrationProvider` is the verification implementation; it has no tool gateway and
no operational side effects.

## Output

The immutable artifact contains:

- eleven acyclic dependency nodes covering the full workforce chain;
- nine ordered waves, including one four-role Engineering parallel wave;
- eleven context packages limited to exact artifact identity, digest, status, and bounded summary;
- seven draft, undispatched handoffs;
- three conflict routes that block affected downstream work;
- three human-owned escalation records; and
- explicit plan-only status and next-authorization blockers.

All context packages exclude credentials, secrets, raw customer data, and local paths. Conflicting
Engineering ownership returns to Architecture and human review. QA disagreement returns to the
responsible Engineering role while QA remains an independent gate. Security conflict blocks
operational progression and requires human risk and release authorities.

## Persistence and recovery

The store writes one canonical schema-versioned JSON envelope at mode 0600 under a contained
tenant/execution path. It rejects symlinks, unexpected entries, unsafe permissions, unknown fields,
oversized or non-canonical data, path escapes, identity drift, and digest tampering. An exact retry
or process restart reopens the same artifact without invoking the planning provider again; changed
work, authority, provider, or source identities conflict with the write-once record.

## Authority boundary

Day 30 plans coordination only. It cannot execute agents, dispatch handoffs, resolve conflicts,
accept risk, approve decisions, access a product workspace, read or write repositories, run
commands, use credentials, access a network, merge, deploy, publish, release, bill, allocate budget,
or select an official pilot. Day 31 isolated workspace behavior requires separate founder approval.

## Verification

Focused tests cover exact source chaining, graph and wave semantics, bounded contexts, authority
drift, source substitution, provider boundary expansion, write-once conflict handling,
retry/restart idempotency, path containment, permissions, unknown entries, and tamper detection.
Real Chromium renders a founder-safe report and records screenshot, console, network, source,
authority, and artifact evidence bound to the exact commit in CI.
