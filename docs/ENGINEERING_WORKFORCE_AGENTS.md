# Engineering Workforce Agents

Day 25 operationalizes Backend, Frontend, AI, and Data Engineer Digital Twins through one shared
Engineering service on the provider-neutral Day 22 runtime. This is a governed Engineering
execution boundary. It is not the Day 31 product-workspace boundary or the Day 32 coding/review loop.

## Shared runtime and exact role profiles

`EngineeringAgentProvider` supports exactly four existing Business Roles:

- `AgentRole.BACKEND_ENGINEER` owns bounded service, domain-workflow, and backend-contract output;
- `AgentRole.FRONTEND_ENGINEER` owns bounded interface, interaction, accessibility, and responsive output;
- `AgentRole.AI_ENGINEER` owns bounded provider-neutral AI, evaluation, and reliability output; and
- `AgentRole.DATA_ENGINEER` owns bounded data-model, schema-evolution, and integrity output.

Each role has a different exact ordered capability tuple and one role-specific implementation
action. Every action tuple also contains assigned-work execution, execution evidence, and status
reporting. The service requires tuple equality rather than subset matching so missing, extra, or
reordered authority fails before provider activity. Each role uses one enabled Twin, one immutable
work order, one current tenant-bound delegation, one Digital Twin assignment, one execution intent,
and one terminal receipt.

All four profiles have zero tools, a zero tool-call budget, and no live-provider authorization. The
provider cannot access a filesystem, environment, process, repository, network, credential,
persistence adapter, product workspace, deployment system, or release system.

## Exact Day 24 source and work order

An `EngineeringWorkOrder` binds its tenant, opportunity, assignment, Business Role, bounded title
and objective, acceptance checks, constraints, target architecture components, issue time, and the
exact Day 24 architecture digest. `EngineeringWorkforceService` reloads the architecture from the
canonical Day 24 store and requires object equality. A changed, fabricated, cross-tenant,
cross-opportunity, missing, corrupt, unpersisted, differently digested, automatically approved, or
pilot-selecting source fails before provider activity. Target component IDs must exist in that exact
artifact.

The architecture remains `DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW`. Day 25 founder approval is
approval of this bounded runtime module, not automatic acceptance of architecture recommendations
or ADRs and not permission to write a product repository.

## Closed role-specific output

One successful assignment produces an `EngineeringWorkArtifact` containing:

- exact work-order, architecture, tenant, opportunity, role, capability, action, authority,
  assignment, provider-request, provider-output, and receipt bindings;
- role-specific typed implementation instructions targeted only at assigned architecture components;
- a role-specific typed interface contract with inputs, outputs, and fail-closed behavior;
- the unchanged acceptance checks from the work order;
- bounded Engineering self-validation checks and handoff notes; and
- a status report naming completed output, next authorization, blockers, and escalations.

Backend artifacts accept only service-logic items and service-interface contracts. Frontend
artifacts accept only user-experience items and user-interface contracts. AI artifacts accept only
AI-system items and AI-interface contracts. Data artifacts accept only data-model items and
data-interface contracts. Provider output is reconstructed after runtime execution, reconciled with
the terminal request/output digests, and validated through the complete closed nested schema before
storage. Unknown fields, duplicate keys, changed acceptance checks, wrong discipline, wrong change
kind, wrong interface kind, wrong target component, elevated status, or selected pilot fail closed.

## Persistence, retry, and evidence

`FileEngineeringArtifactStore` writes one canonical mode-0600 artifact into a closed
tenant/execution directory. It is path contained, bounded, integrity checked, write once, and rejects
unsafe permissions, symlinks, unknown entries, non-canonical records, schema or identity mismatch,
and tampering. Raw provider payloads, exceptions, credentials, secrets, customer data, and local
paths are not persisted.

Exact retry returns the existing Day 22 receipt and the same Engineering artifact without another
provider effect. A restarted service/provider reconstructs and validates the same output and also
performs no duplicate effect. Mandatory exact-head CI runs unit, regression, compilation, lint,
typing, examples, PostgreSQL, and real Chromium coverage. Chromium inspects all four role outputs,
the exact persisted architecture handoff, work-order and receipt digests, restrictive headers,
empty console/network failure collections, and the zero-tool authority boundary. Founder evidence
binds the exact Day 25 commit to the approved Day 24 base.

## Explicit exclusions

Every output remains `DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`. Day 25 does not create
or access a product workspace, write a repository, create a patch, run a command or migration, call
a live AI provider, commit, merge, deploy, release, bill, set a budget, accept architecture, select a
pilot, or perform QA, Security, DevOps, Documentation, or multi-agent-orchestration behavior. Those
are distinct later modules in the founder-locked 37-module plan.
