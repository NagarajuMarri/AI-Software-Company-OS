# Runtime Roadmap

# Day 18 — Customer Roadmap Approval and Immutable Lock

Let the authenticated owner review every milestone and requirement mapping in one exact Day 17
roadmap draft, affirm one fixed confirmation, and create one canonical write-once approval receipt.
Reload and validate the complete customer-owned request, requirements, requirements approval, PRD,
PRD approval, and roadmap chain server-side. Bind the receipt to all identities, versions, and
digests, including the exact rendered roadmap digest; reject missing, stale, cross-customer,
corrupt, tampered, or mismatched authority.

Project the approved artifact into a deterministic immutable roadmap whose roadmap and every item
are `LOCKED`. Preserve exact milestone order, stable roadmap-item IDs, ordered requirement mappings,
priorities, and exactly-once requirement coverage. Preserve exact-retry idempotency, restart-safe
reads, canonical integrity records, mode-0600 exclusive writes, customer isolation, path
containment, closed schemas, symlink/tamper detection, session CSRF, escaping, and restrictive
browser headers. Mandatory Chromium CI proves explicit approval, locked receipt rendering,
logout/login, and recovery of the same locked roadmap.

Day 18 creates immutable planning scope only. It does not estimate or schedule work, assign people
or agents, select a pilot product, connect a repository, create implementation tasks, generate or
execute code, merge, deploy, bill, or release. Day 19 remains separate and requires founder
approval.

# Day 17 — Traceable Customer Roadmap Draft

Let the authenticated owner generate and reopen one deterministic roadmap v0.1 only from the exact
Day 16 locked customer PRD. Reload the complete customer authority chain server-side, require the
rendered PRD-approval digest, and bind the write-once roadmap to every request, requirements,
approval, PRD, and PRD-approval identity and digest.

Reuse the existing Product Requirements roadmap and roadmap-item derivation. Require a valid
`LOCKED` PRD, retain deterministic milestone ordering and stable roadmap item IDs, preserve ordered
requirement priorities, and prove every locked requirement maps exactly once with no additions.
Persist a canonical integrity record with exact-retry idempotency, restart-safe validation,
mode-0600 exclusive creation, customer isolation, path containment, a closed schema, unknown-entry
and symlink rejection, session CSRF, escaped output, and restrictive browser headers. Mandatory
Chromium CI proves generation, complete traceability, logout/login, and same-draft recovery.

The roadmap and every item remain `DRAFT`. Day 17 does not approve the roadmap, estimate or schedule
work, assign people or agents, select a pilot product, connect a repository, create implementation
tasks, generate or execute code, merge, deploy, bill, or release. Day 18 remains separate.

# Day 16 — Customer PRD Approval and Immutable Lock

Let the authenticated owner review the complete exact Day 15 PRD, affirm one fixed confirmation,
and create one canonical write-once approval receipt. Reload the customer-owned request,
requirements revision, requirements approval, and PRD server-side. Bind the receipt to their exact
identities, versions, and digests; reject missing, stale, cross-customer, corrupt, or mismatched
authority.

Project the receipt through the existing governed Product Requirements lifecycle from `DRAFT` to
`UNDER_REVIEW`, `APPROVED`, and `LOCKED`. Require the document and every requirement to be locked,
the customer to be the recorded approver, the lock timestamp to match the receipt, and PRD validation
to pass. Preserve exact-retry idempotency, restart-safe reads, canonical integrity records,
mode-0600 exclusive writes, customer isolation, path containment, closed schemas, symlink/tamper
detection, session CSRF, escaping, and restrictive browser headers. Mandatory Chromium CI proves
approval, receipt rendering, logout/login, and locked-PRD recovery.

Day 16 does not create a roadmap, estimate or schedule work, assign agents, select a pilot product,
connect a repository, generate or execute code, merge, deploy, bill, or release. Those remain
separate founder-governed modules.

# Day 15 — Traceable Customer PRD Draft

Let the authenticated owner generate one deterministic PRD v0.1 only after Day 14 has locked an
approved requirements revision. Reload all authority server-side and bind the write-once artifact to
the exact customer, request, immutable source-request digest, requirements digest, and approval
receipt digest. Map the approved journey and outcomes, must-have features, platforms, declared data
sensitivity, delivery priority, success metrics, and exclusions into stable requirement identities
with explicit source references.

Project the artifact into the existing governed Product Requirements domain and require validation
to pass while retaining `DRAFT` status, no approver, and no future roadmap. Preserve exact-retry
idempotency, restart-safe reads, canonical integrity records, mode-0600 exclusive writes, customer
isolation, path containment, closed schemas, symlink/tamper detection, session CSRF, escaping, and
browser protections. Mandatory Chromium CI proves the full signup, intake, refinement, approval,
generation, review, logout/login, and existing-draft recovery journey.

