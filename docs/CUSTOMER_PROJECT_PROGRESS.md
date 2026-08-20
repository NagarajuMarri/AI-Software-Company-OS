# Customer Project Progress Dashboard

Day 20 gives the authenticated customer a read-only answer to a narrow question: what is visible
about this exact governed project before execution has been authorized?

## Authority chain

The service loads the customer-owned product request and requires the exact Day 14 requirements
approval, Day 16 locked PRD, Day 18 locked roadmap, and Day 19 delivery-estimate draft. The
projection binds all upstream identities and digests, including the roadmap approval and estimate.
No digest or project state is accepted from the browser.

The projection has a stable bounded identifier and a canonical SHA-256 digest. It is rebuilt on
every GET and is not persisted. This prevents a display-only module from becoming an accidental
execution system of record.

## Visible model

- Every locked roadmap item becomes one milestone in the original sequence.
- Every locked requirement becomes one planned task under its existing milestone, exactly once.
- The existing `runtime.project_manager` domain calculates aggregate progress.
- All milestone and task states are `NOT_STARTED`; overall progress is `0%`.
- Operational assigned-agent IDs are empty and visibly reported as zero.
- Three open blockers state that execution authority, an operational workforce, and a product
  workspace are unavailable.
- Governed decisions show the exact locked-roadmap and draft-estimate authority digests.

These are planning projections, not executable tasks. The task identifiers cannot be submitted to a
runner and the Day 20 package exposes no command, mutation, assignment, repository, or agent API.

## Web and evidence contract

`GET /customer/requests/{request_id}/progress` requires a verified customer session and session CSRF
context. Other HTTP methods return `405` with `Allow: GET`. The page is customer-scoped, escapes all
customer content, disables caching, and retains the portal's CSP, frame, sniffing, and referrer
controls.

Exact-head CI runs Chromium through customer authentication, the governed request-to-estimate
navigation, progress inspection, logout/login, and recovery of the same projection. It uploads
`project-progress-dashboard.png` plus a content-digested safe manifest as
`day20-founder-customer-project-progress`.

The Community workshop planner used in that journey is test fixture data only. No official ASCOS
pilot product has been selected.

## Explicit exclusions

Day 20 does not approve the estimate, assign agents, persist execution state, create executable
tasks, connect or write a product repository, generate or execute code, merge, deploy, bill,
release, select a pilot, or implement the Day 21 Preview and Evidence Centre.
