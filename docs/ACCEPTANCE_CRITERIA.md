# Runtime Persistence Acceptance Criteria

# Day 30 acceptance

One bounded orchestration work order and one current tenant-bound authority must bind the exact
persisted Day 23–29 workforce chain in canonical order: CEO, Product Manager, Software Architect,
Backend Engineer, Frontend Engineer, AI Engineer, Data Engineer, QA Engineer, Security Engineer,
DevOps Engineer, and Documentation Engineer. Product Manager must bind CEO; Architecture must bind
Product Manager; every later artifact must retain the exact Architecture, Engineering, QA,
Security, and DevOps sources required by its module. Missing, extra, reordered, fabricated,
changed, cross-opportunity, or cross-tenant sources must fail before planning activity.

Authority must bind the exact work-order and source-set digests, ordered orchestration action
profile, empty tool allowlist, zero tool-call budget, no live-provider authorization, current time
window, assignment identity, and maximum parallel-work limit. The replaceable planning provider may
produce only one closed typed orchestration draft. Provider output cannot expand source context,
dispatch a handoff, execute an agent, approve a conflict, accept risk, or trigger an escalation.

One orchestration artifact must contain exactly eleven acyclic dependency nodes and nine ordered
waves. Wave 4 must contain Backend, Frontend, AI, and Data nodes under bounded four-way parallelism;
all other workforce waves remain dependency ordered, followed by one non-executed human-review
gate. Exactly eleven context packages must match their target nodes' exact source digests and must
exclude credentials, secrets, raw customer data, and local paths. Exactly seven handoffs must bind
known nodes and sources. Exactly three conflict routes must block affected downstream work, and
exactly three escalation records must name human owners and bounded decision options.

Every node and wave must remain `PLAN_ONLY_NOT_EXECUTED`; every handoff must remain
`DRAFT_HANDOFF_NOT_DISPATCHED`; every conflict must remain
`DRAFT_CONFLICT_POLICY_NOT_INVOKED`; every escalation must remain `PENDING_ONLY_IF_TRIGGERED`; and
the complete artifact must remain `DRAFT_ORCHESTRATION_PLAN_AWAITING_HUMAN_AUTHORIZATION` with
pilot state `NOT_SELECTED`. No workspace, repository, command, network, deployment, release, merge,
approval, risk acceptance, billing, budget, or product operation may be claimed.

Persistence must be canonical, integrity checked, mode 0600, tenant/execution scoped, write once,
bounded, path contained, restart safe, and exact-retry idempotent. Unknown entries or fields, unsafe
permissions, symlinks, non-canonical content, identity mismatch, source drift, graph cycles,
cross-source context, unknown handoff nodes, changed states, and tampering must be rejected. Raw
provider data, credentials, secrets, customer content, URLs, and local paths must not be persisted.

Mandatory exact-head CI must execute the Day 30 plan with generic fixtures and real Chromium.
Chromium must inspect the source chain, nine waves, four-way Engineering parallelism, context
exclusions, handoffs, conflicts, escalations, zero-tool boundary, restrictive headers, empty console
failures, and empty network failures. Founder evidence must bind the exact commit, approved Day 29
base, all source digests, work order, authority, provider output, artifact states, and screenshot
digest. Day 30 does not create the Day 31 product workspace or start Day 31 behavior.

# Day 29 acceptance

One enabled Digital Twin must align exactly to `AgentRole.DOCUMENTATION_ENGINEER`, provider
`deterministic-documentation-engineer-v1`, the ordered Documentation capability profile, and the
ordered delegated action profile. It must have zero tools, zero tool calls, no live-provider
authorization, one current tenant-bound authority, and one immutable Documentation work order
whose assignment ID and objective digest match the delegation. Profile, identity, source, or
authority drift must fail before provider activity.

The work order must consume the exact persisted Day 24 Software Architect artifact, exactly four
ordered Day 25 Engineering artifacts, exact Day 26 QA artifact, exact Day 27 Security artifact,
and exact Day 28 DevOps artifact. QA, Security, and DevOps must bind the same Architecture and
Engineering digests; DevOps must bind the exact QA and Security digests. Every source must share
tenant, opportunity, expected draft status, and `NOT_SELECTED` pilot state. Missing, extra,
reordered, fabricated, changed, or cross-tenant sources must fail closed.

One execution must produce exactly five typed records in order: technical, user, API, operations,
and release. Technical must bind Architecture and all Engineering sources; user must bind Frontend
and QA; API must bind Architecture, Backend, Frontend, and AI; operations must bind Security and
DevOps; release must bind all eight upstream digests. One customer handoff must cover exactly all
five record IDs. Every record must be `VALIDATED_AGAINST_EXACT_SOURCES`,
`DRAFT_SOURCE_VALIDATED_AWAITING_HUMAN_REVIEW`, and `NOT_PUBLISHED`; the artifact must remain
`DRAFT_DOCUMENTATION_OUTPUT_AWAITING_HUMAN_REVIEW`.

Only closed typed content whose rebuilt provider request/output digests reconcile with the terminal
receipt may be stored. Persistence must be canonical, integrity checked, mode 0600,
tenant/execution scoped, write once, bounded, path contained, restart safe, and exact-retry
idempotent. Unknown entries or fields, unsafe permissions, symlinks, non-canonical records,
malformed nested fields, source drift, changed states, identity mismatch, and tampering must be
rejected. Raw provider responses, exceptions, credentials, secrets, customer data, publication
receipts, URLs, and local paths must not be persisted.

Mandatory exact-head CI must execute the Documentation profile through the real Digital Twin
runtime using generic fixtures and real Chromium. Chromium must inspect all five records, customer
handoff, exact Day 24–28 bindings, zero-tool boundary, restrictive headers, empty console failures,
and empty network failures. Founder evidence must bind the exact commit, approved Day 28 base,
every upstream artifact, work order, profile, authority, assignment, provider request/output,
receipt, document states, and screenshot digest. Day 29 performs no filesystem, repository,
customer-channel, publication, product execution, deployment, release, approval, orchestration,
commit, merge, billing, budget, or official pilot-selection action.

# Day 28 acceptance

One enabled Digital Twin must align exactly to `AgentRole.DEVOPS_ENGINEER`, provider
`deterministic-devops-engineer-v1`, the ordered DevOps capability profile, and the ordered delegated
action profile. It must have zero tools, zero tool calls, no live-provider authorization, one
current tenant-bound authority, and one immutable DevOps work order whose assignment ID and
objective digest match the delegation. Wrong role, provider, capability, action or order, tenant,
Twin, assignment, objective, tool allowance, source, or elevated authority must fail before
provider activity.

The work order must consume the exact persisted Day 24 Software Architect artifact, exactly four
ordered persisted Day 25 Engineering artifacts—Backend, Frontend, AI, and Data—the exact persisted
Day 26 QA artifact, and the exact persisted Day 27 Security artifact. QA and Security must bind the
same architecture and Engineering digests. Every source must share tenant, opportunity, status,
and `NOT_SELECTED` pilot state. Missing, extra, reordered, fabricated, changed, cross-work-order,
or cross-tenant sources must fail closed.

