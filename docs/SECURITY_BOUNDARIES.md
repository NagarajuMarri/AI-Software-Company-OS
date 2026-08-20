# Security Boundaries

Outbox payloads are schema-versioned, bounded, canonical, and reject
credential-like keys. Raw claim tokens are never stored—only hashes. Events,
attempts, metrics, audit summaries, and dead-letter views omit raw provider
payloads, credentials, and command output.

Credentials are injected only at adapter invocation and are excluded from
checkpoints, events, task payloads, command logs, and exception messages.
Executables, environment keys, repository URLs, paths, branches, output size,
and timeouts are allow-listed or bounded.

External providers and generated patches are untrusted. Human review is
required before approval; protected branches deny writes by default. Operators
must restrict workspace roots, use least-privilege credentials, review audit
records, reconcile interrupted operations, and rotate any credential suspected
of exposure.

# Software Architect workforce boundaries

Day 24 treats Software Architect provider output and every nested architecture field as untrusted.
The composition requires the exact persisted Day 23 Product Manager artifact, opportunity digest,
tenant, `AgentRole.SOFTWARE_ARCHITECT`, provider, capability tuple, ordered action tuple, Twin,
assignment, objective digest, and unexpired authority before provider activity. The profile has an
empty tool allowlist, zero tool-call budget, and no live-provider authorization. The provider
receives only bounded non-secret Product Manager plan fields through the Day 22 typed request; it
receives no filesystem, environment, subprocess, repository, network, credential, persistence,
approval, budget, deployment, or release capability.

After runtime execution, the service rebuilds the deterministic provider request and result, requires
their digests to match the terminal receipt, validates a closed typed architecture schema, and only
then writes state. The artifact store is tenant/execution scoped, canonical, mode 0600, write once,
bounded, path contained, and integrity checked. Reads reject unsafe permissions, symlinks, unknown
entries, malformed nested records, identity mismatch, non-canonical data, and tampering. Raw provider
payloads and exceptions, credentials, customer secrets, and local paths are not stored.

Every artifact remains `DRAFT_AWAITING_HUMAN_ARCHITECTURE_REVIEW`; technology recommendations and
ADRs remain `PROPOSED`, ADRs require human approval, and pilot state is fixed to `NOT_SELECTED`. The
exact action set excludes architecture approval, engineering-task creation, source/repository writes,
commands, commit, merge, deployment, release, billing, budget allocation, and pilot selection. Day 24
also excludes Day 25 engineering execution and Day 30 multi-agent orchestration.

# Leadership workforce boundaries

Day 23 treats the CEO and Product Manager provider output as untrusted. The composition requires an
exact role, provider, capability tuple, ordered delegated-action tuple, tenant, Twin, assignment,
objective digest, and unexpired authority before execution. Both profiles have an empty tool
allowlist and zero tool-call budget. The CEO may frame opportunity intake and status; the Product
Manager may clarify scope, propose a draft product plan, and report status only from the exact
persisted CEO artifact. Neither profile receives filesystem, environment, subprocess, repository,
network, credential, approval, budget, deployment, or release capabilities.

The generic runtime persists only digest evidence. Day 23 separately rebuilds the deterministic
role result, requires its output digest to match the terminal runtime receipt, validates a closed
typed artifact, and only then writes bounded canonical mode-0600 state. Artifact directories are
tenant/execution scoped and closed; records are write once and integrity checked, and reads reject
symlinks, unsafe permissions, malformed schemas, unknown entries, path escape, and tampering. Raw
provider payloads, exceptions, credentials, and local paths are not stored.

Every role artifact is `DRAFT_AWAITING_HUMAN_REVIEW`, reports human-decision blockers, and fixes
pilot state to `NOT_SELECTED`. Exact action profiles exclude approval and governance changes,
investment or budget allocation, repository writes, commit, merge, deployment, billing, release,
and pilot selection. Day 23 also excludes Day 24 architecture, technology, ADR, and technical-risk
behavior, engineering execution, and Day 30 multi-agent orchestration.

# Digital Twin execution boundaries

Day 22 treats the Digital Twin provider, its structured result, and every tool request as untrusted.
The runtime compares the exact tenant, Twin, Business Role, assignment, objective, authority,
capability, provider, and tool bindings before activity. Delegation expires within 24 hours and has
explicit action, tool-call, and output limits. Prohibited approval, governance, repository-write,
commit, merge, deployment, release, billing, and pilot-selection actions are invalid model values,
not conventions in a prompt.

