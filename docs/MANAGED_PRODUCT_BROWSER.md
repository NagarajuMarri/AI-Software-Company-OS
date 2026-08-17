# Managed Product Browser Execution

Day 7 adds the first real end-user browser boundary. ASCOS can load an immutable browser journey
plan, start the exact Day 6 managed environment, resolve approved browser credentials only when the
environment is ready, run declarative journeys in headless Chromium, and retain exact-commit browser,
console, network, screenshot, migration, startup, and readiness evidence.

This module is an execution and evidence engine. It does not invent product-specific selectors or
credentials, modify a managed product, submit human acceptance, merge, deploy, or release.

## Exact authority

`BrowserJourneyPlan` binds the acceptance run and product, runtime-configuration revision/digest,
full commit SHA, acceptance-profile identity/digest, every customer-facing journey, ordered steps,
and public inputs or opaque secret references. `ManagedProductBrowserService` loads all three
persisted authorities and rejects any mismatch before resolving a browser secret or starting the
environment. Current policy must still approve the provider, every runtime origin, and every browser
secret reference.

Plans are write-once. The file store writes canonical schema-versioned JSON, verifies identity and
digest on restart, rejects mutation and corruption, and never persists a resolved secret.

## Declarative end-user steps

Plans use bounded accessible role, label, text, and test-ID locators. Supported actions are click,
fill, visible-text assertion, URL-path assertion, and reload. Arbitrary JavaScript, CSS, XPath,
shell, and browser-evaluation code are not accepted. Paths cannot contain queries, fragments,
backslashes, repeated separators, or literal/encoded traversal. Secret-bearing inputs must use
opaque invocation-only references.

## Browser and network boundary

`PlaywrightChromiumProvider` creates a fresh headless Chromium context per journey with a fixed
viewport, UTC timezone, downloads disabled, service workers blocked, and TLS validation enabled.
Requests are intercepted before dispatch. Only origins declared by the runtime configuration and
current browser policy may be contacted; any other request is aborted and fails the journey.

Network evidence contains only method, resource type, status, and a URL stripped of credentials,
query, and fragment. It never records headers, cookies, authorization, request bodies, response
bodies, or browser storage. Console text is bounded and resolved values are redacted longest-first.
Console/page errors, failed requests, HTTP errors, blocked origins, failed steps, or failed screenshot
capture make the journey fail.

The final screenshot masks secret input locators. Product-specific plans must still ensure the final
screen does not echo credentials elsewhere; Day 7 does not claim that arbitrary screenshots can be
semantically scrubbed after capture.

## Evidence and restart behavior

Browser summary, console, network, and PNG bytes are stored under SHA-256 identities.
`ContentAddressedBrowserArtifactStore` verifies existing/resolved bytes.
`FileBrowserExecutionStore` persists one immutable terminal result for the exact product/run/plan.
An exact retry returns that result without starting another browser or environment.

The result also contains content-addressed Day 6 migration, service-startup, and readiness
observations. Failure evidence cannot be rewritten as success. If shutdown or cleanup cannot be
proven, the result is `RECONCILIATION_REQUIRED`.

Browser evidence is not submitted directly into the Milestone 15 acceptance aggregate on Day 7.
Authentication persistence/security, voice, PWA, and complete multi-journey aggregation remain Days
8–10. Advancing the lifecycle from a partial browser bundle would prevent safe later aggregation.

## Required validation

The mandatory `browser` GitHub Actions job installs the pinned Playwright package and Chromium and
runs a real exact-SHA fixture. It clones a local Git product, migrates and starts it, logs in through
the browser using an invocation-only password, receives an HTTP-only session cookie, reloads the
dashboard to prove session restoration, captures all four browser evidence kinds, stops the service,
removes the workspace, and restart-loads every immutable result/artifact.

The ordinary quality job remains browser-binary-free. The integration test skips there and must pass
in the dedicated browser job on the exact pull-request head commit.

## Remaining boundaries

The Day 6 local environment remains POSIX-only. Browser execution shares the runner host and is not a
production hostile-code sandbox. Container/VM isolation, durable in-flight browser recovery,
product-specific SpeakMate journey configuration, remaining capability probes, human acceptance,
deployment, and release remain later work.