One successful execution must produce exactly six typed plans: CI pipeline, isolated preview
environment, migration, deployment, monitoring, and rollback. CI and deployment must bind all four
Engineering digests plus the exact QA and Security digests. Migration must bind the Data Engineer
artifact and only its components. Rollback must bind the exact deployment and migration plan IDs.
Preview, deployment, monitoring, and rollback targets must be
`ISOLATED_NON_PRODUCTION_PREVIEW`; production targets must be impossible.

Every plan must remain `NOT_EXECUTED`; the complete artifact must remain
`DRAFT_DEVOPS_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`. Architecture, Engineering, QA, and Security
statuses remain unchanged. Day 28 may describe commands and infrastructure steps as reviewable
text but cannot access a workspace, filesystem, repository, process, network, provider,
infrastructure, credential, or secret; execute CI, provision resources, run migrations, deploy,
connect monitoring, roll back, promote, release, or target production.

Only closed typed content whose rebuilt provider request/output digests reconcile with the terminal
runtime receipt may be stored. Persistence must be canonical, integrity checked, mode 0600,
tenant/execution scoped, write once, bounded, path contained, restart safe, and exact-retry
idempotent. It must reject unknown entries or fields, unsafe permissions, symlinks, non-canonical
records, malformed nested fields, source drift, cross-source components, changed QA/Security
bindings, claimed execution, production targets, identity mismatch, and tampering. Raw provider
responses, exceptions, credentials, secrets, customer data, deployment URLs, and local paths must
not be persisted.

Mandatory exact-head CI must execute the DevOps profile through the real Digital Twin runtime using
generic fixtures and real Chromium. Chromium must inspect all six plans, exact
Architecture/Engineering/QA/Security bindings, receipt, zero-tool boundary, restrictive headers,
empty console failures, and empty network failures. Founder evidence must bind the exact commit,
approved Day 27 base, every upstream artifact, work order, profile, authority, assignment, provider
request/output, receipt, plan states, and screenshot digest without credentials or local paths. Day
28 performs no Documentation, multi-agent orchestration, product-workspace or repository access,
filesystem, command, network, infrastructure, credential, CI, migration, deployment, monitoring,
rollback, promotion, release, production, commit, merge, billing, budget, or pilot-selection action.

# Day 27 acceptance

One enabled Digital Twin must align exactly to `AgentRole.SECURITY_ENGINEER`, provider
`deterministic-security-engineer-v1`, the ordered Security capability profile, and the ordered
delegated-action profile. It must have zero tools, zero tool calls, no live-provider authorization,
one current tenant-bound authority, and one immutable Security work order whose assignment ID and
objective digest match the delegation. Wrong role, provider, capability, action or order, tenant,
Twin, assignment, objective, tool allowance, source, or elevated authority must fail before
provider activity.

The work order must consume the exact persisted Day 24 Software Architect artifact, exactly four
ordered persisted Day 25 Engineering artifacts—Backend, Frontend, AI, and Data—and the exact
persisted Day 26 QA artifact bound to those same sources. Every source must share tenant,
opportunity, opportunity digest, architecture identity/digest, expected draft status, and
`NOT_SELECTED` pilot state. Missing, extra, reordered, fabricated, changed, cross-work-order, or
cross-tenant sources must fail closed.

One successful execution must produce exactly six typed STRIDE threat records, four dependency-check
specifications, four secret-check specifications, three draft security findings, coverage
requirements, handoff notes, and a status report. Threats must identify asset, trust boundary,
scenario, properties, mitigations, residual risk, exact Engineering sources, and source-owned
components. Dependency and secret specifications must cover every Engineering role in order.
Findings must bind the exact QA artifact and relevant Engineering sources.

Threat validation and all check specifications must remain `NOT_EXECUTED`; findings must remain
`DRAFT_FINDING_AWAITING_AUTHORIZED_SECURITY_VALIDATION`; the complete artifact must remain
`DRAFT_SECURITY_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`. Architecture, Engineering, and QA statuses
must remain unchanged. Day 27 may identify source-evidenced risks but cannot access a product
workspace, inspect files or dependencies, execute a scanner, validate an observed vulnerability,
remediate a finding, approve security or quality, or accept risk.

Only closed typed content whose rebuilt provider request/output digests reconcile with the terminal
runtime receipt may be stored. Persistence must be canonical, integrity checked, mode 0600,
tenant/execution scoped, write once, bounded, path contained, restart safe, and exact-retry
idempotent. It must reject unknown entries or fields, unsafe permissions, symlinks, non-canonical
records, malformed nested fields, source drift, missing STRIDE coverage, cross-source components,
changed QA binding, claimed scans, elevated findings, identity mismatch, and tampering. Raw
provider responses, exceptions, credentials, secrets, customer data, and local paths must not be
persisted.

Mandatory exact-head CI must execute the Security profile through the real Digital Twin runtime
using generic fixtures and real Chromium. Chromium must inspect all six threats, all Engineering
role dependency and secret specifications, draft findings, exact architecture/Engineering/QA
bindings, receipt, zero-tool boundary, restrictive headers, empty console failures, and empty
network failures. Founder evidence must bind the exact commit, approved Day 26 base, all source
artifacts, work order, profile, authority, assignment, provider request/output, receipt, counts, and
screenshot digest without credentials or local paths. Day 27 performs no DevOps, Documentation,
multi-agent orchestration, product-workspace or repository access, filesystem, command, network,
credential, scan, remediation, approval, risk acceptance, commit, merge, deployment, release,
billing, budget, or official pilot-selection action.

# Day 26 acceptance

One enabled Digital Twin must align exactly to `AgentRole.QA_ENGINEER`, provider
`deterministic-qa-engineer-v1`, the ordered QA capability profile, and the ordered delegated-action
profile. It must have zero tools, zero tool calls, no live-provider authorization, one current
tenant-bound authority, and one immutable QA work order whose assignment ID and objective digest
match the delegation. Wrong role, provider, capability, action or order, tenant, Twin, assignment,
objective, tool allowance, source, or elevated authority must fail before provider activity.

The work order must consume the exact persisted Day 24 Software Architect artifact and exactly four
ordered persisted Day 25 Engineering artifacts: Backend, Frontend, AI, and Data Engineer. Every
source must share the tenant, opportunity, opportunity digest, architecture ID and digest, source
status, and `NOT_SELECTED` pilot state. Missing, extra, reordered, fabricated, changed, or
cross-work-order sources must fail closed. One successful execution must produce exactly four typed
test-plan items, four automated-test specifications, two integration-test specifications, two draft
defect reports, coverage requirements, handoff notes, and an explicit status report.

Automated and integration records are executable specifications, not claims of product execution.
Their state must remain `NOT_EXECUTED`; defects must remain
`DRAFT_DEFECT_AWAITING_AUTHORIZED_TEST_EXECUTION`; the complete artifact must remain
`DRAFT_QA_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`. Architecture and Engineering source statuses must
remain unchanged. Day 26 may identify specification gaps and integration risks from the approved
source chain, but it cannot write a test file, access a product workspace, execute product code,
approve quality, or verify an observed runtime defect.

