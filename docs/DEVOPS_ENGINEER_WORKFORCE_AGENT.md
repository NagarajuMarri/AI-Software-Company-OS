# DevOps Engineer Workforce Agent

ASCOS Day 28 operationalizes one provider-neutral `AgentRole.DEVOPS_ENGINEER` Digital Twin. The
module prepares the operational path for an isolated preview environment while deliberately
performing no operational action.

## Exact inputs

One DevOps work order binds:

- the exact persisted Day 24 Software Architect artifact;
- the ordered Day 25 Backend, Frontend, AI, and Data Engineering artifacts;
- the exact persisted Day 26 QA artifact bound to that same architecture and Engineering set;
- the exact persisted Day 27 Security artifact bound to that same architecture, Engineering set,
  and QA artifact;
- the tenant, opportunity, assignment, role, objective, acceptance checks, risks, constraints, and
  current delegated authority.

Each source is reloaded from its canonical store before provider activity. Missing, additional,
reordered, stale, fabricated, cross-tenant, or differently bound sources fail closed.

## Exact profile

The deterministic offline provider is `deterministic-devops-engineer-v1`. The ordered capabilities
are CI-pipeline planning, preview-environment planning, migration planning, deployment planning,
monitoring planning, rollback planning, and status reporting. The ordered actions include only the
generic Day 22 assigned-work/evidence actions and the corresponding DevOps planning/reporting
actions.

The profile has no tools, zero tool calls, and no live-provider authorization. It cannot read a
filesystem, workspace, environment, repository, credential, secret, network, infrastructure,
provider, CI runner, deployment service, monitoring backend, or release system.

## Typed output

One successful bounded execution produces a closed `DevOpsWorkArtifact` containing:

- `CIPipelinePlan`: ordered validation, quality, integration/browser/persistence, QA/Security, and
  evidence gates bound to all four Engineering artifacts plus exact QA and Security digests;
- `PreviewEnvironmentPlan`: an `ISOLATED_NON_PRODUCTION_PREVIEW` target, component coverage,
  isolation controls, non-secret configuration contract, opaque secret-reference policy, health
  checks, and lifecycle preparation;
- `MigrationPlan`: the exact Data Engineering source and only its component scope, with preflight,
  apply, verification, and rollback preparation;
- `DeploymentPlan`: preview-only prerequisites, dependency-ordered steps, human approval gates,
  evidence requirements, and success criteria;
- `MonitoringPlan`: preview-only availability, performance, persistence, provider, isolation,
  security, browser, and evidence signals plus alert and dashboard requirements;
- `RollbackPlan`: exact deployment/migration plan bindings, triggers, reversible steps, data-safety
  controls, verification, and mandatory human escalation;
- coverage requirements, handoff notes, and a bounded-complete status report.

Every nested plan has `execution_state=NOT_EXECUTED`. Models reject production targets, claimed
execution, changed source digests, cross-source component scopes, unbound rollback plans, changed
statuses, or pilot selection. The complete output remains
`DRAFT_DEVOPS_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`.

## Runtime and persistence guarantees

The work executes through the Day 22 Digital Twin runtime. Before execution, ASCOS validates the
exact ordered role/capability/action profile, provider, tool-free Twin, tenant, assignment,
objective digest, source chain, authority expiry, zero tool budget, and offline-provider boundary.
After execution, ASCOS rebuilds the provider request and deterministic output and reconciles both
digests with the terminal execution receipt.

Only fully reconciled, closed, typed output may enter the Day 28 store. The artifact is canonical,
tenant/execution scoped, write once, bounded, mode 0600, path contained, integrity checked, and
restart safe. Exact retries reopen the same receipt and artifact without a second provider effect.
Reads reject tampering, non-canonical data, unsafe permissions, symlinks, unknown directory entries,
identity drift, and malformed nested records.

## End-user evidence

Mandatory exact-head Chromium testing renders a founder-safe report showing all six plans, their
`NOT_EXECUTED` states, exact Architecture/Engineering/QA/Security digests, receipt digest, and
authority exclusions. The browser asserts restrictive headers, complete plan visibility, empty
console-error collection, and empty network-failure collection. The uploaded manifest binds the
exact commit, approved Day 27 base, every upstream artifact, work order, profile, authority,
assignment, provider request/output, receipt, plan states, and screenshot digest.

The fixture is generic verification data. It is not a pilot selection, infrastructure workspace,
preview deployment, or production target.

## Explicit exclusions

Day 28 does not run CI; create or edit infrastructure; access credentials; provision; migrate;
deploy; monitor; roll back; promote; release; target production; access or write a product
repository; execute commands; commit; merge; approve architecture, QA, or Security; accept risk;
perform Documentation or multi-agent orchestration; spend budget; bill; or select an official
pilot. Those actions require later locked modules and separate human authorization.
