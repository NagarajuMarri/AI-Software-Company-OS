# Milestone 15 — Runtime Product Acceptance & Feature Quality Gates

Milestone 15 makes customer-runtime evidence a first-class ASCOS release control. Implementation
and unit-test success no longer imply that a managed product feature works. A locked capability must
complete this lifecycle:

`PLANNED → IMPLEMENTED → AUTOMATED_VERIFIED → RUNTIME_VERIFIED →`
`HUMAN_ACCEPTANCE_REQUIRED` (when applicable) `→ ACCEPTED → COMPLETED`.

## Runtime acceptance aggregate

`runtime.runtime_acceptance` owns versioned capability contracts, customer journeys, exact-commit
evidence, journey results, human decisions, completeness reports, atomic persistence, and runtime
orchestration. Evidence and decisions are append-only. A completed run is immutable. The capability
contract, journey definitions, run identity, and creation time are immutable after planning. Failed
automated or customer-runtime evidence remains release-blocking audit history; retry after a failed
observation requires a new exact-commit acceptance run.

Every evidence artifact binds:

- managed product and acceptance run;
- locked capability and customer journey;
- full Git commit SHA;
- evidence kind and pass/fail outcome;
- artifact URI and SHA-256 digest;
- UTC observation time and bounded metadata.

## Managed runtime configuration binding

Day 5 adds the immutable declaration consumed by future runtime providers. A configuration revision
binds a registered product and repository to an expected branch, exact commit SHA, argument-array
service commands, backend/frontend/readiness endpoints, public environment policy, opaque secret
references, and an acceptance-profile ID, version, and digest. The complete declaration has a
canonical digest.

Before runtime evidence can be attributed to a configuration, the acceptance run must match its
product and exact commit and the independently supplied acceptance profile must match its bound
identity, version, and digest. The binding retains the configuration ID, revision, digest, and profile
digest; a later revision cannot silently redefine earlier evidence.

Configuration storage is not runtime orchestration. It does not clone or inspect Git, start a
process, resolve a secret, contact an endpoint, open a browser, merge code, deploy, or release. Day 6
will implement exact-SHA environment lifecycle. Day 7 will implement the Chrome/Playwright browser
provider and actual end-user journeys.

The evidence digest covers the complete locked capability and journey definitions, journey-result
timestamps, and every artifact's capability/journey ownership. Secret-bearing metadata keys are
rejected before persistence.

Code and automated-test evidence are required before runtime verification. Actual runtime acceptance
also requires service-startup, readiness, migration, browser, browser-console, browser-network, and
screenshot evidence for customer-facing capabilities. Journey contracts add capability-specific
requirements such as persistence, security, deterministic audio, STT, LLM, TTS, audible playback,
avatar synchronization, and PWA behavior.

## Managed product orchestration

`RuntimeAcceptanceOrchestrator` defines the explicit product-adapter sequence below. Day 5 does not
yet provide the environment or browser adapter that executes it:

1. verify the checked-out commit;
2. verify migrations;
3. start services;
4. wait for readiness;
5. run browser journeys and collect console/network/screenshots;
6. run capability journeys;
7. inspect persistence;
8. verify PWA behavior;
9. stop services, including after probe failure.

The adapter boundary permits Playwright or another approved browser provider without coupling ASCOS
to a product framework. Deterministic audio fixtures carry a hashed media artifact and expected
transcript; production credentials and raw secrets are never evidence metadata.

## Completeness locks

Completeness is evaluated against a locked capability version, not against whichever paths happened
to pass. The included SpeakMate V1 regression profile defines:

- `AUTHENTICATION`: registration, login, logout, session restoration, password recovery, and secure
  error/partial-failure paths;
- `VOICE`: capture, STT, conversation, LLM, TTS, audible playback, avatar synchronization, and a
  repeated turn;
- `PWA`: installation, standalone launch, refresh, and offline-shell behavior.

This prevents the founder-observed `registration 503 → retry 409 → login 503` sequence from being
hidden by register/login-only tests, and prevents Authentication from being accepted without secure
password recovery. Voice cannot be accepted from mocked STT/TTS tests when audible browser playback,
avatar synchronization, or the next turn lacks evidence.

## Release governance

A release lists its locked capability IDs and completed runtime-acceptance run IDs. Before a release
candidate can enter review, be approved, or be published, `ReleaseManagementService` verifies that:

- every referenced run exists and belongs to a release product;
- its full commit SHA equals the candidate commit;
- its lifecycle is `COMPLETED`;
- its evidence digest is valid and its capability set is complete;
- every locked release capability is covered.

Missing, stale, `IMPLEMENTED`, `AUTOMATED_VERIFIED`, rejected-human, or incomplete evidence blocks the
release. A named human decision must bind passing `HUMAN_UX_EVIDENCE` for that exact capability and
evidence digest. Release candidates must also belong to the planned version and use a commit declared
by the release. Human acceptance remains separate and never merges or deploys code.