Only closed typed content whose rebuilt provider request/output digests reconcile with the terminal
runtime receipt may be stored. Persistence must be canonical, integrity checked, mode 0600,
tenant/execution scoped, write once, bounded, path contained, restart safe, and exact-retry
idempotent. It must reject unknown entries or fields, unsafe permissions, symlinks, non-canonical
records, malformed nested fields, source drift, identity mismatch, claimed execution, elevated
states, and tampering. Raw provider responses, exceptions, credentials, secrets, customer data, and
local paths must not be persisted.

Mandatory exact-head CI must execute the QA profile through the real Digital Twin runtime using
generic fixtures and real Chromium. Chromium must inspect all four role plans, automated and
integration specifications, draft defects, exact architecture and Engineering source bindings,
receipt, zero-tool boundary, restrictive headers, empty console failures, and empty network
failures. Founder evidence must bind the exact commit, approved Day 25 base, source artifacts,
work order, profile, authority, assignment, provider request/output, receipt, output counts, and
screenshot digest without credentials or local paths. Day 26 performs no Security, DevOps,
Documentation, multi-agent orchestration, product-workspace or repository write, command, product
test execution, quality approval, commit, merge, deployment, release, billing, budget action, or
official pilot selection.

# Day 25 acceptance

One shared Engineering provider and service must support exactly `AgentRole.BACKEND_ENGINEER`,
`AgentRole.FRONTEND_ENGINEER`, `AgentRole.AI_ENGINEER`, and `AgentRole.DATA_ENGINEER`. Each enabled
Digital Twin must use its exact ordered capability and delegated-action profile, zero tools and tool
calls, no live-provider authorization, one current tenant-bound authority, and one immutable work
order whose assignment ID and objective digest match the delegation. Wrong role, provider,
capability, action or order, tenant, Twin, assignment, objective, tool allowance, source, or elevated
authority must fail before provider activity.

Every work order must bind the same tenant and opportunity, the exact digest of the persisted Day 24
Software Architect artifact, and only component IDs present in that artifact. The architecture must
remain `DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW` with `NOT_SELECTED` pilot state. One successful
role execution must produce closed typed implementation instructions, role-appropriate interface
contracts, exact acceptance checks, engineering self-validation checks, handoff notes, and a status
report. The output must preserve the work-order, architecture, role, capability, action, authority,
assignment, provider request/output, and execution-receipt bindings and remain
`DRAFT_ENGINEERING_OUTPUT_AWAITING_AUTHORIZED_WORKSPACE`.

Provider output and all nested Engineering fields are untrusted. Only a result whose rebuilt request
and output digests reconcile with the terminal runtime receipt may be stored. Persistence must be
canonical, mode 0600, tenant/execution scoped, write once, bounded, path contained, integrity
checked, restart safe, and exact-retry idempotent. It must reject unknown entries or fields, unsafe
permissions, symlinks, non-canonical records, malformed role-specific items, changed acceptance
checks, cross-role output, identity mismatch, and tampering. Raw provider values and exceptions,
credentials, secrets, customer data, and local paths must not be persisted.

Mandatory exact-head CI must execute all four roles through the real shared Digital Twin runtime
using generic fixtures and real Chromium. Chromium must inspect all role outputs, the exact Day 24
architecture binding, work-order and receipt digests, zero-tool authority, output status,
restrictive headers, empty console failures, and empty network failures. Founder evidence must bind
the exact commit, approved Day 24 base, source artifact, all work orders, role profiles, authorities,
assignments, provider requests/outputs, receipts, counts, and screenshot digest without credentials
or local paths. Day 25 performs no product-workspace or repository write, command, code application,
QA, Security, DevOps, Documentation, multi-agent orchestration, merge, deployment, release, billing,
budget action, architecture approval, or official pilot selection.

# Day 24 acceptance

One enabled Digital Twin must align exactly to `AgentRole.SOFTWARE_ARCHITECT`, the explicit Day 24
provider, the ordered Software Architect capability profile, and the ordered delegated-action
profile. It must have zero tools, zero tool calls, no live-provider authorization, one current
tenant-bound authority, and an objective digest matching its immutable assignment. Wrong role,
tenant, Twin, provider, capability, action or action order, objective, tool allowance, or elevated
authority must fail before provider activity.

The source must be the exact persisted Day 23 Product Manager plan for the same tenant, opportunity,
and opportunity digest. The architecture artifact must bind that source digest and contain a typed
domain boundary, principles, at least three components, integrations, data lifecycle, security and
quality considerations, at least two concrete technology recommendations, at least one proposed ADR,
at least one rated technical risk with mitigation and escalation, and an explicit status report. The
artifact must remain `DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW`; all technology recommendations and
ADRs must remain `PROPOSED`, ADRs must require human approval, and pilot state must remain
`NOT_SELECTED`.

Only closed typed content whose provider request/output and receipt digests reconcile may be stored.
Persistence must be canonical, integrity checked, mode 0600, tenant/execution scoped, write once,
bounded, path contained, restart safe, exact-retry idempotent, and reject unknown entries, unsafe
permissions, symlinks, malformed nested fields, non-canonical records, and tampering. Raw provider
responses, exceptions, credentials, secrets, customer data, and local paths must not be persisted.
Retry and a new service/provider instance must return the same artifact without another provider
effect.

Mandatory exact-head CI must execute the architect through the real Digital Twin runtime using
generic fixture data and real Chromium. The browser must inspect the proposal, components,
technology recommendations, proposed ADRs, technical risks, exact Product-Manager handoff, receipt,
draft status, authority exclusions, restrictive headers, console health, and network health.
Founder evidence must bind the exact commit, approved Day 23 base, source/artifact digests, authority,
assignment, provider request/output, receipt, counts, and screenshot digest without credentials or
local paths. Day 24 performs no architecture approval, engineering task creation, repository or
command access, coding, merge, deployment, release, billing, budget decision, orchestration, Day 25
engineering behavior, or official pilot selection.

# Day 23 acceptance

The CEO and Product Manager must be separate enabled Digital Twins aligned exactly to
`AgentRole.CEO` and `AgentRole.PROJECT_MANAGER`. Each must use the Day 22 runtime, the explicit
Day 23 provider, an exact ordered capability profile, an exact ordered delegated-action profile,
zero tools, zero tool calls, no live-provider authorization, one current tenant-bound authority,
and an objective digest that matches its immutable assignment. Wrong role, tenant, Twin, provider,
capability, action order, objective, handoff, tool allowance, or elevated authority must fail before
provider activity.

The CEO output must record a bounded opportunity summary, goals, structured clarification
questions, and status report. It must not contain product scope or plan items. The Product Manager
output must require the exact persisted CEO artifact and opportunity digest, then record goals,
in-scope and out-of-scope items, structured questions, an ordered product plan, and status report.
Both outputs must be closed typed schemas, remain `DRAFT_AWAITING_HUMAN_REVIEW`, retain
`NOT_SELECTED` pilot state, name human-decision blockers, and bind the exact opportunity,
assignment, authority, provider request/output, runtime receipt, and upstream artifact digests.

