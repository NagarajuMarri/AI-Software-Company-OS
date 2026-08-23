# Customer PRD Draft

Day 15 connects the approved customer scope to ASCOS's existing governed Product Requirements
domain. It creates a traceable, deterministic PRD draft that the customer can inspect in the browser.
It deliberately stops before approval, planning, or implementation.

## Contract

Generation requires the current authenticated customer, session CSRF, and the exact Day 14 approval
digest shown at the checkpoint. The service reloads the owned Day 11 request, the locked Day 13
requirements revision, and its Day 14 approval receipt. It rejects the operation unless customer,
request, revision, source-request digest, requirements digest, and receipt digest all agree.

`ascos-deterministic-customer-prd-v1` maps the approved baseline without an external model call:

- the primary journey and desired outcomes become `REQ-JOURNEY-001`;
- each ordered must-have feature becomes `REQ-FEATURE-NNN` with capability-specific,
  testable success, validation-failure, and authorization criteria;
- each source constraint becomes a mandatory, traceable `REQ-CONSTRAINT-NNN` requirement;
- platforms become `REQ-PLATFORM-001`;
- declared data sensitivity becomes `REQ-DATA-001`;
- success metrics remain visible as product-level PRD metrics;
- only non-goals become de-duplicated explicit exclusions; and
- every generated requirement records the exact approved field that sourced it.

The result has stable artifact, product, and PRD identifiers, version `0.1`, and immutable digest
bindings. Projection into `ProductRequirementsDocument` must pass `validate_prd`; its document and
requirements remain `DRAFT`, its approver is empty, and its future roadmap is empty.

## Browser journey and evidence

The customer opens the approved receipt, visits the generation checkpoint, explicitly creates the
draft, and reviews the complete mapped scope and source references. Reopening the checkpoint returns
the existing artifact. Mandatory Chromium CI proves signup, product intake, refinement, approval,
generation, review, logout/login, product recovery, and PRD recovery without console or request
failures. It uploads `prd-draft-review.png` plus a safe manifest containing only identifiers, digests,
the generation profile, and verified claims.

## Persistence and security

The file adapter writes one canonical `prd-v0.1.json` envelope per customer/request using exclusive
mode-0600 creation and a full integrity digest. Reads validate schema, derived identities, exact
source bindings, containment, known directory contents, and the absence of symlinks. Exact retries
return the same artifact; different content conflicts. Customer text is escaped, POST fields are
closed and bounded, responses retain the portal's restrictive browser headers, and cross-customer
lookups return generic not-found behavior.

This adapter is development evidence, not a production database. Production use requires a
transactional uniqueness constraint, encryption and managed keys, backup/restore, retention and
deletion controls, observability, abuse controls, and privacy review.

## Explicitly deferred

Day 15 does not approve or lock the PRD, create a roadmap or estimate, assign agents, connect a Git
repository, generate or execute code, merge, deploy, bill, or release. Those actions require later
modules and their own explicit authority.