Providers receive an immutable bounded request and one gateway capability. They do not receive a
filesystem, environment, subprocess runner, repository adapter, network client, persistence store,
or credential resolver. The Day 22 runtime registry accepts read-only tools only; every call is
checked against the assignment, Twin, delegation, provider, registry, call count, and byte budget.
Context and structured fields reject secret-bearing keys. Tool and provider values remain ephemeral;
persistence retains only identities, sanitized fixed summaries, and canonical digests. Raw provider
exceptions never enter a receipt.

Execution intent is exclusively written before provider activity. Per-execution file locking,
mode-0600 records, canonical envelopes, tenant/path containment, closed directories, bounded reads,
and symlink, permission, schema, and digest validation protect restart state. A complete receipt
makes exact retry side-effect free. A prepared live-provider intent without a receipt is not retried;
it requires reconciliation. Live provider use additionally requires both an exact delegation flag
and explicit operator enablement. Day 22 ships no live provider, mutating tool, or product authority.

# Managed runtime configuration boundaries

Managed runtime configuration persists public environment bindings and opaque secret references,
never resolved secret values. Secret-like keys are prohibited in public bindings, and the same key
cannot appear in both public and secret sets. Repository and endpoint URLs cannot contain embedded
credentials. Configuration digests cover opaque references, not secret values, so credential rotation
does not require exposing or rewriting an accepted record.

Commands are argument arrays with preserved order. Shell interpreters, shell operators, unsafe
relative working directories, and unbounded values are rejected before persistence. Registration
enforces operator-owned repository-host, executable, origin, environment-name, and exact or
prefix-based opaque-secret-reference policies. Loopback HTTP is allowed only for an isolated local
environment; non-loopback service endpoints require HTTPS, and every readiness origin must be
explicitly allowed by the declaration.

The configuration service has no Git, subprocess, socket, HTTP, secret-manager, or browser adapter.
Day 6 and Day 7 providers must consume a verified configuration revision and remain subject to
separate authorization, workspace containment, redaction, evidence, and shutdown controls.

# Managed product environment boundaries

Day 6 is the first managed-runtime side-effect boundary. It reloads an exact persisted configuration
revision and rechecks current operator policy before resolving a secret or invoking Git. Local source
preparation disables interactive Git and ambient system/global configuration, checks out the full SHA
detached, removes every remote, rejects escaping symlinks and working directories, and uses a private
run-specific workspace.

Runtime commands are exact argument arrays with no shell. Processes receive only a minimal base
environment plus exact declared public and resolved-secret bindings. Raw output is not retained;
secret values are replaced before bounded output hashing. Readiness disables ambient proxies and
redirects and can contact only a configuration and operator-approved origin. Every started process is
stopped in reverse order after success or failure. Unproven process termination or cleanup fails
closed as `RECONCILIATION_REQUIRED` and retains the workspace for explicit operator handling.
The included local provider requires POSIX process-group control. Windows construction fails closed
until a Job Object or equivalent full-process-tree adapter is implemented.

The environment result omits raw output, secret values/references, process handles, and local paths.
Day 6 has no browser, repository-write, merge, deployment, or release API.

# Managed browser boundaries

Day 7 composes the exact environment with a fresh headless Chromium context. It blocks unapproved
origins and stores no headers, cookies, authorization, browser storage, request bodies, or response
bodies. Recorded URLs omit credentials, query, and fragment. Console output is bounded and resolved
values are redacted; final screenshots mask secret input locators. Browser execution shares the
runner host and is not yet a hostile-code container/VM sandbox. It exposes no repository-write,
human-acceptance, merge, deployment, or release operation.

# Authentication verification boundaries

Day 8 reloads write-once authentication authority and checks its exact run, product, browser-plan,
runtime-configuration, full-SHA, acceptance-profile, provider, journey, assertion, claim, and evidence
bindings before invoking the underlying browser. Persistence and security claims are derived only
from content-addressed browser summaries with matching digests and named passed assertions. Missing,
corrupt, or mismatched source evidence fails closed and remains durable.