Day 15 does not approve or lock the PRD, create a roadmap, estimate or schedule work, assign agents,
connect repositories, generate or execute code, merge, deploy, bill, or release. Those remain
separate governed modules.

# Day 14 — Customer Approval and Requirements Lock

Let the authenticated owner review and explicitly approve one exact current Day 13 requirements
revision. Require the revision and full requirements digest from the rendered checkpoint, reload
current customer-scoped authority server-side, and require an affirmative confirmation before
creating one canonical write-once receipt. Bind that receipt to the customer, request, draft,
revision, source-request digest, requirements digest, confirmation contract, and server time.

Once the receipt exists, block every later draft mutation and redirect edit attempts to the approved
baseline. Preserve exact-retry idempotency, restart-safe reads, path containment, closed schemas,
exclusive mode-0600 writes, symlink/tamper detection, and generic cross-customer errors. Mandatory
Chromium CI proves confirmation, receipt rendering, edit blocking, logout, returning login, and
reopening the approved baseline.

Day 14 does not generate or approve a PRD, create a roadmap, estimate delivery, assign agents,
connect repositories, generate code, execute a product, merge, deploy, bill, or release. Those are
separate governed modules.

# Day 13 — Guided Customer Requirements Drafts

Let an authenticated customer refine one owned Day 11 request through a guided product-discovery
form. Capture the primary user journey, desired outcomes, reconciled must-have features, measurable
success signals, explicit non-goals, ordered delivery platforms, declared data sensitivity, and
delivery priority. Bind every draft to the immutable source-request digest and customer/request
identity.

Persist an append-only, contiguous revision history with canonical integrity digests, mode-0600
exclusive writes, restart-safe reads, exact-retry idempotency, optimistic concurrency, path
containment, symlink rejection, and corruption detection. A review screen clearly labels the result
as a draft. Mandatory Chromium CI proves signup, intake, refinement, saved review, logout, returning
login, and reopening the same customer-scoped draft with safe screenshot evidence.

Day 13 does not approve or lock requirements, generate a PRD, plan delivery, assign agents, connect a
repository, generate code, run product implementation, merge, deploy, bill, or release. Those remain
separate governed modules.

# Day 12 — Customer Authentication and Returning Sessions

Compose real customer account and session authority in front of the Day 11 workspace. Customers can
create a canonical-email account, sign in with a strong password, retain an HttpOnly strict-same-site
session across requests/reloads, sign out through session-bound CSRF protection, and sign back in to
recover only their existing product requests. Persist salted scrypt credential digests, bearer-token
digests, server-side CSRF values, expiry, and durable revocation markers in canonical, integrity-
checked, exclusive-write records.

The WSGI boundary supplies `REMOTE_USER` and `ascos.csrf_token` internally after session validation;
the browser cannot assert either authority. Pre-authentication forms use signed double-submit CSRF,
authentication errors avoid account disclosure, and all authentication responses are non-cacheable
with restrictive browser headers. Mandatory Chromium CI proves signup, Day 11 request submission,
logout, returning login, reload/session restoration, customer-scoped recovery, and safe evidence.

Day 12 does not implement password recovery, MFA, organizations/roles, billing, conversational
requirements, agent dispatch, repository access, coding, merge, deployment, or release. Those remain
separate later customer-application and workforce modules.

# Day 11 — Customer Workspace and Product-Request Intake

Begin the customer application with a dependency-free, server-rendered workspace. A trusted upstream
customer identity can open the dashboard, submit one bounded product brief containing the desired
outcome, target users, required features, and optional constraints, and reopen only that customer's
immutable request. Persist each request under write-once customer/request authority with canonical
integrity digests, restart-safe reads, exact-retry idempotency, and corruption detection.

The web boundary requires an upstream identity and CSRF authority, bounds request bytes/fields,
accepts only form content, escapes every customer value, applies no-store/CSP/framing/content-type/
referrer headers, and fails closed without exposing submitted values. Mandatory Chromium CI completes
the actual form and uploads a founder-safe confirmation screenshot and manifest.

Day 11 does not create customer credentials or sessions, refine requirements conversationally,
dispatch agents, implement a product, connect repositories, merge, deploy, bill, or release. Those
remain isolated later customer-application modules.

# Day 10 — PWA Verification and Safe Runtime Submission

