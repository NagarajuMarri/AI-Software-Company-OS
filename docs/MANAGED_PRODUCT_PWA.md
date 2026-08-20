# Managed Product PWA Verification and Runtime Submission

Day 10 closes the deterministic runtime-testing engine without granting release authority. It adds an
immutable PWA verification plan, a real Chromium provider, and a separate write-once aggregate
submission plan. All three are bound to the exact managed product commit, runtime configuration
revision/digest, acceptance profile identity/digest, and runtime run.

## PWA authority and execution

`PwaVerificationPlan` fixes the provider, canonical start/manifest/service-worker paths, visible app
shell marker, and ordered claims. `ManagedProductPwaService` reloads that authority, rechecks current
provider/origin policy, and composes it with the Day 6 exact-SHA environment lifecycle. The provider
uses a fresh headless Chromium context with external origins blocked and service workers enabled.

A pass requires:

1. an exact same-origin, redirect-free, bounded manifest with name, short name, standalone-capable
   display, `/` scope, the declared start path, and PNG icons declaring 192x192 and 512x512;
2. the declared service worker in `activated` state and controlling the refreshed page;
3. zero Chromium installability errors, browser-level installation of the exact manifest identity,
   an authorized launched target with standalone user display mode, and a normal refresh;
4. the same controlled shell after Chromium network access is disabled;
5. no browser console/page error, plus content-addressed browser, console, network, PWA, screenshot,
   migration, startup, and readiness evidence.

The provider never records console text, headers, cookies, request/response bodies, browser storage,
credentials, or URL query strings. A failed or unavailable browser, incomplete claim set, artifact mismatch, shutdown
failure, or cleanup uncertainty cannot become passing evidence.

## Complete-capability submission

`AcceptanceSubmissionPlan` names exactly three immutable terminal sources in canonical order:
Authentication, Voice, and PWA. Each source binds its capability, plan ID/digest, result digest, and
complete journey IDs. `RuntimeAcceptanceAggregator` verifies the current acceptance binding, every
source field, all content-addressed artifacts, evidence links, unique IDs, and complete locked journey
coverage before calling the existing Milestone 15 runtime-verification gate.

The file store uses path-contained, write-once canonical JSON plans and receipts. Exact retries return
the existing `RUNTIME_VERIFIED` run only when its receipt and evidence digest still match. Stale,
partial, duplicate, reordered, corrupted, or mutated submissions fail closed.

## Physical evidence

The required browser CI job executes a real exact-SHA fixture and uploads
`day10-founder-pwa-verification`. Download it from the pull request's successful workflow run to inspect
`pwa-install-offline.png` and `manifest.json`. The manifest contains only commit/plan/result/evidence
digests and claim outcomes.

This module verifies deterministic PWA installability prerequisites and standalone/offline browser
behavior. It does not click an operating-system install prompt, test a deployed customer product,
approve human UX, merge code, deploy, or release. Those gates remain explicit and unavailable here.