The mandatory end-user fixture stores only salted password hashes and session/reset-token hashes.
Evidence and the founder verification pack exclude raw passwords, cookies, session/reset values,
headers, bodies, browser storage, and local paths. The pack contains bounded claim identifiers,
digests, outcomes, and masked screenshots. The fixture is an isolated exact-commit validation target,
not a hostile-code sandbox or a production product.

# Voice and media verification boundaries

Day 9 binds deterministic input/output media to immutable content digests, exact product endpoints,
the full source SHA, and named Voice journey assertions. Media fetches disable ambient proxies and
redirects, stay on the already authorized frontend origin, enforce a ten-megabyte bound and safe WAV
type, and require byte equality with the locked fixture. PCM parsing rejects malformed, compressed,
silent, near-silent, or dimension-mismatched content.

Playback evidence comes from provider-owned Chromium checks of decoded duration, completed position,
unmuted state, and bounded volume; application text alone cannot satisfy playback. Evidence contains
only fixture/output digests, bounded signal measurements, claim identifiers, and response length.
It excludes request/response bodies, credentials, cookies, browser storage, local paths, and provider
secrets. Deterministic CI uses no production STT, LLM, or TTS credential and is not a hostile-code,
physical-speaker, production-provider, or human-listening acceptance boundary.

# PWA verification and aggregate-submission boundaries

Day 10 reloads immutable PWA authority and rechecks exact run, configuration, full-SHA, profile,
provider, origin, path, shell-marker, and claim bindings before execution. Chromium blocks unrelated
origins. Manifest and icon retrieval forbids redirects, credentials, queries/fragments, unbounded
content, unsafe paths, unexpected media types, and incomplete installability metadata. Evidence omits
console text, headers, cookies, request/response bodies, browser storage, query strings, credentials,
and local paths. Offline verification changes only the disposable browser context and the managed exact-SHA
environment is still stopped and removed afterward.

Aggregate plans and receipts are path-contained canonical write-once records. Submission validates
the exact Authentication, Voice, and PWA result digests, journey coverage, evidence links, and every
content-addressed artifact before runtime acceptance changes. It exposes no human-acceptance, source
write, merge, deployment, or release operation and stops at `RUNTIME_VERIFIED`.

# Customer product-request boundaries

Day 11 accepts identity only from a trusted WSGI `REMOTE_USER` gateway and accepts CSRF authority only
from server-side session middleware; neither value is read from a customer-controlled header or form
as identity authority. Requests require a matching CSRF value, exact form content type, declared and
bounded byte length, a closed field set, single values, bounded text/items, safe identifiers, and
timezone-aware server submission time. Invalid requests return a generic response without echoing
customer content.

Customer values are escaped before rendering. Responses are non-cacheable and carry restrictive CSP,
frame, content-type, and referrer headers. Persistence is customer-scoped, canonical, integrity
digested, path-contained, write-once, and exact-retry idempotent. Cross-customer reads, traversal,
symlink escape, corruption, and changed identity reuse fail closed. Day 11 stores product briefs and
therefore excludes credentials, secrets, regulated data, uploads, agent execution, repository access,
merge, deployment, billing, and release.

# Customer authentication boundaries

Day 12 owns customer identity before the Day 11 portal. Canonical email is lookup authority, but raw
email never becomes a filesystem name. Passwords are invocation-only and converted to per-account
salted scrypt digests; raw bearer tokens are returned only to the browser and persistence uses their
SHA-256 digests. Session records bind one customer to an independent CSRF value, issue time, twelve-
hour expiry, and durable revocation marker. Account, session, and revocation records are closed-schema,
canonical, integrity checked, path contained, exclusive-write, mode 0600 authorities.

Signup and login use a signed double-submit pre-authentication CSRF cookie. Authenticated mutation
uses the server-side session CSRF value. Cookies are HttpOnly and SameSite=Strict, Secure in normal
operation, and explicitly non-Secure only for the loopback HTTP browser fixture. Authentication
failure pages are generic and do not echo submitted identifiers or credentials. All responses use
no-store, restrictive CSP, frame denial, sniffing denial, and no-referrer policy. The middleware, not
the customer request, injects `REMOTE_USER` and `ascos.csrf_token` into the portal.

This development file adapter does not provide password recovery, MFA, rate limiting, breached-
password screening, organizations/roles, distributed session storage, encryption at rest, production
email delivery, billing, deployment, or release. Production exposure requires those later controls,
TLS termination, a managed database/secret, monitoring, backup, and operational abuse protection.