Bind one immutable PWA plan to the exact runtime run, configuration revision/digest, full product
commit, locked acceptance profile, approved provider, canonical application paths, shell marker, and
seven ordered claims. Mandatory Chromium CI validates the manifest and 192/512 PNG icons, waits for
the exact service worker to activate and control the page, installs and launches the manifest identity
in standalone mode, refreshes
the shell, and reloads it offline. It uploads a content-addressed screenshot and safe claim manifest.

Persist a separate write-once submission plan that names the exact terminal Authentication, Voice,
and PWA plan/result digests and all locked journeys in canonical capability order. Verify every
content-addressed artifact before atomically recording complete runtime evidence and a write-once
receipt. The aggregate stops at `RUNTIME_VERIFIED`; Day 10 does not perform human acceptance, OS-level
PWA installation UI, production-product testing, merge, deployment, or release. Founder approval
unlocked the Day 11 customer application boundary.

# Day 9 — Voice and Media End-User Verification

Bind all eight locked Voice journeys to immutable exact-commit authority. Verify content-addressed
input/output WAVs, byte-identical product delivery, PCM dimensions and non-silent signal, exact
deterministic STT/response/TTS boundaries, persisted conversation turns, completed unmuted Chromium
playback, avatar speaking-to-idle state, and a second turn in the same session. Upload eight masked
screenshots, both playable WAVs, and a safe integrity manifest for founder inspection.

Day 9 uses deterministic credential-free providers and does not claim production-provider, physical
microphone/speaker, or human listening acceptance. Day 10 now adds PWA evidence and safe aggregate
submission. Merge, deployment, and release remain unavailable.

# Day 8 — Authentication Persistence and Security Evidence

Bind the six locked Authentication journeys to a write-once verification plan and derive persistence
and security claims only from digest-verified, named browser assertions. Mandatory Chromium CI runs
registration, login, logout, session restoration, password recovery, and secure error/partial-failure
paths against a real SQLite-backed exact-commit fixture and uploads a founder-safe screenshot and
claim bundle.

Day 8 does not claim production-product validation, Voice, PWA, complete aggregate acceptance, human
acceptance, merge, deployment, or release. Day 9 adds voice/media evidence and Day 10 adds PWA
evidence and safe capability aggregation.

# Day 7 — Exact-Commit Browser Journey Execution

Run immutable, acceptance-profile-bound customer journeys in a fresh Playwright Chromium context
while the exact Day 6 environment is ready. Resolve approved inputs only at invocation, block
unapproved origins, capture bounded secret-safe browser/console/network/screenshot evidence, add
migration/startup/readiness artifacts, and persist one immutable terminal result that exact retries
reuse without new effects.

Day 7 proves real login and session restoration in mandatory browser CI. Day 8 now adds the locked
Authentication persistence/security slice. Production-product validation, voice, PWA, aggregate
completion, human acceptance, merge, deployment, and release remain unavailable.

# Day 6 — Exact-SHA Managed Product Environment Lifecycle

Consume one exact persisted runtime-configuration revision under current operator policy. Prepare a
disposable detached checkout at the configured full SHA, remove Git remotes, resolve approved opaque
secret references only at invocation, run ordered migrations, start declared services without a
shell, perform redirect-free readiness checks, stop services in reverse order, and clean the
workspace. Produce bounded secret-safe lifecycle observations and retain an unsafe-to-clean
workspace as `RECONCILIATION_REQUIRED`.

Day 6 does not itself open a browser or claim customer-journey acceptance. Day 7 now composes this
lifecycle with Playwright while services are ready and still returns through shutdown and cleanup.

# Day 5 — Managed Product Runtime Configuration

Add immutable, revisioned declarations for a managed product's repository, branch, exact commit SHA,
argument-array service commands, backend/frontend/readiness endpoints, public environment bindings,
opaque secret references, and acceptance-profile identity/version/digest. Bind runtime-acceptance
runs to the exact configuration revision and digest. Configuration creation and persistence perform
no Git, subprocess, network, secret-resolution, service, browser, merge, deployment, or release
effect.

Day 6 consumes this declaration to manage an isolated environment at the exact SHA. Day 7 will add
Chrome/Playwright customer-journey execution and browser evidence. Neither capability is claimed by
Day 5.

# Milestone 15

Runtime Product Acceptance adds exact-commit feature and capability gates, managed service and
migration orchestration, browser/console/network/screenshot evidence, deterministic audio and voice
round-trip contracts, persistence and PWA verification, explicit human UX acceptance, completeness
locks, and release-candidate blocking when runtime evidence is missing or incomplete.
# Day 4 PostgreSQL validation increment

Day 4 adds always-scheduled PostgreSQL 16 CI for the bounded experimental adapter. It
validates real migrations, independent-connection claiming and fencing, optimistic
conflicts, expired-claim recovery, and restart readback. This closes the earlier
unit-only PostgreSQL verification gap; it does not complete a production database
provider.

