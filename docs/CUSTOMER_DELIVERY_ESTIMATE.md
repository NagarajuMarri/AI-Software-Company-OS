# Customer Delivery Estimate Draft

Day 19 lets an authenticated customer generate and reopen one deterministic delivery-effort
estimate from the exact locked Day 18 roadmap. The result is version 0.1 and always remains
`DRAFT`. It is a review artifact, not a quote, calendar plan, or authorization to begin work.

## Authority chain

Generation requires the authenticated owner, session CSRF authority, and the exact roadmap-
approval digest rendered by the checkpoint. ASCOS reloads the complete Day 11-18 chain server-side:

1. immutable customer product request;
2. locked requirements revision and approval receipt;
3. locked PRD and approval receipt;
4. source roadmap, approval receipt, and governed `LOCKED` projection.

The estimate binds every upstream identity and digest. Customer, request, roadmap, approval,
product, PRD, requirement mapping, generation time, and estimate identity cannot be asserted by the
form. Missing, stale, cross-customer, corrupt, tampered, unlocked, or mismatched authority fails
closed.

## Deterministic effort model

The profile `ascos-deterministic-customer-delivery-estimate-v1` performs no network, external-AI,
repository, subprocess, secret-manager, or agent call. For each locked roadmap item it:

- maps every locked requirement exactly once, preserving the governed item ID and sequence;
- assigns priority points of Critical 5, High 4, Medium 3, and Low 2;
- adds category points from 0 to 2 for the governed requirement category;
- uses the resulting points as the minimum relative engineering-day effort;
- applies a transparent uncertainty factor of 1.20 for no personal data, 1.35 for personal data,
  or 1.60 for sensitive data, rounded upward, to produce the maximum;
- reports the requirement count, priority set, scope-type set, declared data class, and approved
  platforms as visible drivers; and
- exposes a High, Medium, or Low confidence signal based only on data sensitivity and requirement
  count.

An engineering day is a relative effort unit, not a calendar duration. The visible assumptions say
that team composition, agent assignment, repository condition, dependencies, integrations,
production environment, pricing, billing, taxes, usage charges, contingency, and support operations
are not yet known or included. A later separately approved module must review capacity and
dependencies before proposing a schedule.

## Persistence and browser boundary

One canonical integrity-digested envelope is created exclusively with mode 0600 under the owning
customer/request path. The derived estimate identity is bounded and non-secret. Writes are
write-once, exact retries are idempotent, reads reconstruct and compare the deterministic expected
record, and restart, path-containment, closed-schema, unknown-entry, symlink, and tamper checks fail
closed.

The WSGI boundary accepts only the exact bounded URL-encoded field set and session CSRF, escapes all
customer content, and preserves no-store, restrictive CSP, frame denial, sniffing denial, and
no-referrer protections. Mandatory exact-head Chromium CI proves the entire customer journey,
generation, complete mapping, logout/login, and reopening the same draft. Its artifact contains a
founder-safe screenshot and digest manifest without passwords, bearer tokens, cookies, CSRF values,
salts, or local paths.

## Explicit exclusions

Day 19 does not approve an estimate, create a price or quote, set a date or schedule, assign staff or
agents, connect a repository, create implementation tasks, generate or execute code, merge, deploy,
bill, release, or select an official pilot product. Day 20 remains a separate founder-gated module.