Only validated typed content may enter the leadership artifact store; raw provider responses and
exceptions must not. Records must be canonical, integrity checked, mode 0600, tenant/execution
scoped, write once, bounded, path contained, restart safe, exact-retry idempotent, and reject
unknown entries, symlinks, unsafe permissions, malformed fields, and tampering. Exact retry and a
new service/provider instance must return identical artifacts without repeating provider effects.

Mandatory exact-head CI must execute both roles through the real runtime on generic fixture data,
verify the exact CEO-to-Product-Manager handoff, and use real Chromium to inspect both drafts,
statuses, digest chain, authority exclusions, restrictive headers, console health, and network
health. Founder evidence must bind the exact commit, approved Day 22 base, both artifacts,
authorities, assignments, provider requests/outputs, receipts, and screenshot digest without
credentials or local paths. Day 23 performs no architecture/technology/ADR/risk work, engineering
task creation, repository or command access, coding, budget/investment decision, approval, merge,
deployment, billing, release, multi-agent orchestration, or official pilot selection.

# Day 22 acceptance

One enabled Digital Twin must align to exactly one existing `AgentRole`, one explicit provider, a
bounded capability set, and an approved tool allowlist. One immutable assignment and one expiring
delegation grant must match tenant, Twin, Business Role, assignment, objective digest, authority ID,
and authority digest exactly. The grant must allow assigned-work execution, name every permitted
tool/action, expire within 24 hours, set tool-call/output budgets, and reject approval, governance,
product-repository write, commit, merge, deployment, release, billing, and pilot-selection actions.
Expired, future, disabled, cross-tenant, stale, mismatched, capability-incompatible, or elevated
authority must fail before provider or tool activity.

Provider selection must be explicit and provider-neutral. The provider receives only the bounded
typed request and a mediated tool gateway; it receives no store, filesystem, command runner,
repository, network client, credentials, or host environment. Each tool call must be within the
assignment, Twin, authority, provider, and runtime-registry allowlists. Day 22 registries accept only
explicitly read-only tools. Tool inputs/outputs and provider results must use closed bounded
non-secret fields; budget exhaustion, an unsupported tool, a provider exception, or mismatched
result identity must produce a sanitized terminal failure receipt.

Persistence must record intent before provider activity and one immutable terminal receipt bound to
the exact Twin, assignment, authority, provider request, output, and ordered tool-call digests.
Records must be canonical, mode 0600, write once, path contained, tenant scoped, process serialized,
restart safe, exact-retry idempotent, closed to unknown entries, and reject unsafe permissions,
symlinks, malformed schemas, and tampering. Provider context, tool inputs/outputs, raw provider
responses, exceptions, credentials, and local paths must not be persisted. Live providers require
both explicit authority and operator enablement; an interrupted live intent cannot be resubmitted
without reconciliation.

Mandatory exact-head CI must execute the deterministic provider through the real runtime, invoke one
allowlisted read-only fixture tool, reopen the exact receipt after restart without a second provider
effect, and use Chromium to inspect a restrictive-header founder report. Evidence must contain the
exact commit, approved Day 21 base, authority/assignment/request/intent/output/receipt digests,
tool-call evidence, and screenshot digest without secrets or local paths. It must state that no
specialized Day 23–30 agent behavior and no official pilot product were selected. Day 22 grants no
product task, workspace, repository, command, network, approval, merge, deployment, release, billing,
or pilot-selection authority.

# Day 21 acceptance

Only the authenticated owner may view a request's Preview and Evidence Centre, follow its governed
preview link, or record a review. The service must reload the exact Day 20 progress projection and
its request-to-estimate/locked-roadmap authority chain server-side. One internal publication
boundary may record an already-produced preview only when its credential-free origin is explicitly
allowlisted and every evidence artifact binds the same full commit SHA. The customer web boundary
must not publish previews or evidence and must reject cross-customer, missing, stale, corrupt,
tampered, unsafe-origin, incomplete, or mismatched authority.

The package must include unique artifacts covering automated tests, real browser execution, browser
console, browser network, screenshot, and security results. It must bind customer, request, product,
progress ID/digest, roadmap digest, estimate digest, preview label/URL, full commit SHA, publication
time, and stable package identity. `ACCEPT` must be blocked unless every required evidence kind
passes. `REVISE` must require bounded customer comments. Both decisions must require the exact
rendered package digest, session CSRF, a fixed reviewed-evidence confirmation, and create one
immutable receipt bound to the exact package and progress digests.

Package and receipt persistence must be canonical, integrity checked, customer scoped, write once,
restart safe, exact-retry idempotent, path contained, closed to unknown entries, mode 0600, and
reject symlinks and tampering. Responses must escape customer content and retain no-store, CSP,
frame, sniffing, and referrer protections. Mandatory exact-head CI must run Chromium through
authenticated navigation, evidence inspection, opening the separate allowlisted preview, explicit
acceptance, logout/login, and recovery of the same receipt without console or request failures.
Founder evidence must include centre, opened-preview, and receipt screenshots plus a digested
manifest free of passwords, tokens, cookies, CSRF values, salts, and local paths.

Day 21 records a customer review only. It creates no preview/deployment, agent, executable task,
workspace, repository write, code, merge, billing, release, pilot selection, or Day 22 authority.

# Day 20 acceptance

Only the authenticated owner may view project progress for a customer request. The service must
reload the exact request-to-estimate authority chain server-side, require the Day 18 locked roadmap
and Day 19 draft estimate to match every identity, digest, and ordered requirement mapping, and fail
closed on missing, stale, cross-customer, corrupt, or mismatched authority. The route is GET-only;
neither browser nor customer input may assert progress, status, assignments, blockers, decisions,
authority digests, or execution state.

Every governed roadmap item must appear once as a milestone. Every locked requirement must appear
once, in roadmap order, as a planned task bound to its existing milestone. ASCOS must calculate the
aggregate through the existing Project Manager progress domain and report zero completed, zero in
progress, zero task-level blocked, zero percent, and no assigned operational agents. The dashboard
must visibly show open execution-authority, workforce, and product-workspace blockers plus the
locked-roadmap and draft-estimate decisions with exact authority digests. Repeated views must produce
the same content digest and must not create a progress persistence directory.

The web surface must escape customer content, retain no-store, CSP, framing, sniffing, and referrer
protections, and visibly state that it is a visibility-only projection. Mandatory exact-head CI must
run real Chromium through authenticated access, full governed-plan navigation, dashboard inspection,
logout, login, and reopening the same projection without console or network failures. Founder-safe
evidence must contain `project-progress-dashboard.png` and a digested manifest without passwords,
bearer tokens, cookies, CSRF values, salts, or local paths.

Day 20 creates no estimate approval, agent assignment, executable task, repository connection or
write, code, merge, deployment, billing, release, official pilot selection, or Day 21 authority.

# Day 19 acceptance

Estimate generation must require an authenticated customer, session CSRF, one exact owned Day 18
locked roadmap, and the roadmap-approval digest rendered at the checkpoint. The service must reload
and validate the complete request-to-roadmap-approval chain and the governed `LOCKED` projection
server-side. Missing, stale, cross-customer, corrupt, tampered, unlocked, invalid, or mismatched
authority must fail closed before persistence.

