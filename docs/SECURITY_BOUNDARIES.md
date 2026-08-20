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

# Process and PostgreSQL boundaries

Serializable worker configuration accepts connection references, never raw database
URLs or provider credentials. Spawned children reconstruct live clients and
connections locally. Operational state excludes environment variables, raw provider
responses, secrets, and unbounded exception text. Connection failures are mapped to
redacted provider-neutral errors.
