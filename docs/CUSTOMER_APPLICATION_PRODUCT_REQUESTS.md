# Customer Application: Product-Request Intake

Day 11 starts the ASCOS customer application with one reviewable, physically testable slice. A
customer enters a workspace, describes a desired product, submits the brief, and reopens the exact
persisted request. This turns the founder-approved product vision into a durable application
boundary without prematurely combining authentication, AI refinement, agent dispatch, coding, or
deployment.

## Customer journey

1. The Day 12 authentication middleware validates a server-side session and supplies `REMOTE_USER`
   and `ascos.csrf_token` (a trusted upstream gateway remains a supported composition boundary).
2. `GET /customer` renders the customer-scoped workspace and prior product requests.
3. `GET /customer/requests/new` renders a CSRF-protected product form.
4. The customer supplies product name, outcome, target users, one or more required features, and
   optional constraints.
5. `POST /customer/requests` validates the complete bounded form and persists one immutable brief.
6. A 303 redirect opens the customer-scoped confirmation/detail page.
7. A restart reloads the same canonical record; an exact retry returns the original submission.

## Authority and persistence

`CustomerProductRequest` binds a safe request ID and customer ID to the product name, summary,
target users, ordered features, optional constraints, terminal `SUBMITTED` stage, and server time.
Its digest is canonical and independent of storage formatting.

`FileCustomerProductRequestStore` creates each record with an exclusive write, mode 0600, beneath
the customer/request path. It validates the closed schema, canonical bytes, digest, path identity,
and model on every read. It never edits or deletes a submitted request. The service treats only a
business-identical retry as idempotent; changed reuse is a conflict.

The file adapter is a development and deterministic-test adapter. A later customer-application
module may add a database implementation behind the same domain boundary.

## Web and trust boundary

`CustomerPortalApplication` is dependency-free WSGI so the domain remains framework-neutral. It
does not trust customer identity or CSRF values from request headers. Day 12 now supplies the real
account/session middleware that provides those server-side environment authorities; a production
deployment must additionally supply TLS, managed persistence, rate limiting, recovery, monitoring,
and other later operational controls.

The portal accepts only bounded URL-encoded forms with a closed single-value field set. It uses a
constant-time CSRF comparison, escapes all customer values, never echoes an invalid submission, and
sets no-store, restrictive CSP, frame denial, content-type sniffing denial, and no-referrer headers.
Requests can be read only through the current customer identity.

## Physical evidence

Mandatory Chromium CI starts the portal with deterministic trusted identity/session middleware,
opens an empty workspace, completes the product form, follows the redirect, verifies the submitted
detail, and confirms the persisted record. The `day11-founder-customer-application` artifact
contains:

- `customer-product-request.png` — the real confirmation/detail page;
- `manifest.json` — safe claims plus request/screenshot digests.

The evidence pack excludes credentials, session identifiers, CSRF values, and secrets. The
deterministic fixture proves the customer journey and persistence contract, not production
authentication or deployment.

## Explicit non-goals

Day 11 does not implement:

- customer signup, password login, sessions, recovery, organizations, or roles;
- conversational/AI requirement refinement or PRD approval;
- repository connection, product planning, agent assignment, coding, testing orchestration, billing,
  merge, deployment, or release;
- file uploads, secrets, regulated-data intake, or a public production server.