The deterministic profile must preserve exact roadmap-item IDs and order, map every locked
requirement exactly once, and produce per-item and total relative engineering-day ranges. Its
priority and category points, data-sensitivity uncertainty factor, effort band, confidence rule,
drivers, and assumptions must be stable, bounded, and visible. The artifact must bind every upstream
identity and digest, stay `DRAFT`, and expose no approval, price, quote, calendar date, schedule,
staffing, agent, repository, task, code, deployment, billing, release, or pilot-product authority.

Persistence must be customer scoped, canonical, integrity checked, mode 0600, write once, restart
safe, exact-retry idempotent, path contained, closed to unknown entries, and reject symlinks and
tampering. The web form must use a bounded closed schema, trusted session identity and CSRF, escape
customer text, and retain no-store, CSP, framing, sniffing, and referrer protections. Mandatory
exact-head Chromium CI must prove signup through estimate generation, complete mapping and
assumption display, logout/login, and reopening the same draft without console or request failures.
The founder artifact must contain `delivery-estimate-draft.png` and a content-digested safe manifest.
Day 19 performs no approval, quote, scheduling, assignment, repository, implementation, merge,
deployment, billing, release, pilot selection, or Day 20 action.

# Day 18 acceptance

Roadmap approval must require an authenticated customer, session CSRF, the complete rendered Day 17
roadmap, one fixed affirmative confirmation, and the exact rendered roadmap digest. The service must
reload and validate the complete request, requirements, requirements approval, PRD, PRD approval,
roadmap, and governed mappings server-side. Missing, stale, false-confirmation, cross-customer,
corrupt, tampered, invalid, or mismatched authority must fail closed before persistence.

The write-once receipt must bind customer, request, product, PRD version and identity, roadmap
identity, source-request digest, requirements digest, requirements-approval digest, PRD digest,
PRD-approval digest, roadmap digest, confirmation contract, and UTC approval time. Its governed
projection must make the roadmap and every item `LOCKED`, preserve exact ordering, stable item IDs,
requirement IDs, priorities, and exactly-once requirement coverage, and record the authenticated
customer and receipt time. The model must expose no estimate, date, schedule, staffing, agent,
repository, task, implementation, deployment, billing, release, or pilot-product authority.

Persistence must be customer scoped, canonical, integrity checked, mode 0600, write once, restart
safe, exact-retry idempotent, path contained, closed to unknown entries, and reject symlinks and
tampering. The web checkpoint must use a bounded closed form, escape customer text, redirect every
locked draft/generation route to the receipt, and retain no-store, CSP, framing, sniffing, and
referrer protections. Mandatory exact-head Chromium CI must prove signup through roadmap approval,
complete locked mappings, logout/login, and recovery of the same receipt with a safe screenshot and
digest manifest. Day 18 performs no estimate, schedule, agent, repository, task, coding, merge,
deployment, billing, release, pilot selection, or Day 19 action.

# Day 17 acceptance

Roadmap generation must require an authenticated customer, session CSRF, one exact owned and locked
Day 16 PRD, and the PRD-approval digest rendered at the checkpoint. The service must reload and
validate the complete request, requirements, requirements approval, PRD, PRD approval, and governed
locked document. Missing, stale, cross-customer, corrupt, tampered, invalid, or mismatched authority
must fail closed before persistence.

Derivation must reuse the existing Product Requirements roadmap and roadmap-item operations. The PRD
must be valid and `LOCKED`; every source requirement must be `LOCKED`; milestone ordering, stable item
IDs, ordered requirement mappings, and priorities must match the governed projection. Every locked
requirement must appear exactly once and no unknown requirement may appear. The artifact and every
item remain `DRAFT`, with no estimate, date, schedule, assignee, agent, repository, implementation,
deployment, billing, release, or pilot-product authority.

Persistence must be customer scoped, canonical, integrity checked, mode 0600, write once, restart
safe, exact-retry idempotent, path contained, closed to unknown entries, and reject symlinks and
tampering. The web form must use a closed bounded schema, escape all customer text, and preserve the
no-store, CSP, framing, sniffing, and referrer protections. Mandatory exact-head Chromium CI must
prove signup through roadmap generation, complete mapping display, logout/login, and same-draft
recovery with a safe screenshot and digest manifest. Day 17 performs no roadmap approval, estimate,
schedule, agent, repository, coding, merge, deployment, billing, release, or Day 18 action.

# Day 16 acceptance

PRD approval must require an authenticated customer, session CSRF, one exact owned Day 15 PRD, its
complete rendered scope, an affirmative fixed confirmation, and the exact rendered PRD digest. The
service must reload the product request, locked customer requirements, requirements approval, and
PRD server-side and reject missing, stale, cross-customer, corrupt, tampered, or mismatched authority
before persistence.

The write-once receipt must bind customer, request, PRD artifact, product, PRD identity, version,
source-request digest, requirements digest, requirements-approval digest, PRD digest, confirmation
contract, and UTC approval time. Projection through the existing governed lifecycle must produce a
`LOCKED` PRD with the customer as approver, the receipt time as lock time, every requirement locked,
complete review/approve/lock history, and no validation issues. No roadmap record or downstream
authority may be created.

Persistence must be customer scoped, canonical, integrity checked, mode 0600, write once, restart
safe, exact-retry idempotent, path contained, closed to unknown entries, and rejecting of symlinks and
tampering. The web form must use a closed bounded schema, escape all customer text, and retain the
portal's no-store, CSP, framing, sniffing, and referrer protections. Mandatory exact-head Chromium CI
must prove signup through locked-PRD receipt plus logout/login recovery, with a safe screenshot and
digest manifest. Day 16 performs no roadmap, estimate, pilot selection, agent, repository, coding,
merge, deployment, billing, or release action.

# Day 15 acceptance

PRD generation must require an authenticated customer, session CSRF, one exact owned Day 14 approval
receipt, and the approval digest rendered at the generation checkpoint. The service must reload the
approved source request and requirements revision, compare every source/digest binding, and reject
missing, stale, cross-customer, corrupt, tampered, or mismatched authority before persistence.

The deterministic profile must map every approved scope field into a canonical PRD v0.1. Stable
requirements must cover the user journey and desired outcomes, each must-have feature, ordered
platforms, and declared data sensitivity; each requirement must retain a human-readable source
reference. Success metrics, exclusions, and delivery priority must remain visible. The generated
artifact must pass the existing Product Requirements validator, stay `DRAFT`, have no approver or
future roadmap, and expose no downstream action.

Persistence must be customer scoped, canonical, integrity checked, write-once, restart safe,
path-contained, mode 0600, exact-retry idempotent, and rejecting of unknown files and symlinks. The
web boundary must use a closed bounded form, escape all customer text, and retain the existing
no-store, CSP, framing, sniffing, and referrer protections. Mandatory exact-head Chromium CI must
prove signup through PRD review plus logout/login and existing-draft recovery, with a safe screenshot
and digest manifest. Day 15 performs no PRD approval, planning, agent, repository, coding, merge,
deployment, billing, or release action.

# Day 14 acceptance

Only the authenticated owner of the immutable source request may open the approval checkpoint,
approve, or view its receipt. Approval must reload current server-side request and draft authority,
require an explicit confirmation, and match both the exact positive revision and complete 64-digit
draft digest shown to the customer. Missing drafts, stale forms, false/missing confirmation,
cross-customer access, source mismatch, and malformed authority must fail closed.

