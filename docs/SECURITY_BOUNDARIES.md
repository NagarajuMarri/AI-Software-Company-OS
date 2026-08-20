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

# Process and PostgreSQL boundaries

Serializable worker configuration accepts connection references, never raw database
URLs or provider credentials. Spawned children reconstruct live clients and
connections locally. Operational state excludes environment variables, raw provider
responses, secrets, and unbounded exception text. Connection failures are mapped to
redacted provider-neutral errors.
