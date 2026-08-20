# CEO and Product Manager Workforce Agents

Day 23 operationalizes exactly two leadership roles on the provider-neutral Digital Twin runtime
delivered in Day 22. It does not add an architect, engineering agent, product workspace, or
multi-agent orchestrator.

## Role contracts

The CEO Digital Twin maps exactly to `AgentRole.CEO`. Its immutable authority allows assigned-work
execution, evidence production, opportunity intake, and status reporting. From one bounded
`OpportunityIntake`, the provider returns a draft opportunity summary, goals, clarification
questions, completed work, next action, blockers, and human decisions required. It cannot produce a
product plan, approve opportunity priority, allocate budget, or select an official pilot.

The Product Manager Digital Twin maps to the repository's existing
`AgentRole.PROJECT_MANAGER`. Its immutable authority allows assigned-work execution, evidence
production, scope clarification, product-plan proposal, and status reporting. It requires the exact
persisted CEO brief and same opportunity digest, then returns draft goals, in/out scope, structured
questions, an ordered product plan, status, blockers, and human decisions required. The naming
mapping preserves the existing governed enum while implementing the founder-locked Product Manager
module.

Both profiles declare zero tools and a zero tool-call budget. The local deterministic
`LeadershipAgentProvider` receives only the typed Day 22 request and has no filesystem, network,
subprocess, repository, credential, approval, budget, deployment, or release adapter. A future
replaceable provider must satisfy the same closed request/result schema and exact authority checks.

## Durable evidence

`LeadershipWorkforceService` dispatches the assignment through `DigitalTwinRuntime`. After the
runtime writes its intent and terminal digest-only receipt, the service purely rebuilds the role
result, compares its output digest with the receipt, converts it into the closed typed artifact, and
persists it through `FileLeadershipArtifactStore`. This reconstruction allows an interrupted
artifact write to be completed after restart without repeating the provider effect.

Each artifact binds:

- tenant, opportunity, execution, assignment, Digital Twin, Business Role, and provider;
- opportunity and optional upstream CEO-artifact digests;
- exact delegated-authority, assignment, provider-request, provider-output, and receipt digests;
- validated role content and explicit status report; and
- fixed `DRAFT_AWAITING_HUMAN_REVIEW` and `NOT_SELECTED` pilot states.

The file adapter writes a canonical integrity envelope with mode 0600 under a closed
tenant/execution path. It is write once, bounded, exact-retry idempotent, and rejects path escape,
unsafe directories/files, symlinks, unknown entries, malformed schemas, and tampering.

## Verification

Unit and security tests cover both successful roles, action/capability/tenant/tool boundaries,
exact CEO handoff, malformed provider output, pilot-selection rejection, exact retry/restart, and
storage integrity. Mandatory real Chromium CI inspects the two founder-safe drafts and exact digest
handoff with restrictive response headers, no console errors, and no failed requests. The uploaded
`day23-founder-leadership-workforce` manifest binds the exact PR head to the approved Day 22 base,
both artifacts and receipts, and the screenshot digest.

## Explicit exclusions

Day 23 provides recommendations and draft status only. It does not approve product scope,
investment, budget, architecture, repository access, engineering tasks, code, merges, deployments,
billing, releases, or an official pilot product. Architecture proposals, technology selection,
ADRs, and technical risk identification remain Day 24. Agent dependency scheduling, parallel work,
handoff automation, conflict resolution, and escalation orchestration remain Day 30.