The receipt must bind a bounded derived approval ID, customer/request/draft identities, revision,
source-request digest, requirements digest, fixed confirmation-contract version, and timezone-aware
server time. It must be canonical, integrity-digested, path-contained, write-once, mode 0600,
restart-safe, exact-retry idempotent, and protected against unknown fields/files, mutation, symlinks,
and conflicting second approval. Once present, it must durably block every later draft mutation and
edit route without rewriting the approved draft.

The web checkpoint must use trusted session identity and session CSRF, exact bounded URL-encoded
fields, a required confirmation checkbox, restrictive security headers, escaped customer content,
and generic failure pages that do not echo rejected authority. The receipt page must say that the
baseline is approved while implementation has not started.

Mandatory exact-head CI must run real Chromium through signup, intake, refinement, explicit
confirmation, receipt display, attempted edit redirect, logout, returning login, and reopening the
approved baseline without console/request failures. The founder artifact must contain
`requirements-approved.png` and a content-digested manifest without passwords, bearer tokens,
cookies, CSRF values, salts, or local paths. Day 14 grants no PRD, planning, agent, repository,
coding, merge, deployment, billing, or release authority.

# Day 13 acceptance

Only the authenticated customer that owns the immutable source request may open, save, list, or
review its guided requirements. Every revision must bind the exact customer ID, request ID, bounded
derived draft ID, positive contiguous revision, source-request digest, primary user journey, desired
outcomes, must-have features, measurable success metrics, optional non-goals, canonical platform
order, data-sensitivity declaration, delivery-priority declaration, and timezone-aware server time.

Draft history must be append-only, write-once, canonical, integrity-digested, path-contained, mode
0600, restart-safe, and limited to 1,000 revisions. Exact retries must reuse the existing latest
revision without another write. Changed submissions must provide the exact latest revision; stale
writers, gaps, unknown files, duplicate/unknown platforms, traversal, symlinks, cross-customer
access, source mismatch, mutation, and malformed authority must fail closed.

The web form must require trusted session identity and CSRF authority, exact URL-encoded content,
bounded bytes and fields, closed field names, single values except bounded platform checkboxes,
bounded normalized lines, and enumerated selections. Customer content must be escaped and invalid
submissions must not echo it. All pages must be non-cacheable and carry CSP, framing, sniffing, and
referrer protections. The review page must state that the record is only a draft and conveys no
approval or implementation authority.

Mandatory exact-head CI must run a real Chromium journey through signup, product-request creation,
guided clarification, immutable save, review, logout, new login, and reopening the same draft without
console or request failures. The founder artifact must contain `requirements-review.png` and a
content-digested manifest with no password, bearer token, cookie, CSRF value, salt, or local path.
Day 13 does not claim requirements approval/locking, PRD generation, planning, agents, coding,
repository connection, merge, deployment, billing, or release.

# Day 12 acceptance

Registration must canonicalize and validate an ASCII email, enforce the bounded strong-password
policy, generate a collision-resistant customer identity, use a unique 128-bit salt, and persist only
the scrypt credential digest. Login must compare derived digests in constant time and return one
generic credential failure for unknown accounts and wrong passwords. Raw passwords and bearer
session tokens must never be persisted, logged, rendered, or included in evidence.

Every issued session must persist only its SHA-256 token digest plus customer identity, independent
CSRF authority, issued time, and no more than a twelve-hour expiry. Invalid, missing, duplicate-cookie,
expired, revoked, malformed, tampered, noncanonical, symlinked, or path-escaping authority must fail
closed. Logout must require the matching session CSRF value, durably revoke the session, clear the
cookie, and remain externally idempotent. Restarted storage must preserve valid sessions and revoked
sessions exactly.

Signup/login forms must use signed double-submit pre-authentication CSRF. Session cookies must be
HttpOnly, SameSite=Strict, path-scoped, bounded to session lifetime, and Secure except in the explicit
loopback browser fixture. Only the authenticated server-side middleware may populate `REMOTE_USER`
and `ascos.csrf_token` for the Day 11 portal. All authentication responses must be no-store and carry
CSP, framing, sniffing, and referrer protections.

Mandatory exact-head CI must run a fresh real Chromium journey through unauthenticated redirect,
signup, product-request submission, sign-out, sign-in, reload/session restoration, and recovery of
the same customer-scoped request with no console or request failures. The founder artifact must
contain login and returning-workspace screenshots plus a safe manifest; it must contain no password,
bearer token, CSRF value, salt, cookie, header, or local path. Day 12 does not claim recovery, MFA,
organizations/roles, billing, AI refinement, agents, coding, merge, deployment, or release.

# Day 11 acceptance

The customer portal must require a trusted upstream customer identity and CSRF token before it accepts
a product request. The request body, content type, form fields, identifiers, text, feature count,
constraint count, and individual values must be bounded. Customer text must be escaped on every
render, responses must be non-cacheable and carry CSP, frame, content-type, and referrer protections,
and invalid submissions must fail closed without echoing customer content.

One successful submission must persist a canonical, integrity-digested, write-once request bound to
the customer and request IDs, desired product outcome, target users, ordered required features,
optional constraints, terminal submission stage, and timezone-aware submission time. Exact retries
must reuse the original record; changed retries, traversal, cross-customer reads, symlink escape,
corruption, and overwrite must fail. Restarted storage must reproduce the request exactly.

Mandatory exact-head CI must run a real Chromium journey from an empty customer dashboard through the
product form to the persisted confirmation/detail page. The founder artifact must contain a safe
screenshot and manifest with no credentials, session identifiers, CSRF values, or customer secrets.
Day 11 does not claim customer account/login implementation, AI refinement, agent dispatch,
repository connection, coding, merge, deployment, billing, or release.

# Day 10 acceptance

PWA verification must reload one immutable plan and prove exact agreement with the
`AUTOMATED_VERIFIED` runtime run, persisted runtime configuration revision/digest/full commit SHA,
acceptance profile identity/digest, current provider/origin policy, canonical start/manifest/service
worker paths, shell marker, and every locked PWA claim before the managed environment starts.

A passing fresh Chromium profile must fetch an exact same-origin manifest without redirects, require
non-empty name/short name, standalone-capable display, exact start/scope paths, and valid bounded PNG
responses declaring both 192x192 and 512x512 sizes. The exact service worker must reach `activated`,
control the page after reload, pass Chromium installability checks, install its exact manifest
identity, launch an authorized target with standalone user display mode, survive a
normal refresh, and serve the expected controlled shell after network access is disabled. Console or
page errors, origin escapes, mismatches, missing screenshot, incomplete claims, shutdown uncertainty,
or artifact-integrity failure must fail closed.

The aggregate submission plan must be write-once, restart-safe, corruption-detecting, and bind exactly
Authentication, Voice, and PWA—in that order—to their plan/result digests and complete locked journey
sets. Submission must accept only successful exact-run/configuration/profile/commit results, verify
every content-addressed artifact and evidence link, reject duplicates or omissions, and persist an
immutable receipt. Exact retry must not repeat runtime mutation. Successful submission advances only
from `AUTOMATED_VERIFIED` to `RUNTIME_VERIFIED`; it must not request or record human approval.

