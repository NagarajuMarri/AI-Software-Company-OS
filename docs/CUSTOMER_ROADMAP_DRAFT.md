# Traceable Customer Roadmap Draft

Day 17 lets an authenticated customer create one deterministic roadmap v0.1 from the exact Day 16
locked PRD. It makes the first planning artifact visible without estimating, scheduling, assigning,
or implementing work.

## Contract

The generation checkpoint accepts only session CSRF and the exact rendered PRD-approval digest. The
service reloads the complete customer-owned request, requirements, requirements approval, PRD, PRD
approval, and governed locked document server-side. The resulting record binds every identity and
digest in that authority chain.

The v2 deterministic profile requires the complete PRD to be valid and `LOCKED`, then decomposes it
into bounded dependency-ordered stages. Platform, data, and cross-cutting constraints establish the
foundation and guardrails first; feature requirements are delivered in ordered increments of no
more than five; remaining operational requirements follow; and the primary journey becomes the
final end-to-end acceptance milestone. Each stable roadmap item preserves deterministic sequence,
ordered requirement IDs, and requirement priorities. Every locked requirement appears exactly once
and no other requirement may appear.

Complexity is never collapsed merely because every generated PRD requirement originally carried the
same placeholder milestone. A 43-requirement PRD, for example, produces multiple bounded milestones
rather than one unactionable “Customer MVP” bucket.

## Legacy draft regeneration

Existing v1 single-milestone drafts remain readable so the authority chain does not become corrupt.
They cannot receive a new approval. If and only if no roadmap approval receipt exists, the review
page offers explicit regeneration into the v2 profile. Regeneration preserves the customer, request,
product, PRD, approval identities, and every upstream digest while atomically replacing the exact
legacy draft. Approved legacy roadmaps remain immutable and cannot be regenerated.

## Draft boundary

The artifact and each rendered item remain `DRAFT`. The schema deliberately contains no effort or
cost estimate, target date, schedule commitment, assignee, agent, repository, branch, implementation
task, deployment, billing, release, or pilot-product field. Roadmap approval and every later planning
or delivery authority require separate founder-approved modules.

## Browser journey and evidence

The customer completes the existing signup-to-locked-PRD journey, opens the roadmap checkpoint,
generates the draft, inspects all requirement mappings, signs out, signs in again, and reopens the
same roadmap. Mandatory Chromium CI uploads `roadmap-draft-generated.png` plus a redacted digest and
claim manifest. The Community workshop planner shown there is browser test data only; no official
ASCOS pilot product has been selected.

## Persistence and security

The adapter writes one `roadmap-v0.1.json` envelope per customer/request with exclusive mode-0600
creation and a full canonical integrity digest. Reads revalidate the complete upstream authority and
compare the exact milestone mapping for that record's generation profile. Exact v2 retries return the
same record; changed content conflicts. The one legacy-regeneration path uses an exact source digest,
approval-state guard, mode-0600 temporary file, fsync, and atomic replacement. Containment, closed
directories, bounded identities, symlink rejection, output escaping, no-store responses, CSP,
framing, sniffing, and referrer controls remain mandatory.

This file adapter is deterministic single-instance evidence. Production exposure requires
transactional uniqueness, encryption and managed keys, backup/restore, retention/deletion,
observability, rate limits, abuse controls, and privacy review.

## Explicitly deferred

Day 17 does not approve the roadmap, estimate or schedule work, assign people or agents, select an
official pilot product, connect a repository, create implementation tasks, generate or execute code,
merge, deploy, bill, or release. Day 18 is not included.