Remaining PostgreSQL work includes full `PersistenceProvider` and durable-outbox
contract conformance, composition-root integration, deployment configuration and
security, backup/restore and point-in-time recovery, failover, capacity testing, and
sustained contention/soak testing. Until those items are implemented and accepted,
PostgreSQL remains an experimental adapter rather than a supported production runtime
backend.
# Milestone 14.1

Release Management adds governed semantic versions, candidates, approvals, release notes,
changelogs, artifacts, decisions, deployments, rollback history, comparisons, and release queries.
Release history is immutable and traceable to products, requirements, commits, and pull requests.

# Milestone 14.0

Product Requirements Management adds first-class requirements and PRDs with controlled lifecycle,
versioning, approval, locking, supersession, revision history, deterministic diffs, validation,
roadmap derivation, decision logs, atomic persistence, and requirement-to-release traceability. The
Spoken English AI PRD v1.0 is the locked product baseline. Future implementation milestones must
resolve approved requirement IDs before materialisation.

# Milestone 12.4

Add the controlled coding-provider boundary and prepare Personalised Daily
Speaking Practice Session as the first real Spoken English AI workflow through
ASCOS. The optional live adapter is deny-by-default; offline tests prove
durability, context, patch, progress, reconciliation, and security controls
without modifying the product repository.

# Milestone 12.3B

The Managed Product Execution Bridge adds separately approved execution plans,
runtime mappings, isolated workspaces, deterministic coding tasks, conservative
change policy, quality gates, review evidence, explicit completion review, and
draft-only repository effects. Live coding providers, automatic merge,
deployment, release, and production workspace infrastructure remain future
work.

# Milestone 12.3A

The Managed Product Planning Bridge connects registered identity, structural
knowledge, and deterministic project management through reviewed requests,
bounded context, provider-neutral proposals, explicit approval, and safe
materialisation. Runtime execution and live LLM planning remain future work.

# Milestone 12.2

The Project Knowledge Engine adds deterministic, read-only repository scanning,
structural symbol and dependency knowledge, statistics, queries, atomic
ASCOS-controlled persistence, and CLI access. Semantic AI and autonomous coding
remain future work.

# Milestone 12.1

The AI Project Manager adds deterministic milestone and task state,
dependency-aware next actions, integer progress, decisions, notes, risks,
typed transitions, atomic project-isolated JSON persistence, a Python API, and
CLI operations. It does not add LLM planning, autonomous agents, product
business logic, or product-repository writes.

# Milestone 12.0

The project registry establishes stable managed-product identity, repository
routing and lifecycle metadata, duplicate protection, registration events,
composition-root access, and optional atomic JSON persistence.
`spoken-english-ai` is demonstrated as the first managed product without
coupling ASCOS to or modifying its repository. Project-scoped execution,
lifecycle transition services, and database persistence remain future work.

Milestone 11.3E adds durable outbox repositories, fenced worker claims,
idempotent dispatch/application, deterministic retry, dead-letter controls,
reconciliation, crash recovery, supervisor health, and safe metrics. A future
milestone may add real worker processes. Day 4 verifies the bounded PostgreSQL
adapter's locking behavior, while full provider composition remains future work.

Milestone 11.3D establishes safe local execution, workspace and Git isolation,
offline GitHub contracts, coding-agent provider selection, durable external
task tracking, reconciliation, and explicit human approval. Worker processes,
distributed queues, and a supported production Codex/OpenAI adapter remain
future milestones.

Milestone 11.3C delivers transactional SQLite checkpoints/events, optimistic
concurrency, runtime leases, fencing, and restart recovery. Day 4 adds real-server
validation for a bounded PostgreSQL adapter; PostgreSQL remains a future full provider
behind the same contracts.

- 11.3A: deterministic end-to-end software delivery workflow.
- 11.3B: provider-neutral persistence, file checkpoints, and restart recovery.
- Future: process-safe locking, database-backed providers, incremental
  snapshots, retention policies, encrypted backups, and disaster-recovery
  automation.

Milestone 11.3B deliberately adds no database, cloud store, broker, or async
runtime.
# Milestone 11.3F

Process worker lifecycle, durable registration and heartbeat, provider health,
circuit breaking, deterministic routing, and an optional PostgreSQL concurrency
adapter are implemented. Day 4 adds PostgreSQL 16 migration, concurrency, and recovery
CI for that adapter. A future milestone must still add deployment-specific composition,
complete provider contracts, and broader real-PostgreSQL soak testing; it must not
weaken explicit-start, operator-control, idempotency, or fencing guarantees.
