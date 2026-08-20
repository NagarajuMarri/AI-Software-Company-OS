# Customer PRD Approval and Immutable Lock

Day 16 gives an authenticated customer one explicit checkpoint for approving the exact Day 15 PRD.
It freezes product scope without starting planning or implementation.

## Contract

The checkpoint renders the complete PRD: problem, target users, primary journey, every requirement
and acceptance criterion, success metrics, exclusions, platforms, data declaration, priority, source
references, version, and artifact digest. Submission requires session CSRF, the exact rendered PRD
digest, and one fixed affirmative confirmation.

The service reloads the customer-owned product request, requirements draft, requirements approval,
and PRD. It accepts no customer, product, authority identity, lifecycle state, or timestamp from the
form. One `customer-prd-v1` receipt binds all identities plus the source-request, requirements,
requirements-approval, and PRD digests.

## Governed lifecycle

ASCOS projects the exact receipt through the existing Product Requirements domain:

1. the Day 15 document and requirements begin as `DRAFT`;
2. the exact version enters `UNDER_REVIEW`;
3. the authenticated customer becomes the recorded approver at `APPROVED`; and
4. the same version and every requirement become `LOCKED` at the receipt time.

The projection must pass `validate_prd`, preserve the empty future-roadmap field, and record the
review, approval, lock, and approval-history evidence. The receipt is the durable authority; the
locked document is deterministically reconstructed and revalidated on every read.

## Browser journey and evidence

The customer reviews the Day 15 draft, opens the approval checkpoint, selects the required
confirmation, receives the locked receipt, signs out, signs back in, and reopens the same locked PRD.
Mandatory Chromium CI uploads `prd-approved-and-locked.png` and a redacted manifest containing only
safe identities, digests, result claims, and the explicit no-pilot fixture contract.

## Persistence and security

The adapter writes one `prd-approval-v0.1.json` envelope per customer/request using exclusive
mode-0600 creation and a full integrity digest. Reads validate schema, derived identities, exact
authority bindings, containment, known directory contents, and the absence of symlinks. Exact retries
return the same receipt; different content conflicts. Responses remain non-cacheable with restrictive
CSP, frame, content-type, and referrer protections.

This adapter is development evidence, not a production database. Production use requires
transactional uniqueness, encryption and managed keys, backup/restore, retention/deletion,
observability, abuse controls, rate limits, and privacy review.

## Explicitly deferred

Day 16 does not create a roadmap, estimate or schedule work, assign agents, select an official pilot
product, connect a Git repository, generate or execute code, merge, deploy, bill, or release. Each
requires a later bounded founder-approved module.