# Customer guided-requirements boundaries

Day 13 accepts a source request only through the authenticated customer-scoped Day 11 service. It
never trusts a form customer ID, source digest, revision timestamp, or draft identity. The service
loads those authorities server-side, derives a bounded draft ID, orders platform selections, binds
the current immutable request digest, and assigns the next revision and time.

Draft records are closed-schema canonical JSON with integrity digests and exclusive mode-0600
writes. History is append-only and requires contiguous revision filenames. Exact-retry reuse and
optimistic concurrency prevent duplicate effects and lost updates. Path containment, identifier
validation, symlink rejection, history bounds, source-digest verification, corruption detection, and
cross-customer request lookup fail closed.

The web boundary accepts only bounded URL-encoded forms with exact fields and session CSRF, escapes
all customer content, does not echo invalid values, and applies no-store, restrictive CSP, frame
denial, sniffing denial, and no-referrer headers. The data-sensitivity selection is a customer
declaration, not automatic data discovery or a compliance certification. Day 13 stores product
requirements and therefore forbids credentials, secrets, uploaded files, regulated records, agent
execution, repository access, approval, coding, merge, deployment, billing, and release authority.

# Customer requirements-approval boundaries

Day 14 trusts customer identity and CSRF only from the Day 12 session middleware. The form may carry
only the rendered revision, complete draft digest, CSRF value, and one fixed confirmation value; it
cannot assert a customer, request digest, approval identity, time, or downstream authority. The
service reloads the owned immutable request and latest draft and compares the digest in constant
time before creating the receipt.

Approval receipts use a closed canonical schema, full integrity digest, exclusive mode-0600 write,
bounded derived identity, contained customer/request path, and symlink/unknown-entry rejection. A
receipt is write-once and binds the exact source and draft digests. Its existence is the draft lock;
all later edits fail closed and edit routes return the approved baseline. Tampered or mismatched
receipts make both approval inspection and future draft mutation unavailable rather than reopening
the scope.

The development file adapter provides deterministic single-instance evidence, not a cross-process
transactional guarantee. Production exposure requires a transactional database constraint spanning
approval creation and draft revision, encryption/backup/retention controls, monitoring, rate limits,
and privacy review. Customer approval is scope confirmation only: it conveys no PRD, planning,
agent, repository, coding, merge, deployment, billing, or release authority.

# Customer PRD-draft boundaries

Day 15 treats the Day 14 receipt as the only generation authority. Customer identity and CSRF come
from Day 12 session middleware; the form may carry only the fixed action and the rendered approval
digest. The service reloads the request, approved requirements revision, and receipt server-side,
requires exact customer/request/source/draft/approval bindings, and validates the resulting artifact
through the existing governed Product Requirements domain. The deterministic generation profile
makes no network, external AI, repository, secret-manager, subprocess, or agent call.

The PRD record is a closed canonical write-once envelope with a full integrity digest, bounded stable
identities, exclusive mode-0600 creation, path containment, unknown-entry and symlink rejection, and
restart verification. Customer-provided content is escaped in the read-only review page. Persisted
data contains the approved product scope and may contain customer-declared personal-data intent, but
must not contain credentials, secrets, uploads, or regulated records.

The development file adapter is single-instance evidence. Production exposure requires a
transactional database uniqueness constraint, encryption, backup/restore, retention/deletion,
monitoring, abuse controls, and privacy review. A generated artifact is `DRAFT` only: it has no
approver, roadmap, estimate, agent assignment, repository access, coding, merge, deployment, billing,
or release authority.

# Customer PRD-approval boundaries

Day 16 trusts customer identity and CSRF only from the Day 12 session middleware. The approval form
may carry only the rendered PRD digest, the fixed confirmation value, and session CSRF; it cannot
assert customer, product, source, requirements, approval, PRD identity, time, lifecycle status, or
downstream authority. The service reloads the complete Day 11-15 chain server-side, compares every
digest binding, and fails closed on missing, stale, cross-customer, corrupt, or mismatched authority.

