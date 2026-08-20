# Customer Guided Requirements Drafts

Day 13 gives an authenticated customer a structured way to clarify what ASCOS should eventually
build. It preserves the original Day 11 product request as immutable authority and records each
clarification as a separate write-once draft revision. This is product discovery, not approval,
planning, agent dispatch, coding, or deployment.

## Customer journey

1. The customer signs in through the Day 12 session boundary.
2. The customer opens an owned Day 11 product request and selects **Refine requirements**.
3. The form displays the immutable outcome and constraints from the source request.
4. The customer supplies a primary user journey, desired outcomes, reconciled must-have features,
   measurable success metrics, explicit non-goals, delivery platforms, data sensitivity, and
   delivery priority.
5. `POST /customer/requests/{request_id}/requirements` validates trusted session CSRF and the exact
   bounded form, reloads the source request, verifies the expected latest revision, and appends one
   canonical draft.
6. The review page displays the clarified scope and labels it **Draft saved** and **no implementation
   has started**.
7. After logout and a new login, the same customer can reopen the saved draft; another customer
   receives no knowledge that the request or draft exists.

## Authority and revision model

`CustomerRequirementsDraft` binds the customer/request identities and exact source-request digest to
all guided fields, the server-assigned revision and time, and a bounded draft identity derived from a
SHA-256 request-ID digest. Its canonical digest changes with any authority field.

`FileCustomerRequirementsStore` stores `revision-000001.json`, `revision-000002.json`, and later
immutable revisions beneath the customer/request path. It requires a closed schema, canonical bytes,
matching digest and path identity, contiguous filenames, a maximum of 1,000 revisions, safe regular
files, and contained paths. Each new file is created exclusively with mode 0600 and flushed to disk.

`CustomerRequirementsService` always reloads the customer-owned source request. It derives the draft
ID, source digest, canonical platform order, revision, and time server-side. A business-identical
retry returns the current revision. Changed content requires the exact current revision, preventing a
stale browser tab from overwriting a newer clarification.

The file adapter is a deterministic development/test adapter. Production exposure later requires a
transactional database implementation, backups, retention policy, operational monitoring, abuse
controls, and applicable privacy/compliance review.

## Web and trust boundary

The Day 13 router handles only the requirements edit/review paths and delegates all other paths to the
existing Day 11 portal. Day 12 authentication injects customer identity and CSRF authority through
the in-process WSGI environment. Neither is accepted from a customer-controlled form or header.

The form has bounded bytes, field count, line count, line length, and enum values. It accepts one or
more known platforms and canonicalizes their order. Customer content is escaped on both form and
review pages. Responses are non-cacheable and use restrictive CSP, frame denial, content-type
sniffing denial, and no-referrer policy.

## Physical evidence

Mandatory Chromium CI runs the complete signed-in and returning-customer flow. The
`day13-founder-guided-requirements` artifact contains:

- `requirements-review.png` — the real saved draft review screen;
- `manifest.json` — source/draft/screenshot digests plus bounded pass claims.

The artifact proves form completion, immutable persistence, returning access, browser security, and
the absence of implementation authority. It excludes passwords, bearer tokens, cookies, CSRF
values, salts, and local paths.

## Explicit non-goals

Day 13 does not approve or lock the draft, generate a governed PRD, converse with an external AI
provider, plan milestones, estimate cost, assign agents, connect repositories, write code, execute
tests against a generated product, merge, deploy, bill, or release.
