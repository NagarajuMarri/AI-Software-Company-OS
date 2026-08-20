# Customer Preview and Evidence Centre

Day 21 gives the authenticated customer one bounded review surface for an existing product preview
and the exact evidence supporting it. It does not create, host, or deploy the preview.

## Authority chain

An internal service boundary records one preview package only after loading the customer-owned Day
20 progress projection. The package binds customer, request, product, progress identity and digest,
locked-roadmap digest, Day 19 estimate digest, preview label and URL, full commit SHA, and every
evidence artifact. The customer browser cannot assert or replace any of these values.

The preview origin must be in the service's explicit canonical allowlist. Production URLs require
HTTPS; HTTP is accepted only for `localhost`, `127.0.0.1`, or `::1` test fixtures. Credentials,
queries, and fragments are forbidden. The allowlist is rechecked whenever the centre is read.

## Evidence and decision contract

The package reuses `runtime.runtime_acceptance.EvidenceArtifact` and requires these governed kinds:

- automated test;
- Chromium browser;
- browser console;
- browser network;
- screenshot; and
- security.

Every required artifact binds the same full commit SHA. `ACCEPT` is unavailable when any required
result fails. `REVISE` remains available and requires comments explaining the requested change.
Both decisions require the exact package digest displayed to the customer, the session CSRF value,
and confirmation that the preview and evidence were reviewed.

Exactly one review receipt can be recorded. It binds the customer, request, package identity and
digest, progress digest, exact decision, comments, fixed confirmation contract, and UTC review time.
An identical retry returns the same receipt; a different later decision fails closed.

## Web and persistence contract

- `GET /customer/requests/{request_id}/evidence` shows the package, artifacts, and receipt/form.
- `GET /customer/requests/{request_id}/evidence/preview` redirects only to the recorded URL.
- `POST /customer/requests/{request_id}/evidence/review` accepts the closed bounded decision form.

The package and receipt are separate canonical write-once JSON records with full integrity digests,
exclusive mode-0600 creation, customer/request path containment, closed fields/directories,
restart-safe validation, and symlink/tamper rejection. Customer text is escaped and pages preserve
the customer portal's no-store, CSP, frame, sniffing, and referrer protections.

Exact-head CI uses real Chromium to authenticate, navigate through the governed customer project,
inspect all evidence, open a separate loopback preview fixture, submit `ACCEPT`, sign out/in, and
reopen the same receipt. It uploads `preview-evidence-centre.png`,
`fixture-preview-opened.png`, `customer-accept-receipt.png`, and a content-digested manifest as
`day21-founder-customer-preview-evidence`.

The Community workshop planner shown by that test is verification data only. No official ASCOS
pilot product has been selected.

## Explicit exclusions

Day 21 does not create or deploy a preview, create a product workspace or executable task, activate
or run an agent, connect or write a repository, generate code, merge, deploy, bill, release, select
a pilot, or implement the Day 22 Digital Twin execution runtime.