The receipt is a closed canonical write-once record with a full integrity digest, bounded derived
identity, exclusive mode-0600 creation, path containment, unknown-entry and symlink rejection, exact
retry idempotency, and restart validation. Customer text is escaped on both the approval checkpoint
and receipt. The locked governed projection must traverse the existing review, approval, and lock
states; it records the authenticated customer as approver, locks every requirement at the receipt
time, and must pass PRD validation.

The development file adapter is deterministic single-instance evidence. Production exposure
requires transactional uniqueness, encryption and managed keys, backup/restore, retention/deletion,
monitoring, abuse controls, rate limits, and privacy review. A locked PRD is scope authority only: it
does not create a roadmap or estimate, select a pilot, assign an agent, connect a repository, generate
or execute code, merge, deploy, bill, or release.

# Customer roadmap-draft boundaries

Day 17 trusts customer identity and CSRF only from the Day 12 session middleware. The generation form
may carry only session CSRF and the rendered PRD-approval digest; it cannot assert customer, product,
upstream identities, requirement mappings, milestone order, generation time, status, estimate,
schedule, assignee, repository, or execution authority. The service reloads the complete Day 11-16
chain, reconstructs and validates the locked governed PRD, and fails closed on missing, stale,
cross-customer, corrupt, tampered, or mismatched authority.

Roadmap structure comes only from the existing governed roadmap and roadmap-item derivation. The
service requires exact stable IDs and ordering, compares milestone and priority mappings, and proves
that every locked requirement occurs once. The deterministic profile makes no network, external AI,
secret-manager, repository, subprocess, or agent call.

The record is a closed canonical write-once envelope with a full integrity digest, bounded derived
identity, exclusive mode-0600 creation, path containment, unknown-entry and symlink rejection, exact
retry idempotency, and restart reconstruction. Customer text is escaped on both checkpoint and review
pages. The development adapter remains single-instance evidence; production exposure requires
transactional uniqueness, encryption and managed keys, backup/restore, retention/deletion,
observability, rate limits, abuse controls, and privacy review.

The roadmap is `DRAFT` only. It does not approve a plan, estimate or schedule work, assign people or
agents, select a pilot, connect a repository, create implementation tasks, generate or execute code,
merge, deploy, bill, or release.

# Customer roadmap-approval boundaries

Day 18 trusts customer identity and CSRF only from the Day 12 session middleware. The approval form
may carry only the exact rendered roadmap digest, one fixed confirmation value, and session CSRF; it
cannot assert customer, upstream authority, roadmap identity, requirement mappings, item state,
approver, time, or downstream authority. The service reloads the complete Day 11-17 chain
server-side, compares every identity and digest binding, reconstructs the governed mapping, and
fails closed on missing, stale, cross-customer, corrupt, tampered, or mismatched authority.

The approval receipt is a closed canonical write-once record with a full integrity digest, bounded
derived identity, exclusive mode-0600 creation, contained customer/request path, exact-retry
idempotency, restart validation, and rejection of unknown entries and symlinks. The receipt is the
only authority for the locked projection. That projection preserves exact stable roadmap-item IDs,
order, requirement IDs, and priorities, changes only the roadmap/item statuses to `LOCKED`, records
the authenticated customer and receipt time, and is revalidated on every read. Once locked, draft,
review, and approval-entry routes redirect to the immutable receipt.

The development adapter remains deterministic single-instance evidence. Production exposure
requires transactional uniqueness spanning roadmap and receipt, encryption and managed keys,
backup/restore, retention/deletion, observability, rate limits, abuse controls, and privacy review.
A locked roadmap is immutable planning scope only: it grants no estimate, date, schedule, staffing,
agent, repository, task, code, merge, deployment, billing, release, or official pilot-product
authority.

# Customer delivery-estimate boundaries

Day 19 trusts customer identity and CSRF only from the Day 12 session middleware. The generation
form may carry only the exact rendered roadmap-approval digest and session CSRF; it cannot assert
customer, request, roadmap, approval, product, PRD, requirement mapping, estimate identity, time,
range, confidence, assumptions, or downstream authority. The service reloads the complete Day 11-18
chain and governed locked projection, compares all identity and digest bindings, and fails closed on
missing, stale, cross-customer, corrupt, tampered, unlocked, or mismatched authority.

