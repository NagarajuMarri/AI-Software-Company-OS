# Managed Product Authentication Verification

Day 8 adds a bounded authentication evidence provider on top of the exact-SHA environment and
Playwright browser boundaries from Days 6 and 7. It verifies the six locked SpeakMate V1
authentication journeys: registration, login, logout, session restoration, password recovery, and
secure error/partial-failure handling.

## Immutable authority

An `AuthenticationVerificationPlan` is write-once and binds the acceptance run, product, browser
plan ID and digest, runtime-configuration revision and digest, full commit SHA, acceptance-profile
identity and digest, provider, ordered journey contracts, required browser step IDs, and exact
authentication claims. File-backed plans are content-verified on write and load, reject path and
symlink escapes, survive restart, and cannot be silently replaced.

The provider reloads this persisted authority and checks every binding before invoking its underlying
browser provider. It derives persistence and security evidence only from digest-verified browser
summaries whose named assertions passed. A missing, failed, corrupt, or mismatched assertion produces
durable failed evidence; it cannot be converted into a passing authentication claim.

## Real end-user verification

Mandatory browser CI creates an exact-commit disposable product checkout, migrates a real SQLite
database, starts the product service, and drives Chromium through all six customer journeys. The
fixture proves registration persistence, duplicate rejection, login, logout revocation, session
restoration, password replacement with old-password rejection, single-use reset, generic unknown
account responses, invalid-token rejection, transactional rollback, throttling, password hashing,
and session/reset-token hashing. Shutdown, workspace cleanup, and persisted-result restart readback
are required for success.

The job uploads `day8-founder-verification`, containing a secret-safe manifest and one masked final
screenshot per journey. The manifest records claim outcomes and content digests, not credentials,
cookies, session values, reset values, headers, bodies, or browser storage.

## Boundary and remaining work

This module verifies an isolated exact-SHA product fixture, not a deployed production product. It
does not resolve PWA evidence, human acceptance, release completion, merge, deploy, or release. Day 9
now adds deterministic voice and media verification. Day 10 adds PWA verification and safe submission
of complete capability slices to the runtime-acceptance aggregate.
