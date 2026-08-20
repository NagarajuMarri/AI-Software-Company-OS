# Customer Requirements Approval and Lock

Day 14 converts one reviewed Day 13 draft into an immutable customer-approved requirements baseline.
It is an explicit scope checkpoint. It does not authorize ASCOS to generate a PRD, plan delivery,
assign agents, connect a repository, write code, merge, deploy, bill, or release.

## Customer journey

1. The signed-in owner opens the saved requirements review and selects **Approve requirements**.
2. The checkpoint displays the complete current scope plus its revision and full digest.
3. The owner must select an affirmative statement confirming that exact scope.
4. The server reloads the owned product request and latest draft, checks the session CSRF value,
   exact revision, complete digest, and confirmation, then writes one approval receipt.
5. The receipt page shows the approved scope, approval time, receipt identity, requirements digest,
   and receipt digest while stating that implementation has not started.
6. Editing the approved draft redirects to the receipt. After logout and a new login, the same
   customer reopens the locked baseline; other customers receive no record disclosure.

## Authority contract

`CustomerRequirementsApproval` binds:

- approval, customer, request, and draft identities;
- the exact positive draft revision;
- immutable source-request and full requirements digests;
- confirmation contract `customer-requirements-v1`; and
- timezone-aware server approval time.

The approval ID, time, source digest, and draft authority are assigned or reloaded server-side. An
exact retry returns the same receipt. A stale revision/digest, changed source, conflicting receipt,
or approval without an existing draft fails closed.

`FileCustomerRequirementsApprovalStore` creates a canonical `approval.json` exactly once with mode
0600 and an integrity digest. Reads require a closed envelope and record, canonical bytes, matching
path identity and derived approval identity, contained directories, regular files, and no unknown
entries or symlinks. A valid receipt is the lock checked by every later draft save.

The file adapter is intentionally deterministic for development and CI. Production requires a
transactional database uniqueness/locking constraint that covers approval creation and draft
revision together, plus managed backup, retention, encryption, monitoring, rate limiting, and
privacy controls.

## Web and security boundary

The approval routes accept identity and CSRF authority only from the authenticated WSGI environment.
The POST body is a bounded URL-encoded closed schema containing only CSRF, expected revision, expected
digest, and fixed confirmation. Customer content is escaped. Responses are no-store and use
restrictive CSP, framing denial, content-type sniffing denial, and no-referrer policy. Rejected forms
never echo submitted authority or customer content.

## Physical evidence

Mandatory Chromium CI exercises signup, product intake, guided refinement, approval checkpoint,
explicit confirmation, receipt display, blocked editing, logout, returning login, and approved
baseline recovery. The `day14-founder-requirements-approval` artifact contains:

- `requirements-approved.png` — the actual locked customer baseline and receipt; and
- `manifest.json` — source, draft, approval, and screenshot digests plus bounded pass claims.

The artifact excludes passwords, bearer tokens, cookies, CSRF values, salts, and local paths.

## Explicit non-goals

Day 14 does not revise requirements after approval, generate or approve a PRD, create a roadmap,
estimate delivery, dispatch agents, connect repositories, generate code, execute customer-product
tests, merge, deploy, charge a customer, or release software.
