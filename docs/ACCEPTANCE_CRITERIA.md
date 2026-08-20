# Runtime Persistence Acceptance Criteria

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
may only be claimed when the optional test database is configured.

# Milestone 12.0 acceptance

Managed projects require stable validated identities, normalized repository
uniqueness, deterministic lookup and lifecycle filtering, registration events,
composition-root access, and restart-safe atomic file persistence. The first
managed product registration must reference Spoken English AI portably and
must not modify its repository.