The deterministic model uses only governed requirement priority/category, declared data sensitivity,
approved platforms, and locked scope count. It performs no network, external-AI, secret-manager,
repository, subprocess, or agent call. Every locked requirement must map exactly once to its existing
governed roadmap item. Effort ranges, points, drivers, confidence, and assumptions are explanatory
signals, not a commitment or hidden execution instruction.

The estimate is a closed canonical write-once record with a full integrity digest, bounded derived
identity, exclusive mode-0600 creation, contained customer/request path, exact-retry idempotency,
restart reconstruction, and rejection of unknown entries, symlinks, and tampering. Customer text is
escaped on checkpoint and review pages; browser evidence excludes passwords, bearer tokens, cookies,
CSRF values, salts, and local paths. The development adapter remains single-instance evidence;
production exposure requires transactional uniqueness, encryption and managed keys, backup/restore,
retention/deletion, observability, rate limits, abuse controls, and privacy review.

The artifact remains `DRAFT`. An engineering day is relative effort rather than calendar duration.
Day 19 grants no approval, price, quote, date, schedule, staffing, agent, repository, implementation
task, code, merge, deployment, billing, release, or official pilot-product authority.

# Customer project-progress boundaries

Day 20 trusts customer identity and CSRF only from the Day 12 session middleware and exposes one
GET-only view. It accepts no progress mutation or customer-asserted identity, digest, milestone,
task, assignment, blocker, decision, or execution authority. The service reloads the complete
Day 11-19 customer authority chain on every read and requires exact request, PRD, locked-roadmap,
roadmap-approval, estimate, digest, and ordered requirement bindings. Missing, cross-customer,
corrupt, stale, tampered, or mismatched authority fails closed.

The dashboard is a deterministic non-persistent projection. Existing governed roadmap items become
visible milestones and locked requirements become non-executable planned tasks exactly once. ASCOS's
existing Project Manager progress calculation must independently return zero progress for this
not-started state. Operational agent assignments are deliberately empty. Open blockers describe
missing authority and later capabilities; they do not become executable tasks. Decisions expose
only bounded labels, rationale, time, and the exact safe authority digest.

Customer content is escaped and responses remain non-cacheable with restrictive CSP, frame denial,
sniffing denial, and no-referrer policy. Browser evidence excludes passwords, bearer tokens,
cookies, CSRF values, salts, and local paths. Day 20 has no persistence adapter, mutation route,
agent runtime, repository adapter, subprocess, external AI, network-provider, code, deployment,
release, billing, pilot-selection, or Day 21 authority.

# Customer preview-and-evidence boundaries

Day 21 trusts customer identity and CSRF only from the Day 12 session middleware. Customer routes
can read the centre, follow the recorded preview link, and submit a closed five-field review form;
they cannot publish or replace a preview/evidence package. The service reloads the exact Day 20
projection and validates customer/request/product identities plus progress, locked-roadmap, and
estimate digests. Browser-submitted customer IDs, commit SHAs, evidence, preview URLs, progress, or
downstream authority are never trusted.

Preview URLs must be credential-free, query-free, fragment-free, path-bearing HTTPS URLs. Plain
HTTP is allowed only for loopback browser fixtures. Their canonical origin must match an explicit
service allowlist both at publication and read time. Evidence artifact URLs are similarly bounded;
every artifact must use the existing governed runtime-acceptance model, cover the six required
test/browser/security kinds, and bind the same full commit SHA. Failed required evidence cannot be
accepted. `REVISE` requires comments; both decisions require the exact package digest, a fixed
review confirmation, and session CSRF.

The package and review receipt use exclusive mode-0600 canonical writes, full integrity digests,
stable bounded identifiers, customer/request path containment, exact-retry idempotency, closed
directories and schemas, restart validation, and symlink/tamper rejection. Content is escaped;
responses are non-cacheable and keep CSP, frame denial, sniffing denial, and no-referrer policy.
Evidence excludes passwords, bearer tokens, cookies, CSRF values, salts, and local paths. Day 21
contains no preview deployment, agent runtime, task runner, repository adapter, subprocess,
external-AI provider, billing, merge, release, pilot-selection, or Day 22 authority.

# Process and PostgreSQL boundaries

Serializable worker configuration accepts connection references, never raw database
URLs or provider credentials. Spawned children reconstruct live clients and
connections locally. Operational state excludes environment variables, raw provider
responses, secrets, and unbounded exception text. Connection failures are mapped to
redacted provider-neutral errors.