Mandatory exact-head CI must run the real PWA fixture, exact-SHA checkout, migration, service startup,
readiness, Chromium verification, offline reload, reverse shutdown, workspace cleanup, result restart
readback, and upload the founder-safe screenshot/manifest. This proves deterministic installability
prerequisites and browser behavior, not OS installation UI, production-product operation, human UX,
merge, deployment, or release.

# Day 9 acceptance

Voice verification must reload one immutable plan and prove exact agreement with the browser plan,
runtime configuration revision/digest/full commit SHA, acceptance profile identity/digest, provider,
all eight locked Voice journeys, named step IDs, exact claims, fixture authority, canonical media
paths, and bounded response before the underlying browser runs.

Input and output media must be content-addressed WAV artifacts. The exact product endpoints must
return HTTP 200 audio from the approved origin without redirects or ambient proxies, and delivered
bytes must equal the locked fixture bytes. Verification must reject malformed, compressed, wrong-rate,
wrong-channel, wrong-duration, silent, near-silent, or digest-mismatched media. Passing audio evidence
must record bounded PCM dimensions, peak, RMS, and non-silent ratio without storing credentials.

Audible-playback and repeat-turn claims require a provider-owned Chromium media assertion proving
decoded positive duration, completed current time, unmuted state, and volume of at least 50 percent.
Named browser assertions must prove exact transcript, bounded response, persisted turn, generated TTS,
avatar `speaking → idle`, and a second same-session turn. Missing, corrupt, mismatched, failed, or
self-reported-only playback evidence fails closed.

Mandatory exact-head CI must execute all eight journeys against a migrated SQLite-backed fixture,
verify shutdown, workspace cleanup, immutable result restart readback, and upload a founder pack with
eight screenshots, both verified WAVs, and a secret-safe manifest. Deterministic adapters do not
constitute production STT/LLM/TTS or human physical-speaker acceptance. Day 9 performs no PWA,
aggregate completion, human approval, merge, deployment, or release action.

# Day 8 acceptance

Authentication verification must load one immutable plan and prove exact agreement with the browser
plan, runtime configuration revision/digest/full commit SHA, acceptance profile identity/digest,
provider, all six locked Authentication journeys, required named step IDs, exact claims, and required
persistence/security evidence kinds before the underlying browser provider runs.

Passing persistence or security evidence may be derived only from a content-addressed browser summary
whose digest, plan, journey, outcome, and named passed assertions are verified. Missing, corrupt,
mismatched, or failed source evidence must generate durable failure evidence. Plans are write-once,
restart-safe, path-contained, identity-checked, and corruption-detecting.

Mandatory exact-head Chromium CI must exercise the complete customer flow against a migrated SQLite
database and prove persistence, duplicate rejection, login, logout revocation, session restoration,
password replacement, old-password and reused-reset rejection, account-enumeration-safe recovery,
invalid-token handling, transaction rollback, throttling, and hardened password/session/reset storage.
It must also prove shutdown, cleanup, result restart readback, and absence of raw test credentials and
tokens from persisted artifacts. The founder artifact must contain a safe claim manifest and six
masked screenshots. Day 8 performs no production-product, voice, PWA, human-acceptance, merge,
deployment, or release action.

# Day 7 acceptance

Browser execution must load one immutable plan and prove exact agreement with the
`AUTOMATED_VERIFIED` runtime-acceptance run, persisted configuration revision/digest/full commit SHA,
locked profile identity/digest, and every journey belonging to each selected capability before resolving a browser secret
or starting the environment. Current policy must approve the provider, origins, and opaque browser
secret references.

Journeys must use bounded declarative accessible locators/actions, canonical URL paths, and exact
input references, with no arbitrary JavaScript, CSS, XPath, shell, query/fragment targets, or
traversal. Secret-bearing inputs require invocation-only references. Exact retries must return the
immutable terminal result without a second environment, secret lookup, or browser effect.

The browser runs only after exact-SHA migration, startup, and readiness and before reverse shutdown
and cleanup. Requests must remain on approved origins. Evidence excludes headers, cookies, browser
storage, bodies, credentials, and query strings; console values are bounded/redacted; secret input
locators are masked in the final screenshot. Console/page errors, failed/HTTP-error requests, blocked
origins, failed steps, or missing screenshots must fail the journey.

Browser, console, network, screenshot, migration, startup, and readiness artifacts must be
content-addressed and integrity-checked. Terminal results survive restart, reject mutation/corruption,
retain failures, and become `RECONCILIATION_REQUIRED` when shutdown or cleanup is unproven. Mandatory
exact-head Chromium CI must prove real login, HTTP-only session creation, reload/session restoration,
evidence capture, shutdown, cleanup, and restart readback. Day 7 performs no production-product,
human-acceptance, merge, deployment, or release action.

# Day 6 acceptance

Managed Product Environment execution must load one exact immutable runtime-configuration revision
by project, configuration ID, revision, and canonical digest and recheck current operator repository,
executable, origin, environment-name, and opaque-secret-reference policy before any side effect.
Caller-supplied or stale configuration content is not execution authority.

The local provider must create a run-specific disposable clone, disable interactive Git and ambient
Git configuration, check out the configured full SHA detached, reject any observed mismatch, remove
all remotes before product commands run, contain every working directory and symlink, and never
expose repository-write, push, merge, deployment, or release behavior.

Secrets must be resolved only through an injected provider after authorization, injected only into
the minimal allow-listed process environment, redacted before bounded output hashing, and absent from
results, observations, errors, workspace identity, and persisted evidence. Migration/start/stop
commands must remain shell-free argument arrays. Readiness must use only configured, operator-approved
origins, inherit no proxy, follow no redirect, and remain bounded by declared timeouts.

Migrations and services must execute in declaration order; shutdown must execute in reverse order
after success or failure. A complete run must prove exact source, migrations, process startup,
readiness, declared stop, and workspace cleanup. Unproven process termination or cleanup must retain
the workspace and return `RECONCILIATION_REQUIRED`; other verified failures return `FAILED` without
claiming runtime acceptance. Day 6 must perform no browser, customer-journey, merge, deployment, or
release action.

# Day 5 acceptance

Managed Product Runtime Configuration must bind one registered product to its repository, expected
branch, lowercase full Git commit SHA, bounded argument-array service commands, service and readiness
URLs, explicitly public environment values, opaque secret references, and an exact acceptance-profile
identity/version/digest. Its canonical SHA-256 digest must preserve command order and change whenever
any execution-relevant field changes.

Configurations must be immutable and revisioned. Updates require an exact expected revision, retain
all earlier revisions, reject stale writers, persist atomically, survive restart, and reject malformed,
non-contiguous, unsupported, or digest-invalid history. Runtime-acceptance binding must require the
same product, exact commit, and verified acceptance-profile digest and must retain the configuration
ID, revision, and digest.

