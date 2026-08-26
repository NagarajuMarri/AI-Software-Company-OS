# Customer Roadmap Approval and Immutable Lock

Day 18 lets an authenticated customer approve and permanently lock one exact Day 17 roadmap draft.
It creates immutable planning scope without estimating, scheduling, staffing, assigning agents, or
starting implementation.

## Approval contract

The checkpoint renders every roadmap milestone, stable governed item ID, ordered requirement
mapping, and priority. The form accepts only session CSRF, the exact rendered roadmap digest, and one
fixed affirmative confirmation. Customer, request, product, PRD, upstream digests, receipt identity,
status, approver, and time are reloaded or derived server-side.

The service revalidates the complete request-to-roadmap authority chain and rejects missing, stale,
cross-customer, corrupt, tampered, invalid, or mismatched state. One canonical write-once receipt
binds the customer, request, roadmap, product, PRD version and identity, all six source/artifact
digests, confirmation contract, and UTC approval time.

Only the current decomposed roadmap generation profile may receive a new approval. Legacy
single-milestone drafts remain readable but must pass the separately guarded, unapproved-only
regeneration checkpoint first. A legacy draft with an existing approval remains immutable.

## Locked governed projection

The receipt projects only its exact source roadmap into terminal `LOCKED` state. The roadmap and
every milestone item become `LOCKED`; milestone ordering, stable roadmap-item identities, ordered
requirement IDs, priorities, and exactly-once coverage remain byte-for-byte derived from the Day 17
artifact. The authenticated customer is the approver and the receipt timestamp is the lock time.

The schema deliberately has no effort or cost estimate, target date, schedule, assignee, agent,
repository, branch, implementation task, code, deployment, billing, release, or official pilot-
product field. Approval therefore conveys no execution authority.

## Persistence and security

The adapter writes one `roadmap-approval-v0.1.json` envelope per customer/request with exclusive
mode-0600 creation and a full canonical integrity digest. Exact retries return the same receipt;
conflicting writes fail. Reads reconstruct the complete upstream chain and locked projection.
Path containment, bounded identities, closed directories and schemas, symlink/unknown-entry/tamper
rejection, output escaping, no-store responses, CSP, framing, sniffing, and referrer controls remain
mandatory. Locked draft, review, and approval-entry routes return to the immutable receipt.

This file adapter is deterministic single-instance evidence. Production exposure requires
transactional uniqueness, encryption and managed keys, backup/restore, retention/deletion,
observability, rate limits, abuse controls, and privacy review.

## Browser journey and evidence

The customer completes signup through roadmap generation, reviews the exact roadmap, provides the
fixed confirmation, receives the locked receipt, signs out, signs in again, and reopens the same
locked roadmap. Mandatory Chromium CI uploads `roadmap-approved-and-locked.png` and a redacted
content-digest manifest. Community workshop planner is browser test data only; no official ASCOS
pilot product has been selected.

## Explicitly deferred

Day 18 does not estimate or schedule work, assign people or agents, select a pilot product, connect a
repository, create implementation tasks, generate or execute code, merge, deploy, bill, or release.
Day 19 is not included and requires separate founder approval.
