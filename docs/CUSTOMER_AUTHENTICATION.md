# Customer Authentication and Returning Sessions

Day 12 turns the Day 11 customer workspace into an account-backed application. A customer can create
an account, keep a server-side session, sign out, sign back in, and recover the product requests owned
by the same durable customer identity. The module is framework-neutral, dependency-free WSGI and
does not grant any agent, repository, deployment, merge, billing, or release authority.

## Customer journey

1. An unauthenticated customer opening `/customer` is redirected to `/login`.
2. `/signup` issues a signed, ten-minute, HttpOnly, SameSite=Strict pre-authentication CSRF cookie.
3. Registration validates the matching form token, canonical email, confirmation, and strong
   password; it persists one account and issues a twelve-hour server-side session.
4. The authenticated middleware validates the bearer token by digest and injects only the account's
   customer ID and session CSRF value into the Day 11 portal.
5. The customer submits or reopens customer-scoped product briefs.
6. `POST /logout` requires the current session CSRF value, persists revocation, clears the cookie,
   and redirects to login.
7. A new login issues a new session for the same customer identity; the prior product requests remain
   visible after navigation, process/storage restart, and browser reload.

## Credential and session authority

`CustomerAccount` binds a generated safe customer ID to canonical ASCII email, a 128-bit salt, a
32-byte scrypt digest (`N=16384`, `r=8`, `p=1`), and timezone-aware creation time. Passwords are
12–128 characters and require upper case, lower case, and a digit. The raw password is never stored.

`CustomerSession` binds the SHA-256 digest of a random bearer token to the customer, an independent
random CSRF token, issue time, and twelve-hour expiry. Only `IssuedCustomerSession` temporarily
returns the raw bearer value to the WSGI response. Logout writes a durable revocation authority;
revoked and expired sessions cannot authenticate after restart.

The file stores are deterministic development/test adapters. They use hashed filenames, contained
paths, mode-0600 exclusive writes, canonical JSON, closed schemas, record digests, and byte-level
canonical validation. Symlinks, traversal, mutation, malformed authority, collisions, and invented
session revocation fail closed.

## Browser and trust boundary

Session cookies are HttpOnly, SameSite=Strict, path scoped, and Secure except when an explicit
loopback HTTP test composition disables the Secure flag. Authentication responses use no-store,
restrictive CSP, frame denial, content-type sniffing denial, and no-referrer policy. Wrong password
and unknown account both produce the same public response. Invalid forms do not echo customer input.

The browser cannot supply `REMOTE_USER` or `ascos.csrf_token` as trusted headers. The authentication
middleware derives both only after server-side session validation and delegates them through the
in-process WSGI environment.

## Physical evidence

Mandatory Chromium CI runs the full returning-customer journey and uploads
`day12-founder-customer-authentication` containing:

- `login.png` — the actual unauthenticated sign-in screen;
- `returning-workspace.png` — the existing product request visible after logout and new login;
- `manifest.json` — bounded claims and content digests for both screenshots and the product request.

The test also verifies HttpOnly/SameSite cookie behavior, persistence, reload, no console failures,
no failed browser requests, and absence of raw password material from stored authority. Evidence
contains no password, bearer token, CSRF value, salt, cookie/header, or local path.

## Explicit non-goals

Day 12 does not implement password reset/recovery, email verification, MFA, organizations, roles,
rate limiting, production mail, distributed sessions, billing, AI requirements refinement, agent
dispatch, repository connection, coding, testing orchestration, merge, deployment, or release.