Validation must reject shell mediation and control syntax, unsafe relative paths, repository or
endpoint credentials, non-loopback plain HTTP, readiness endpoints on unrelated origins, raw secrets,
secret-like public keys, and public/secret key conflicts. Registration must match the managed-product
repository and operator-owned repository-host, executable, origin, environment-name, and exact or
prefix-based secret-reference policies.
Creating, validating, digesting, persisting, loading, revising, or binding a configuration must
perform no Git, subprocess, network,
secret-resolution, service-startup, browser, merge, deployment, or release action.

# Milestone 15 acceptance

No locked customer-facing capability may advance from automated verification to acceptance without
exact-commit runtime evidence for every required customer journey. Code, automated tests, migrations,
service startup/readiness, browser execution, console/network capture, and screenshot artifacts are
mandatory. Capability-specific contracts must additionally prove persistence, security, PWA, or the
deterministic audio/STT/LLM/TTS/playback/avatar chain as applicable.

Authentication completeness includes registration, login, logout, session restoration, password
recovery, and partial-failure/error paths. Voice completeness includes a repeated audible browser
turn. Failed evidence must remain durable and force a new acceptance run. Human UX gates require a
named, current-commit decision bound to passing human-UX evidence and the complete current evidence
digest. Locked contracts, journey definitions, evidence/result histories, and run identity cannot be
rewritten after planning. Release review, approval, and publication must reject missing, stale,
incomplete, or pre-runtime acceptance runs.
# Day 4 PostgreSQL validation acceptance

Day 4 is accepted only when the exact candidate commit passes the always-scheduled CI
job against a real PostgreSQL 16 service. The integration evidence must cover fresh,
repeat, and concurrent migrations; rejection or rollback of unsafe schema changes;
exclusive multi-connection outbox claims; expired-claim fencing and reclaim; optimistic
single-winner writes; and restart readback from a fresh repository connection. Fake
connection tests or a skipped database suite do not satisfy this acceptance gate.

This acceptance applies only to the bounded experimental PostgreSQL adapter. It does
not certify a production persistence provider. Full `PersistenceProvider` and durable
outbox contract conformance, runtime composition, deployment security, backup/restore,
point-in-time recovery, failover, capacity, and soak validation remain incomplete and
must not be represented as accepted or production-ready.
# Milestone 12.4 acceptance

Managed provider execution requires typed capabilities, secret-safe injected
configuration, durable submission intent, deterministic idempotency, exact
uncertain-state reconciliation, monotonic progress, bounded context/results,
validated text patches, independent Git inspection, enforced usage limits, and
explicit live authorization. Existing approval and product-write controls remain
mandatory. The product pilot runs against temporary fixtures by default.

Live correctness must survive process restart through a durable exact-identity
response receipt; absent provider retrieval or receipt, uncertainty must require
operator action. Patch intent precedes staged writes, every replacement is
checkpointed, and only a verified manifest of independently observed Git state
may be accepted. Component-aware no-link path handling, request-specific output
limits, exact acceptance predecessors, and evidence-confirmed cancellation are
required.

# Milestone 12.3B acceptance

Managed execution requires completed 12.3A materialisation and separate
version-specific human execution approval. Runtime mappings are deterministic
and idempotent; workspaces are isolated; coding results and changes are
policy-validated; commands are bounded argument arrays; required gates and
review evidence are durable; completion requires separate human review; and
commit, push, and draft-PR effects remain explicit, restart-safe, protected from
duplicates, and incapable of automatic merge, deployment, or release.

Every external effect must persist exact intent before invocation and exact
verified completion afterward. Crash recovery must reuse matching workspace,
branch, commit, remote ref, PR, and runtime-mapping state without duplication;
divergence must require operator reconciliation. Evidence may use only durable
accepted successful coding results, must canonically bind all plan, workspace,
branch, base, result, path, and gate identities, and must be digest-verified at
every sensitive transition. Gate profiles must enforce executable/environment
allow-lists, no shell mediation, bounded time/output, redaction, deterministic
failure policy, and one non-success-preserving result per required gate.

# Milestone 12.3A acceptance

Planning must use registered identity and an explicit current knowledge snapshot,
produce strictly validated dependency-safe proposals, require separate
actor-attributed approval, persist only bounded structured state, materialise
only through `AIProjectManager`, and create no product repository or runtime
execution side effect.

Materialisation must durably prepare an operation before manager mutation,
reconcile exact manager content after interruption, prevent duplicate records,
record reconciliation-required conflicts, and consider a proposal fully
materialised only when both manager state and the completed materialisation
lifecycle are durable.

# Milestone 12.2 acceptance

Knowledge indexing must be deterministic, text-only, ignore common generated
and version-control paths, use Python AST safely, preserve stable query and
serialization ordering, validate registry identity, persist only under
ASCOS-controlled storage, and never modify a product repository.

# Milestone 12.1 acceptance

Manager state must reference a registered project, permit only validated and
atomic task/milestone transitions, plan executable tasks deterministically,
calculate stable integer progress, round-trip all supported records through
schema-versioned atomic JSON under ASCOS-controlled storage, expose Python and
CLI operations, and never write to a managed product repository.

Milestone 11.3E requires atomic intent/event creation, deterministic exclusive
claims, hashed claim tokens, stale-fencing rejection, at-least-once dispatch,
idempotent local result application, bounded retry, dead-letter/operator audit,
uncertain-outcome reconciliation, restart safety, provider-neutral persistence,
and no automatic approval, merge, or deployment.

Milestone 11.3D requires argument-array command execution without a shell,
workspace containment, protected Git branches, typed offline GitHub behavior,
deterministic coding-provider selection, explicit side-effect records,
reconciliation after interruption, persisted task/review state, credential
exclusion, and approval that neither completes nor merges automatically.

Milestone 11.3C requires deterministic migrations, atomic checkpoint/event
commits, stale-writer rejection, durable event ordering, hashed lease
identities with UTC expiry and fencing, restart without historical
re-emission, legacy-provider compatibility, and executable examples.

A persistence implementation is acceptable when:

- canonical serialization is deterministic and rejects unsupported values;
- checkpoints are immutable, versioned, and SHA-256 verified;
- writes are atomic and partial temporary files are never listed;
- invalid references or event sequences reject the complete restore;
- all runtime identifiers, lifecycle states, capacity, history, and events
  survive restart;
- historical events are not re-emitted;
- new event sequences continue after restart;
- persistence-disabled construction remains compatible;
- failures are surfaced and never falsely reported as durable;
- approval and assignment completion remain explicit.
# Milestone 11.3F acceptance

The worker runtime must start only explicitly, use unique instance identities,
heartbeat through durable registries, stop gracefully, and preserve outbox fencing.
Provider routing must reject disabled, open, and saturated providers deterministically.
PostgreSQL claiming must use atomic `FOR UPDATE SKIP LOCKED`; real integration results
may only be claimed from the always-scheduled PostgreSQL CI job or an explicitly
configured real test database. A missing test database must produce a reported skip,
not a successful PostgreSQL claim.

# Milestone 12.0 acceptance

Managed projects require stable validated identities, normalized repository
uniqueness, deterministic lookup and lifecycle filtering, registration events,
composition-root access, and restart-safe atomic file persistence. The first
managed product registration must reference Spoken English AI portably and
must not modify its repository.
