# Customer PRD Acceptance-Criteria Refinement

This checkpoint converts generated feature templates into customer-reviewed, product-specific test
authority without calling an external model or accessing a repository.

## Contract

The authenticated customer opens `/customer/requests/{request_id}/prd/criteria` from an unapproved
PRD review. The form includes only ordered `REQ-FEATURE-NNN` requirements. Each feature requires two
to five non-empty, unique criteria of at most 500 characters. Every generated default tuple must be
replaced before locking succeeds.

Submission requires session CSRF, the exact source PRD digest, a closed set of feature fields, and a
fixed affirmative confirmation. Scope, descriptions, constraints, metrics, exclusions, platforms,
data classification, priorities, and source references are not editable at this checkpoint.

## Authority and lifecycle

One `customer-prd-criteria-v1` baseline records the customer and request identities, exact source PRD
digest, ordered complete feature coverage, refined criteria, confirmation version, lock timestamp,
and content digest. The baseline is write-once. Exact retries are idempotent and different retries
conflict.

ASCOS deterministically overlays only the locked feature criteria onto the source PRD. The resulting
effective PRD has a new digest, which the later PRD approval receipt binds. Approval is unavailable
until this baseline exists. Once the PRD is approved, the criteria route redirects to the immutable
PRD receipt and cannot change the baseline.

## Persistence and security

The local adapter stores one mode-0600 `criteria-v0.1.json` envelope per customer/request. Reads
validate schema, derived identity, source binding, complete ordered feature coverage, content digest,
path containment, closed directory contents, and symlink absence. Forms are size-bounded,
field-closed, CSRF-protected, customer-scoped, escaped, non-cacheable, and restricted by the portal's
CSP and browser headers.

This development adapter still requires transactional uniqueness, managed encryption, retention,
backup/restore, observability, abuse controls, and privacy review for production use.

## Explicitly deferred

Criteria refinement does not approve the PRD, create a roadmap, estimate work, assign agents, call
Codex, access or modify a product repository, deploy, bill, release, or continue a pilot.
